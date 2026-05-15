#!/usr/bin/env python3
"""
Query NewAPI's `logs` table for per-model RPM/TPM over a time window.

Designed to run **inside** the backend container that already holds the NewAPI
MySQL DSN in its environment (default env var: SQL__MYSQL_CONNECT). The DSN is
read from env at runtime and never accepted on the command line, so no DB
credentials cross process boundaries.

Read-only: only SELECT queries are issued against the `logs` and (optionally)
`users` tables.

Examples
--------

    # Probe: list top usernames and matching model names in a window
    python query_newapi_tpm_rpm.py \\
        --start "2026-05-14 16:00" --end "2026-05-14 17:00" \\
        --probe --model-search "gpt-5,opus,gemini-3"

    # Main query: RPM/TPM per model
    python query_newapi_tpm_rpm.py \\
        --start "2026-05-14 16:00" --end "2026-05-14 17:00" \\
        --username askmanyai \\
        --models "gpt-5.5=gpt-5.5,opus-4.7=claude-opus-4-7,gemini-3.1-pro=gemini-3.1-pro-preview" \\
        --format text

All time inputs are interpreted as Beijing time (UTC+8). The window is
half-open: [start, end). `logs.created_at` is a Unix timestamp in seconds.
"""
from __future__ import annotations

import argparse
import asyncio
import calendar
import datetime as dt
import json
import os
import re
import sys
from typing import Any
from urllib.parse import unquote, urlparse


DEFAULT_DSN_ENV_VARS = (
    "SQL__MYSQL_CONNECT",
    "NEWAPI_MYSQL_DSN",
    "MYSQL_DSN",
)
BJT = dt.timezone(dt.timedelta(hours=8))


def _parse_bjt(s: str) -> int:
    """Parse a Beijing-time string into a Unix timestamp (seconds, UTC)."""
    s = s.strip()
    # Accept "YYYY-MM-DD HH:MM[:SS]"
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M")
    for fmt in fmts:
        try:
            naive = dt.datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Could not parse '{s}' as BJT datetime; expected YYYY-MM-DD HH:MM[:SS]")
    return calendar.timegm((naive - dt.timedelta(hours=8)).timetuple())


