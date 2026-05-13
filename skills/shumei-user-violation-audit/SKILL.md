---
name: shumei-user-violation-audit
description: Automate Shumei-based user violation-rate audits from MongoDB user and conversation collections, producing a CSV sorted by per-user request violation rate. Use when asked to screen users for forbidden/risky content, compute user-level violation rates, audit newly registered/free/suspicious users, or rerun a similar report with custom user filters, conversation filters, and a Shumei input-event key.
---

# Shumei User Violation Audit

Use this skill to turn a user cohort plus conversation-selection rule into a per-user CSV:
`用户 -> conversation.query -> Shumei input event -> 违禁请求数 / 检测成功请求数`.

## Required Inputs

Before running, identify these values from the user or local context:

- User filter: Mongo query for the `user` collection.
- Conversation filter: Mongo query template for the `conversation` collection.
- Shumei key: `accessKey` for the text risk service.
- Mongo access: either direct `mongo_uri + mongo_db`, or an app/container environment that already has Mongo access.
- Output path: default to the current workspace with a timestamped CSV when not specified.

Do not hardcode the Shumei key in the skill. Treat it as run input.

## Script

Use the bundled script:

```bash
python3 scripts/audit_user_violation_rate.py --config config.json
```

Print an editable config template:

```bash
python3 scripts/audit_user_violation_rate.py --print-example-config
```

The script is read-only for MongoDB. It writes a UTF-8-BOM CSV and a `.gz` copy unless `--no-gzip` is passed.

## Filter Templates

The script accepts valid JSON. Template placeholders are resolved before querying:

- `{{now}}`
- `{{now - 2592000}}`
- `{{username}}`
- `{{register_time}}`
- `{{register_time + 86400}}`
- `{{user.some_nested_field}}`

Default conversation template matches the prior AMA audit:

```json
{
  "user": "{{username}}",
  "request_time": {
    "$gte": "{{register_time}}",
    "$lt": "{{register_time + 86400}}"
  },
  "query": { "$exists": true, "$ne": "" }
}
```

Example still-free users registered in the past 30 days:

```json
{
  "register_time": { "$gte": "{{now - 2592000}}", "$lt": "{{now}}" },
  "$and": [
    {
      "$or": [
        { "pay_history": { "$exists": false } },
        { "pay_history": [] },
        { "pay_history": null }
      ]
    },
    {
      "$or": [
        { "vip_expire_time": { "$exists": false } },
        { "vip_expire_time": { "$lte": "{{now}}" } },
        { "vip_expire_time": -1 }
      ]
    }
  ]
}
```

## Workflow

1. Convert the user's cohort requirement into `user_filter`.
2. Convert the conversation requirement into `conversation_filter_template`; include `query: {"$exists": true, "$ne": ""}` unless the user explicitly wants empty queries included.
3. Create a temporary config JSON outside the skill directory, usually in the workspace.
4. Run the script where Mongo is reachable.
5. Verify the final `RESULT_JSON_START` summary: row count, request count, violation count, and failed checks.
6. Return the CSV path and summarize the key counts.

If the target MongoDB is only reachable from a server/container, copy or mount the script there and run it inside that environment. For very large CSVs over TAT/stdout, prefer leaving the report file on the server or transferring a compressed `.csv.gz`; avoid printing CSV contents to stdout.

## Output Semantics

The default violation rule follows the existing product behavior:

```text
code == 1100 and riskLevel != PASS
```

CSV rows are sorted by:

1. `请求违禁率` descending
2. `违禁请求数` descending
3. `对话请求数` descending

Default columns include user identity fields, request counts, Shumei risk labels/descriptions, up to three violating query examples, and first/last selected request times.
