# Troubleshooting

## `No token found in auth_kv key: kirocli:odic:token`

- Cause: `kiro-cli` is not logged in yet, or local auth DB changed.
- Action:
  1. Re-login in Kiro CLI / Kiro IDE.
  2. Re-run the script.
  3. If DB path is custom, pass `--db-path <path>`.

## `Binary not found or not executable`

- Cause: `kiro-rs` release binary is missing.
- Action:
  1. Build it in target project: `cargo build --release`
  2. Re-run the script.

## Endpoint verification returns non-200

- Cause: service startup failed, wrong API key in `config.json`, or upstream auth issue.
- Action:
  1. Check runtime logs: `logs/kiro-rs.log`
  2. Confirm `config.json` keys (`apiKey`, optional `adminApiKey`)
  3. Retry with `--no-verify` only if you are troubleshooting startup manually.

## `TEMPORARILY_SUSPENDED` from upstream

- Cause: account status issue upstream (not a local JSON format issue).
- Action:
  1. Follow the provider support link in error message.
  2. Keep local sync script unchanged; the script cannot bypass provider suspension.
