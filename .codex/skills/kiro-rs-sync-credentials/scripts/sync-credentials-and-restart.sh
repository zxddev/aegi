#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PROJECT_DIR="/home/user/workspace/gitcode/aegi/code/temp/kiro.rs"
DEFAULT_DB_PATH="${HOME}/.local/share/kiro-cli/data.sqlite3"

project_dir="${DEFAULT_PROJECT_DIR}"
db_path="${DEFAULT_DB_PATH}"
do_restart=1
do_verify=1

usage() {
  cat <<'EOF'
Sync latest kiro-cli OIDC credentials into kiro-rs credentials.json, restart service, and verify health.

Usage:
  sync-credentials-and-restart.sh [options]

Options:
  --project-dir <path>  Target kiro-rs project directory
  --db-path <path>      Source kiro-cli sqlite database path
  --no-restart          Only update credentials.json
  --no-verify           Skip HTTP endpoint checks
  -h, --help            Show this help message
EOF
}

log() {
  printf '[info] %s\n' "$*"
}

error() {
  printf '[error] %s\n' "$*" >&2
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "Missing required command: $cmd"
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      [[ $# -ge 2 ]] || {
        error "--project-dir needs a value"
        exit 1
      }
      project_dir="$2"
      shift 2
      ;;
    --db-path)
      [[ $# -ge 2 ]] || {
        error "--db-path needs a value"
        exit 1
      }
      db_path="$2"
      shift 2
      ;;
    --no-restart)
      do_restart=0
      shift
      ;;
    --no-verify)
      do_verify=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

require_cmd jq
require_cmd sqlite3
require_cmd curl
require_cmd pgrep
require_cmd pkill
require_cmd setsid

credentials_file="${project_dir}/credentials.json"
config_file="${project_dir}/config.json"
binary_file="${project_dir}/target/release/kiro-rs"
log_file="${project_dir}/logs/kiro-rs.log"

[[ -d "$project_dir" ]] || {
  error "Project directory not found: $project_dir"
  exit 1
}
[[ -f "$db_path" ]] || {
  error "Kiro DB not found: $db_path"
  exit 1
}
[[ -f "$credentials_file" ]] || {
  error "credentials.json not found: $credentials_file"
  exit 1
}
[[ -f "$config_file" ]] || {
  error "config.json not found: $config_file"
  exit 1
}

token_json="$(sqlite3 "$db_path" "SELECT value FROM auth_kv WHERE key='kirocli:odic:token';")"
device_json="$(sqlite3 "$db_path" "SELECT value FROM auth_kv WHERE key='kirocli:odic:device-registration';")"

[[ -n "$token_json" ]] || {
  error "No token found in auth_kv key: kirocli:odic:token"
  exit 1
}
[[ -n "$device_json" ]] || {
  error "No device registration found in auth_kv key: kirocli:odic:device-registration"
  exit 1
}

printf '%s' "$token_json" | jq -e '.refresh_token and .access_token and .expires_at' >/dev/null
printf '%s' "$device_json" | jq -e '.client_id and .client_secret' >/dev/null

machine_id="$(jq -r '.machineId // empty' "$credentials_file" 2>/dev/null || true)"
if [[ -z "$machine_id" ]]; then
  machine_id="$(jq -r '.machineId // empty' "$config_file" 2>/dev/null || true)"
fi

backup_file="${credentials_file%.json}.backup.$(date +%Y%m%d_%H%M%S).json"
cp "$credentials_file" "$backup_file"

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

jq -n \
  --argjson token "$token_json" \
  --argjson device "$device_json" \
  --arg machine_id "$machine_id" \
  '{
    accessToken: $token.access_token,
    refreshToken: $token.refresh_token,
    expiresAt: $token.expires_at,
    authMethod: "idc",
    clientId: $device.client_id,
    clientSecret: $device.client_secret,
    region: ($token.region // "us-east-1"),
    machineId: $machine_id
  }' >"$tmp_file"

mv "$tmp_file" "$credentials_file"
trap - EXIT
rm -f "$tmp_file"

log "credentials.json updated"
log "backup created: $backup_file"

if [[ "$do_restart" -eq 1 ]]; then
  [[ -x "$binary_file" ]] || {
    error "Binary not found or not executable: $binary_file"
    exit 1
  }

  old_pids="$(pgrep -f 'target/release/kiro-rs' || true)"
  if [[ -n "$old_pids" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done <<<"$old_pids"
    sleep 1
    old_pids="$(pgrep -f 'target/release/kiro-rs' || true)"
    if [[ -n "$old_pids" ]]; then
      while IFS= read -r pid; do
        [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
      done <<<"$old_pids"
    fi
  fi

  mkdir -p "$(dirname "$log_file")"
  (
    cd "$project_dir"
    setsid ./target/release/kiro-rs >>"$log_file" 2>&1 < /dev/null &
  )
  sleep 2

  new_pid="$(pgrep -f 'target/release/kiro-rs' | head -n 1 || true)"
  [[ -n "$new_pid" ]] || {
    error "kiro-rs failed to start, check $log_file"
    exit 1
  }
  log "kiro-rs started, pid=$new_pid"
fi

if [[ "$do_verify" -eq 1 ]]; then
  host="$(jq -r '.host // "127.0.0.1"' "$config_file" 2>/dev/null || echo "127.0.0.1")"
  port="$(jq -r '.port // 8990' "$config_file" 2>/dev/null || echo "8990")"
  api_key="$(jq -r '.apiKey // empty' "$config_file" 2>/dev/null || true)"
  admin_api_key="$(jq -r '.adminApiKey // empty' "$config_file" 2>/dev/null || true)"

  if [[ "$host" == "0.0.0.0" || "$host" == "::" || "$host" == "[::]" ]]; then
    host="127.0.0.1"
  fi

  if [[ -n "$api_key" ]]; then
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 \
      "http://${host}:${port}/v1/models" \
      -H "Authorization: Bearer ${api_key}")"
    [[ "$code" == "200" ]] || {
      error "Verification failed: GET /v1/models returned HTTP $code"
      exit 1
    }
    log "verified: GET /v1/models -> 200"
  else
    log "skip /v1/models verification (apiKey missing in config.json)"
  fi

  if [[ -n "$admin_api_key" ]]; then
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 \
      "http://${host}:${port}/api/admin/credentials" \
      -H "Authorization: Bearer ${admin_api_key}")"
    [[ "$code" == "200" ]] || {
      error "Verification failed: GET /api/admin/credentials returned HTTP $code"
      exit 1
    }
    log "verified: GET /api/admin/credentials -> 200"
  else
    log "skip admin verification (adminApiKey missing in config.json)"
  fi
fi

log "done"