def _load_dsn(env_var: str | None) -> tuple[dict, str]:
    """Return (connect_kwargs, env_var_used)."""
    candidates = (env_var,) if env_var else DEFAULT_DSN_ENV_VARS
    dsn = None
    used = None
    for name in candidates:
        if not name:
            continue
        v = os.environ.get(name)
        if v:
            dsn = v
            used = name
            break
    if not dsn:
        sys.stderr.write(
            f"ERROR: MySQL DSN env var not set. Tried: {', '.join(c for c in candidates if c)}.\n"
            f"       Set --env-var <NAME> if your container uses a different name.\n"
        )
        sys.exit(2)

    # Accept mysql://, mysql+pymysql://, mysql+aiomysql://, plain "user:pass@host:port/db"
    cleaned = dsn
    for prefix in ("mysql+aiomysql://", "mysql+pymysql://", "mysql://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Synthesise a scheme so urlparse cooperates
    parsed = urlparse("mysql://" + cleaned)
    if not (parsed.hostname and parsed.username and parsed.path):
        sys.stderr.write(f"ERROR: could not parse DSN from {used} (got hostname/user/path missing).\n")
        sys.exit(2)

    db = parsed.path.lstrip("/")
    kwargs = {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": parsed.username,
        "password": unquote(parsed.password) if parsed.password else "",
        "db": db,
        "autocommit": True,
        "charset": "utf8mb4",
    }
    return kwargs, used


async def _open(env_var: str | None):
    try:
        import aiomysql
    except ImportError:
        sys.stderr.write("ERROR: aiomysql not installed in this container.\n")
        sys.exit(2)
    kwargs, used = _load_dsn(env_var)
    conn = await aiomysql.connect(**kwargs)
    return conn, used


def _parse_models(spec: str) -> list[tuple[str, str]]:
    """Parse 'label1=name1,label2=name2' into [(label, real_name), ...]."""
    out: list[tuple[str, str]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            label, name = chunk.split("=", 1)
            label = label.strip()
            name = name.strip()
        else:
            label = name = chunk
        if not name:
            continue
        out.append((label, name))
    return out


def _parse_search_terms(spec: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,;\s]+", spec) if t.strip()]


async def cmd_probe(args, conn) -> dict:
    async with conn.cursor() as cur:
        result: dict[str, Any] = {"window": {"start_ts": args._start_ts, "end_ts": args._end_ts}}

        await cur.execute(
            """
            SELECT username, COUNT(*) c
            FROM logs
            WHERE type = 2 AND created_at >= %s AND created_at < %s
            GROUP BY username
            ORDER BY c DESC
            LIMIT %s
            """,
            (args._start_ts, args._end_ts, args.probe_top),
        )
        result["top_usernames"] = [{"username": u, "requests": c} for (u, c) in await cur.fetchall()]

        await cur.execute(
            """
            SELECT token_name, COUNT(*) c
            FROM logs
            WHERE type = 2 AND created_at >= %s AND created_at < %s
            GROUP BY token_name
            ORDER BY c DESC
            LIMIT %s
            """,
            (args._start_ts, args._end_ts, args.probe_top),
        )
        result["top_token_names"] = [{"token_name": t, "requests": c} for (t, c) in await cur.fetchall()]

        if args.model_search:
            terms = _parse_search_terms(args.model_search)
            like_clauses = " OR ".join(["model_name LIKE %s"] * len(terms))
            params: list = [args._start_ts, args._end_ts]
            if args.username:
                params.append(args.username)
            params.extend([f"%{t}%" for t in terms])
            user_filter = "AND username = %s" if args.username else ""
            sql = f"""
                SELECT model_name, COUNT(*) c
                FROM logs
                WHERE type = 2 AND created_at >= %s AND created_at < %s
                  {user_filter}
                  AND ({like_clauses})
                GROUP BY model_name
                ORDER BY c DESC
                LIMIT %s
            """
            params.append(args.probe_top)
            await cur.execute(sql, params)
            result["candidate_models"] = [{"model_name": m, "requests": c} for (m, c) in await cur.fetchall()]

    return result


async def cmd_query(args, conn) -> dict:
    pairs = _parse_models(args.models)
    if not pairs:
        sys.stderr.write("ERROR: --models is empty; nothing to query.\n")
        sys.exit(2)
    if not args.username:
        sys.stderr.write("ERROR: --username is required for main query; pass empty string with --allow-no-username if intentional.\n")
        sys.exit(2)

    window_minutes = (args._end_ts - args._start_ts) / 60.0
    rows = []
    async with conn.cursor() as cur:
        for label, real in pairs:
            await cur.execute(
                """
                SELECT COUNT(*) c,
                       COALESCE(SUM(prompt_tokens), 0) p,
                       COALESCE(SUM(completion_tokens), 0) co,
                       COALESCE(SUM(prompt_tokens + completion_tokens), 0) tot
                FROM logs
                WHERE type = 2
                  AND username = %s
                  AND model_name = %s
                  AND created_at >= %s AND created_at < %s
                """,
                (args.username, real, args._start_ts, args._end_ts),
            )
            c, p, co, tot = await cur.fetchone()
            c = int(c or 0)
            p = int(p or 0)
            co = int(co or 0)
            tot = int(tot or 0)
            rpm_avg = c / window_minutes if window_minutes else 0.0
            tpm_avg = tot / window_minutes if window_minutes else 0.0
            avg_tokens_per_req = (tot / c) if c else 0.0

            peak_tokens = None
            peak_reqs = None
            if c > 0:
                await cur.execute(
                    """
                    SELECT FLOOR((created_at - %s) / 60) m,
                           COUNT(*) c,
                           COALESCE(SUM(prompt_tokens + completion_tokens), 0) t
                    FROM logs
                    WHERE type = 2 AND username = %s AND model_name = %s
                      AND created_at >= %s AND created_at < %s
                    GROUP BY m
                    ORDER BY t DESC
                    LIMIT 1
                    """,
                    (args._start_ts, args.username, real, args._start_ts, args._end_ts),
                )
                r = await cur.fetchone()
                if r:
                    peak_tokens = {"minute_offset": int(r[0]), "requests": int(r[1]), "tokens": int(r[2])}

                await cur.execute(
                    """
                    SELECT FLOOR((created_at - %s) / 60) m,
                           COUNT(*) c,
                           COALESCE(SUM(prompt_tokens + completion_tokens), 0) t
                    FROM logs
                    WHERE type = 2 AND username = %s AND model_name = %s
                      AND created_at >= %s AND created_at < %s
                    GROUP BY m
                    ORDER BY c DESC
                    LIMIT 1
                    """,
                    (args._start_ts, args.username, real, args._start_ts, args._end_ts),
                )
                r = await cur.fetchone()
                if r:
                    peak_reqs = {"minute_offset": int(r[0]), "requests": int(r[1]), "tokens": int(r[2])}

            rows.append({
                "label": label,
                "model_name": real,
                "request_count": c,
                "prompt_tokens": p,
                "completion_tokens": co,
                "total_tokens": tot,
                "rpm_avg": round(rpm_avg, 2),
                "tpm_avg": round(tpm_avg, 1),
                "avg_tokens_per_req": round(avg_tokens_per_req, 1),
                "peak_minute_by_tokens": peak_tokens,
                "peak_minute_by_requests": peak_reqs,
            })

    return {
        "window": {
            "start_bjt": dt.datetime.fromtimestamp(args._start_ts, BJT).strftime("%Y-%m-%d %H:%M:%S"),
            "end_bjt": dt.datetime.fromtimestamp(args._end_ts, BJT).strftime("%Y-%m-%d %H:%M:%S"),
            "start_ts": args._start_ts,
            "end_ts": args._end_ts,
            "minutes": window_minutes,
        },
        "username": args.username,
        "rows": rows,
    }


def _format_text(payload: dict) -> str:
    out_lines: list[str] = []
    w = payload["window"]
    out_lines.append(
        f"Window: {w.get('start_bjt', w['start_ts'])} .. {w.get('end_bjt', w['end_ts'])} BJT "
        f"(ts=[{w['start_ts']},{w['end_ts']}))  minutes={w['minutes']}"
    )
    if "username" in payload:
        out_lines.append(f"username = {payload['username']}")
    out_lines.append("")

    if "rows" in payload:
        header = (
            f"{'label':18} {'real_model':32} {'reqs':>7} {'prompt':>12} {'compl':>12} "
            f"{'tokens':>13} {'RPM':>8} {'TPM':>12} {'avg/req':>10}"
        )
        out_lines.append(header)
        for r in payload["rows"]:
            out_lines.append(
                f"{r['label']:18} {r['model_name']:32} {r['request_count']:>7} "
                f"{r['prompt_tokens']:>12} {r['completion_tokens']:>12} {r['total_tokens']:>13} "
                f"{r['rpm_avg']:>8.2f} {r['tpm_avg']:>12.1f} {r['avg_tokens_per_req']:>10.1f}"
            )
        out_lines.append("")
        out_lines.append("Peak minute (by tokens):")
        for r in payload["rows"]:
            pk = r.get("peak_minute_by_tokens")
            if pk:
                out_lines.append(
                    f"  {r['label']:18} +{pk['minute_offset']:>2}min  "
                    f"reqs={pk['requests']:>4}  tokens={pk['tokens']:>8}  (peak TPM)"
                )
            else:
                out_lines.append(f"  {r['label']:18} (no data)")
        out_lines.append("")
        out_lines.append("Peak minute (by requests):")
        for r in payload["rows"]:
            pk = r.get("peak_minute_by_requests")
            if pk:
                out_lines.append(
                    f"  {r['label']:18} +{pk['minute_offset']:>2}min  "
                    f"reqs={pk['requests']:>4}  tokens={pk['tokens']:>8}  (peak RPM)"
                )
            else:
                out_lines.append(f"  {r['label']:18} (no data)")

    if "top_usernames" in payload:
        out_lines.append("Top usernames in window:")
        for r in payload["top_usernames"]:
            out_lines.append(f"  {r['username']:24}  {r['requests']:>8}")
    if "top_token_names" in payload:
        out_lines.append("")
        out_lines.append("Top token_names in window:")
        for r in payload["top_token_names"]:
            out_lines.append(f"  {r['token_name']:24}  {r['requests']:>8}")
    if "candidate_models" in payload:
        out_lines.append("")
        out_lines.append("Candidate model_names matching search:")
        for r in payload["candidate_models"]:
            out_lines.append(f"  {r['model_name']:36}  {r['requests']:>8}")

    return "\n".join(out_lines) + "\n"


async def amain(args) -> None:
    args._start_ts = _parse_bjt(args.start)
    args._end_ts = _parse_bjt(args.end)
    if args._end_ts <= args._start_ts:
        sys.stderr.write("ERROR: --end must be strictly greater than --start.\n")
        sys.exit(2)

    conn, env_used = await _open(args.env_var)
    try:
        if args.probe:
            payload = await cmd_probe(args, conn)
        else:
            payload = await cmd_query(args, conn)
        payload["_env_var_used"] = env_used
    finally:
        conn.close()

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_text(payload), end="")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--start", required=True, help='BJT start, e.g. "2026-05-14 16:00"')
    p.add_argument("--end", required=True, help='BJT end (exclusive), e.g. "2026-05-14 17:00"')
    p.add_argument("--username", default="", help="NewAPI username filter (logs.username). Required for main query.")
    p.add_argument(
        "--models",
        default="",
        help='Comma-separated label=real pairs, e.g. "gpt-5.5=gpt-5.5,opus-4.7=claude-opus-4-7"',
    )
    p.add_argument("--env-var", default=None, help="Env var name that holds the MySQL DSN (default: try common names)")
    p.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    p.add_argument("--probe", action="store_true", help="Probe mode: list top usernames, token_names, candidate model names")
    p.add_argument(
        "--model-search",
        default="",
        help="In probe mode, comma- or space-separated substrings to LIKE-match against model_name",
    )
    p.add_argument("--probe-top", type=int, default=30, help="Top N rows per probe list (default 30)")
    p.add_argument("--allow-no-username", action="store_true", help="Allow empty username in main query (off by default)")

    args = p.parse_args()
    if args.allow_no_username and not args.username:
        args.username = ""
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
