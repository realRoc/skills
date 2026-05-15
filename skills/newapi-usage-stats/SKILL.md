---
name: newapi-usage-stats
description: Query a NewAPI gateway MySQL database for per-model usage stats (RPM/TPM, total tokens, peak minute) over a given time window, filtered by NewAPI username. Designed for the common case where NewAPI's MySQL is only reachable from inside a backend container running on a Tencent Cloud CVM. Uses Tencent Cloud TAT (Automation Tools) to run a read-only Python script inside that container; the container already holds the MySQL DSN in its environment, so credentials never leave the box. Use when asked to compute RPM/TPM for NewAPI models, audit askmanyai/teamo/upstream-user consumption, size rate-limit quotas from real traffic, or report per-model token volume for any hour/day window.
---

# NewAPI Usage Stats (RPM / TPM)

Read-only audit of NewAPI `logs` table. Computes per-model:

- request count, prompt/completion/total tokens
- **average RPM** and **average TPM** over the window
- **peak minute** (by tokens and by requests) — useful for rate-limit sizing
- average tokens per request

Window granularity is minutes; the query joins nothing and uses the `(model_name, username)` composite index plus the `(created_at, type)` index.

## Threat model & credentials policy

This skill never embeds:

- Tencent Cloud SecretId / SecretKey
- CVM instance IDs, regions, public IPs
- Backend container names
- NewAPI MySQL host, port, user, password, database

**Every invocation must collect these from the user.** Do not cache TAT credentials between runs — ask the user for them each time the skill triggers, even if you saw them earlier in the session.

The MySQL DSN is read **inside the container** from the `SQL__MYSQL_CONNECT` (or user-specified) environment variable. The local machine never sees the DSN.

The remote Python script is read-only (only `SELECT` queries against `logs`). Reject any modification request that would add writes.

## Required inputs

Collect each invocation:

| Input | Example | Notes |
|---|---|---|
| Tencent Cloud SecretId | `AKID...` | Use `AskUserQuestion` or read from a user-provided file path. Never log. |
| Tencent Cloud SecretKey | `...` | Same as above. Treat as secret. |
| CVM region | `ap-hongkong` | Region where the CVM lives. |
| CVM instance ID | `ins-xxxxxxxx` | The box running the backend container. |
| Container name | `monitor-server-monitor-server-1` | Container that has the MySQL DSN in its env and `aiomysql` installed. |
| Env var name holding the DSN | `SQL__MYSQL_CONNECT` | Default. The script auto-detects common alternatives. |
| Time window (BJT) | `2026-05-14 16:00` → `2026-05-14 17:00` | Beijing time, half-open `[start, end)`. |
| NewAPI username filter | `askmanyai` | Filters `logs.username`. Required — leave empty only with explicit user OK. |
| Models | `gpt-5.5=gpt-5.5, opus-4.7=claude-opus-4-7, gemini-3.1-pro=gemini-3.1-pro-preview` | `label=real_model_name` pairs. Comma-separated. The label is for display; the real name is what gets matched in MySQL. |

If the user gives only friendly model labels (e.g. `opus-4.7`), first list candidate real model names from the DB (see *Probing* below), then confirm with the user before running the final query.

## Workflow

1. **Ask the user for TAT credentials.** Required even if the session previously used them. Accept either:
   - direct paste of SecretId/SecretKey, or
   - a path to a CSV/XLSX file the user trusts (use Read/openpyxl to parse).
2. **Ask the user for target & query parameters.** Pre-fill obvious defaults (yesterday's afternoon, `askmanyai`) only with the user's confirmation.
3. **Set credentials as env vars** for the local `tccli` calls — never write to `~/.tccli` or any persistent file:
   ```bash
   export TENCENTCLOUD_SECRET_ID=...
   export TENCENTCLOUD_SECRET_KEY=...
   ```
4. **Probing** (optional but recommended when models or username are uncertain): run a small probe inside the container to discover real `model_name` strings:
   ```bash
   python3 scripts/tat_run.py \
     --region <REGION> --instance-id <INSTANCE_ID> \
     --command "docker exec <CONTAINER> python -c 'import os; print(os.environ.get(\"SQL__MYSQL_CONNECT\",\"\")[:8])'"
   ```
   Then use the script's `--probe` mode (see `scripts/query_newapi_tpm_rpm.py --help`) to list top usernames and matching model names for the window.
5. **Run the main query** by uploading the remote script via TAT, executing it inside the container, and capturing JSON output:
   ```bash
   python3 scripts/tat_run.py \
     --region <REGION> --instance-id <INSTANCE_ID> \
     --container <CONTAINER> \
     --remote-script scripts/query_newapi_tpm_rpm.py \
     --remote-args '--start "2026-05-14 16:00" --end "2026-05-14 17:00" \
                    --username askmanyai \
                    --models "gpt-5.5=gpt-5.5,opus-4.7=claude-opus-4-7,gemini-3.1-pro=gemini-3.1-pro-preview" \
                    --format json'
   ```
6. **Render the result** as a Markdown table showing label, real model name, request count, total tokens, RPM, TPM, peak-minute TPM, peak-minute RPM, and avg tokens/request.
7. **Clean up.** Unset the env vars at the end of the session if you exported them in a long-lived shell.

## Output shape

The remote script emits JSON (with `--format json`) of this form so the agent can format consistently:

```json
{
  "window": {"start_bjt": "...", "end_bjt": "...", "start_ts": 0, "end_ts": 0, "minutes": 60.0},
  "username": "askmanyai",
  "rows": [
    {
      "label": "gpt-5.5",
      "model_name": "gpt-5.5",
      "request_count": 459,
      "prompt_tokens": 2764956,
      "completion_tokens": 1537564,
      "total_tokens": 4302520,
      "rpm_avg": 7.65, "tpm_avg": 71708.7, "avg_tokens_per_req": 9373.7,
      "peak_minute_by_tokens": {"minute_offset": 41, "requests": 12, "tokens": 226644},
      "peak_minute_by_requests": {"minute_offset": 23, "requests": 14, "tokens": 146468}
    }
  ]
}
```

The text format (default) prints a fixed-width table — useful when the agent wants to forward stdout verbatim.

## Sizing guidance

When the goal is rate-limit sizing, the **peak minute** values matter more than the hour average. A common rule of thumb: provision **peak TPM × 1.5–2** and **peak RPM × 1.5–2** as the upstream quota. Hour averages typically undershoot real bursts by 3–10×.

## Why TAT?

NewAPI's MySQL is on a private Tencent CDB endpoint that's only reachable from the VPC. TAT lets the agent run commands on the CVM without opening a public DB port, exporting credentials to the laptop, or persisting them in `tccli`'s config. The DSN stays inside the container.

## Failure modes to watch

- **Wrong env var.** Some deploys use a different name than `SQL__MYSQL_CONNECT`; pass `--env-var <NAME>` to the remote script.
- **Wrong container.** `docker ps` on the CVM to verify the container name before running. Multiple environments (dev/test/stable) may coexist.
- **Model name doesn't exist for that window.** The probe returns zero rows; surface this to the user instead of returning 0 RPM as "real data".
- **Time zone confusion.** All `--start`/`--end` inputs are interpreted as Beijing time (UTC+8). `logs.created_at` is a Unix timestamp.
- **TAT timeout.** Default is 600s. For windows larger than ~24h on a busy table, partition the window or add `LIMIT`-style sampling.
