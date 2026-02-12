---
name: kiro-rs-sync-credentials
description: Synchronize latest Kiro CLI OIDC credentials from ~/.local/share/kiro-cli/data.sqlite3 into code/temp/kiro.rs/credentials.json, back up old credentials, restart kiro-rs, and verify health endpoints. Use when the user asks to update Kiro credentials, rotate refresh token, recover from disabled/expired credentials, or restart kiro-rs after auth failures.
---

# Kiro Rs Sync Credentials

Update and validate `kiro-rs` credentials in a reproducible way.

## Quick Start

Run the automation script:

```bash
bash scripts/sync-credentials-and-restart.sh
```

Default behavior:
- Read latest token and device registration from `~/.local/share/kiro-cli/data.sqlite3`
- Rewrite `credentials.json` using those values
- Create timestamped backup next to `credentials.json`
- Restart `kiro-rs` with detached process mode
- Verify `/v1/models` and `/api/admin/credentials` (when API keys exist in `config.json`)

## Parameters

- `--project-dir <path>`: Target `kiro-rs` directory.
- `--db-path <path>`: Source SQLite DB path for `kiro-cli` credentials.
- `--no-restart`: Update credentials only.
- `--no-verify`: Skip endpoint checks.
- `--help`: Show usage.

Example with explicit target:

```bash
bash scripts/sync-credentials-and-restart.sh \
  --project-dir /home/user/workspace/gitcode/aegi/code/temp/kiro.rs
```

## Preconditions

- `jq`, `sqlite3`, `curl`, `pgrep`, `pkill`, `setsid` available in PATH
- `target/release/kiro-rs` exists in target project
- Target project has `config.json` and `credentials.json`

## Expected Output

After success, report:
- Backup file path
- Current `kiro-rs` PID
- HTTP status checks (`/v1/models`, optional admin endpoint)

## Troubleshooting

Read `references/troubleshooting.md` when:
- SQL keys are missing in `kiro-cli` DB
- Endpoints fail after restart
- Upstream rejects credential requests (for example `TEMPORARILY_SUSPENDED`)
