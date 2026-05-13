#!/usr/bin/env python3
"""Compute per-user Shumei violation rates from MongoDB conversations.

The script is read-only for MongoDB and only writes local CSV/gzip output.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import httpx
from pymongo import MongoClient


DEFAULT_SHUMEI_URL = "http://api-text-xjp.fengkongcloud.com/text/v4"
DEFAULT_CONVERSATION_FILTER = {
    "user": "{{username}}",
    "request_time": {
        "$gte": "{{register_time}}",
        "$lt": "{{register_time + 86400}}",
    },
    "query": {"$exists": True, "$ne": ""},
}
DEFAULT_USER_PROJECTION = {
    "_id": 0,
    "username": 1,
    "register_time": 1,
    "register_ip": 1,
    "banned_info": 1,
    "account_type": 1,
    "vip_expire_time": 1,
    "remain_requests": 1,
    "remain_free_battery": 1,
    "remain_vip_battery": 1,
    "remain_extend_battery": 1,
}
DEFAULT_ROW_FIELDS = [
    ("用户标识", "username", "raw"),
    ("注册时间", "register_time", "time"),
    ("注册IP", "register_ip", "raw"),
    ("当前封禁信息", "banned_info", "raw"),
    ("账号类型", "account_type", "raw"),
    ("VIP到期时间", "vip_expire_time", "time"),
    ("剩余总电池", "remain_requests", "raw"),
    ("剩余免费电池", "remain_free_battery", "raw"),
    ("剩余VIP电池", "remain_vip_battery", "raw"),
    ("剩余扩展电池", "remain_extend_battery", "raw"),
]
DEFAULT_CONFIG = {
    "mongo_uri": "",
    "mongo_db": "",
    "user_collection": "user",
    "conversation_collection": "conversation",
    "user_filter": {
        "register_time": {"$gte": "{{now - 2592000}}", "$lt": "{{now}}"},
        "$and": [
            {
                "$or": [
                    {"pay_history": {"$exists": False}},
                    {"pay_history": []},
                    {"pay_history": None},
                ]
            },
            {
                "$or": [
                    {"vip_expire_time": {"$exists": False}},
                    {"vip_expire_time": {"$lte": "{{now}}"}},
                    {"vip_expire_time": -1},
                ]
            },
        ],
    },
    "user_projection": DEFAULT_USER_PROJECTION,
    "conversation_filter_template": DEFAULT_CONVERSATION_FILTER,
    "query_field": "query",
    "shumei_key": "REPLACE_ME",
    "shumei_url": DEFAULT_SHUMEI_URL,
    "app_id": "default",
    "event_id": "input",
    "event_type": "TEXTRISK",
    "concurrency": 25,
    "output_csv": "./user_violation_rate.csv",
    "include_zero_query_users": True,
    "max_text_length": 2000,
    "example_limit_per_user": 3,
    "example_text_limit": 160,
}


class ConfigError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit MongoDB conversation queries with Shumei and output per-user violation rates."
    )
    parser.add_argument("--config", help="Path to JSON config.")
    parser.add_argument("--print-example-config", action="store_true")
    parser.add_argument("--mongo-uri", help="Override config.mongo_uri.")
    parser.add_argument("--mongo-db", help="Override config.mongo_db.")
    parser.add_argument("--user-filter-json", help="Override config.user_filter with valid JSON.")
    parser.add_argument(
        "--conversation-filter-json",
        help="Override config.conversation_filter_template with valid JSON.",
    )
    parser.add_argument("--shumei-key", help="Override config.shumei_key.")
    parser.add_argument("--output-csv", help="Override config.output_csv.")
    parser.add_argument("--concurrency", type=int, help="Override config.concurrency.")
    parser.add_argument("--no-gzip", action="store_true", help="Do not write .gz copy.")
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> Dict[str, Any]:
    if args.print_example_config:
        print(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    config: Dict[str, Any] = {}
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)

    for key, value in {
        "mongo_uri": args.mongo_uri,
        "mongo_db": args.mongo_db,
        "shumei_key": args.shumei_key,
        "output_csv": args.output_csv,
        "concurrency": args.concurrency,
    }.items():
        if value is not None:
            config[key] = value

    if args.user_filter_json:
        config["user_filter"] = json.loads(args.user_filter_json)
    if args.conversation_filter_json:
        config["conversation_filter_template"] = json.loads(args.conversation_filter_json)

    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    if not merged.get("mongo_uri"):
        raise ConfigError("mongo_uri is required.")
    if not merged.get("mongo_db"):
        raise ConfigError("mongo_db is required.")
    if not merged.get("shumei_key") or merged["shumei_key"] == "REPLACE_ME":
        raise ConfigError("shumei_key is required.")
    return merged


def get_path(obj: Dict[str, Any], path: str) -> Any:
    if path.startswith("user."):
        path = path[5:]
    current: Any = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


MACRO_RE = re.compile(
    r"^\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)(?:\s*([+-])\s*(-?\d+(?:\.\d+)?))?\s*\}\}$"
)
INLINE_MACRO_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)(?:\s*([+-])\s*(-?\d+(?:\.\d+)?))?\s*\}\}")


def resolve_macro_value(expr: str, user: Dict[str, Any], now: float) -> Any:
    match = MACRO_RE.match(expr)
    if not match:
        return INLINE_MACRO_RE.sub(lambda m: str(resolve_match(m, user, now) or ""), expr)
    return resolve_match(match, user, now)


def resolve_match(match: re.Match[str], user: Dict[str, Any], now: float) -> Any:
    name, op, delta = match.groups()
    value = now if name == "now" else get_path(user, name)
    if op and delta is not None:
        try:
            value = float(value or 0)
            amount = float(delta)
            value = value + amount if op == "+" else value - amount
        except Exception:
            value = None
    return value


def resolve_template(value: Any, user: Dict[str, Any], now: float) -> Any:
    if isinstance(value, str):
        return resolve_macro_value(value, user, now)
    if isinstance(value, list):
        return [resolve_template(v, user, now) for v in value]
    if isinstance(value, dict):
        return {k: resolve_template(v, user, now) for k, v in value.items()}
    return value


def format_time(value: Any, tz: timezone) -> str:
    try:
        ts = float(value)
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def normalize_text(text: str, max_length: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) > max_length:
        half = max_length // 2
        cleaned = cleaned[:half] + cleaned[-half:]
    return cleaned


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_cell(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


async def check_shumei(
    client: httpx.AsyncClient,
    *,
    url: str,
    key: str,
    app_id: str,
    event_id: str,
    event_type: str,
    text: str,
    token_id: str,
) -> Tuple[bool, Dict[str, Any]]:
    body = {
        "accessKey": key,
        "appId": app_id,
        "eventId": event_id,
        "type": event_type,
        "data": {
            "text": text,
            "tokenId": hashlib.md5(token_id.encode("utf-8")).hexdigest(),
        },
    }
    last_error = ""
    for attempt in range(3):
        try:
            response = await client.post(url, json=body, timeout=30)
            payload = response.json()
            violation = payload.get("code") == 1100 and payload.get("riskLevel", "PASS") != "PASS"
            return True, {
                "violation": violation,
                "code": payload.get("code"),
                "risk_level": payload.get("riskLevel", "PASS"),
                "risk_label1": payload.get("riskLabel1", ""),
                "risk_label2": payload.get("riskLabel2", ""),
                "risk_label3": payload.get("riskLabel3", ""),
                "risk_description": payload.get("riskDescription", ""),
                "request_id": payload.get("requestId", ""),
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(0.4 * (attempt + 1))
    return False, {
        "violation": False,
        "risk_level": "ERROR",
        "risk_label1": "error",
        "risk_label2": "",
        "risk_label3": "",
        "risk_description": last_error,
        "request_id": "",
    }


async def run_shumei_checks(
    config: Dict[str, Any],
    hash_to_text: Dict[str, str],
    hash_to_token: Dict[str, str],
) -> Dict[str, Dict[str, Any]]:
    concurrency = max(int(config.get("concurrency", 25)), 1)
    semaphore = asyncio.Semaphore(concurrency)
    results: Dict[str, Dict[str, Any]] = {}
    started_at = time.time()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(40, connect=10),
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
        trust_env=False,
    ) as client:

        async def run_one(item: Tuple[str, str]) -> Tuple[str, Dict[str, Any]]:
            h, text = item
            async with semaphore:
                ok, result = await check_shumei(
                    client,
                    url=config["shumei_url"],
                    key=config["shumei_key"],
                    app_id=config.get("app_id", "default"),
                    event_id=config.get("event_id", "input"),
                    event_type=config.get("event_type", "TEXTRISK"),
                    text=text,
                    token_id=hash_to_token.get(h, h),
                )
                result["error"] = not ok
                return h, result

        tasks = [asyncio.create_task(run_one(item)) for item in hash_to_text.items()]
        total = len(tasks)
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            h, result = await task
            results[h] = result
            if i % 5000 == 0 or i == total:
                elapsed = max(time.time() - started_at, 0.001)
                print(
                    json.dumps(
                        {
                            "phase": "shumei",
                            "checked_unique": i,
                            "total_unique": total,
                            "violating_unique": sum(1 for r in results.values() if r.get("violation")),
                            "error_unique": sum(1 for r in results.values() if r.get("error")),
                            "qps": round(i / elapsed, 2),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    return results


def collect_rows(config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, str]]:
    client = MongoClient(config["mongo_uri"])
    db = client[config["mongo_db"]]
    user_collection = db[config.get("user_collection", "user")]
    conv_collection = db[config.get("conversation_collection", "conversation")]

    now = time.time()
    user_filter = resolve_template(config["user_filter"], {}, now)
    user_projection = config.get("user_projection") or DEFAULT_USER_PROJECTION
    conv_template = config.get("conversation_filter_template") or DEFAULT_CONVERSATION_FILTER
    query_field = config.get("query_field", "query")
    max_text_length = int(config.get("max_text_length", 2000))

    rows: List[Dict[str, Any]] = []
    hash_to_text: Dict[str, str] = {}
    hash_to_token: Dict[str, str] = {}

    cursor = user_collection.find(user_filter, user_projection).sort(config.get("user_sort") or [("register_time", 1)])
    for idx, user in enumerate(cursor, 1):
        conv_filter = resolve_template(conv_template, user, now)
        conv_projection = {"_id": 0, query_field: 1, "request_time": 1}
        query_hashes: List[str] = []
        first_query_time = 0.0
        last_query_time = 0.0

        for conv in conv_collection.find(conv_filter, conv_projection).sort("request_time", 1):
            query = normalize_text(str(conv.get(query_field, "") or ""), max_text_length)
            if not query:
                continue
            h = text_hash(query)
            query_hashes.append(h)
            hash_to_text.setdefault(h, query)
            hash_to_token.setdefault(h, str(user.get("username") or user.get("user") or h))
            request_time = float(conv.get("request_time") or 0)
            if request_time and not first_query_time:
                first_query_time = request_time
            if request_time:
                last_query_time = request_time

        row = {
            "user": user,
            "query_hashes": query_hashes,
            "first_query_time": first_query_time,
            "last_query_time": last_query_time,
        }
        if query_hashes or config.get("include_zero_query_users", True):
            rows.append(row)

        if idx % 10000 == 0:
            print(
                json.dumps(
                    {
                        "phase": "collect",
                        "users_seen": idx,
                        "rows_kept": len(rows),
                        "query_refs": sum(len(r["query_hashes"]) for r in rows),
                        "unique_queries": len(hash_to_text),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    print(
        json.dumps(
            {
                "phase": "collect_done",
                "rows": len(rows),
                "query_refs": sum(len(r["query_hashes"]) for r in rows),
                "unique_queries": len(hash_to_text),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return rows, hash_to_text, hash_to_token


def build_csv_rows(
    config: Dict[str, Any],
    rows: List[Dict[str, Any]],
    hash_to_text: Dict[str, str],
    results: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    tz = timezone(timedelta(hours=int(config.get("timezone_hours", 8))))
    row_fields = config.get("row_fields") or DEFAULT_ROW_FIELDS
    example_limit = int(config.get("example_limit_per_user", 3))
    example_text_limit = int(config.get("example_text_limit", 160))
    csv_rows: List[Dict[str, Any]] = []

    for row in rows:
        user = row["user"]
        query_hashes = row["query_hashes"]
        total = len(query_hashes)
        violation_count = 0
        error_count = 0
        levels: Counter[str] = Counter()
        labels: Counter[str] = Counter()
        descriptions: Counter[str] = Counter()
        examples: List[str] = []

        for h in query_hashes:
            result = results.get(h, {"error": True, "risk_description": "missing_result"})
            if result.get("error"):
                error_count += 1
                continue
            if result.get("violation"):
                violation_count += 1
                levels[result.get("risk_level") or ""] += 1
                label = "/".join(
                    x
                    for x in [
                        result.get("risk_label1"),
                        result.get("risk_label2"),
                        result.get("risk_label3"),
                    ]
                    if x
                )
                labels[label or result.get("risk_level") or "unknown"] += 1
                descriptions[result.get("risk_description") or ""] += 1
                if len(examples) < example_limit:
                    examples.append(safe_cell(hash_to_text.get(h, ""), example_text_limit))

        checked = total - error_count
        rate = violation_count / checked if checked else 0.0
        csv_row: Dict[str, Any] = {}
        for header, field, mode in row_fields:
            value = get_path(user, field)
            csv_row[header] = format_time(value, tz) if mode == "time" else value
        csv_row.update(
            {
                "对话请求数": total,
                "检测成功请求数": checked,
                "检测失败请求数": error_count,
                "违禁请求数": violation_count,
                "请求违禁率": f"{rate:.6f}",
                "风险级别": ";".join(f"{k}:{v}" for k, v in levels.most_common(5)),
                "风险标签": ";".join(f"{k}:{v}" for k, v in labels.most_common(5)),
                "风险说明": ";".join(f"{k}:{v}" for k, v in descriptions.most_common(5)),
                "违禁query样例": " || ".join(examples),
                "首次请求时间": format_time(row["first_query_time"], tz),
                "最后请求时间": format_time(row["last_query_time"], tz),
            }
        )
        csv_rows.append(csv_row)

    csv_rows.sort(
        key=lambda r: (
            float(r.get("请求违禁率") or 0),
            int(r.get("违禁请求数") or 0),
            int(r.get("对话请求数") or 0),
        ),
        reverse=True,
    )
    return csv_rows


def write_outputs(config: Dict[str, Any], csv_rows: List[Dict[str, Any]], no_gzip: bool) -> Dict[str, Any]:
    output_csv = Path(config["output_csv"]).expanduser().resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(csv_rows[0].keys()) if csv_rows else []
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    output_gz = None
    if not no_gzip:
        output_gz = Path(str(output_csv) + ".gz")
        with open(output_csv, "rb") as src, gzip.open(output_gz, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)

    summary = {
        "output_csv": str(output_csv),
        "output_gz": str(output_gz) if output_gz else "",
        "rows": len(csv_rows),
        "users_with_violation": sum(1 for r in csv_rows if int(r.get("违禁请求数") or 0) > 0),
        "total_requests": sum(int(r.get("对话请求数") or 0) for r in csv_rows),
        "total_violation_requests": sum(int(r.get("违禁请求数") or 0) for r in csv_rows),
        "total_failed_checks": sum(int(r.get("检测失败请求数") or 0) for r in csv_rows),
        "csv_bytes": output_csv.stat().st_size,
        "gz_bytes": output_gz.stat().st_size if output_gz else 0,
    }
    print("RESULT_JSON_START")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


async def async_main() -> None:
    args = parse_args()
    config = load_config(args)
    rows, hash_to_text, hash_to_token = collect_rows(config)
    results = await run_shumei_checks(config, hash_to_text, hash_to_token)
    csv_rows = build_csv_rows(config, rows, hash_to_text, results)
    write_outputs(config, csv_rows, args.no_gzip)


def main() -> None:
    try:
        asyncio.run(async_main())
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
