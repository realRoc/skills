#!/usr/bin/env python3
"""
Batch-geolocate IPv4/IPv6 addresses via ip-api.com and print a Markdown
distribution table (Chinese provinces + foreign countries) with counts and
percentages. Optionally writes CSV and raw JSON sidecar files.

Free tier: max 15 batches × 100 IPs per minute (~1500 IPs/min). No API key.

Usage:
    python3 lookup_ips.py --file ips.txt
    python3 lookup_ips.py --ips "1.2.3.4,5.6.7.8"
    cat ips.txt | python3 lookup_ips.py --stdin
    python3 lookup_ips.py --file ips.json --csv out.csv --raw raw.json
"""
import argparse
import csv
import ipaddress
import json
import re
import sys
import time
import urllib.request
from collections import Counter

API_URL = "http://ip-api.com/batch?fields=status,country,countryCode,regionName,query"
BATCH_SIZE = 100
PER_BATCH_SLEEP = 4.5  # 60 / 13 ≈ 4.6 — under the 15 req/min cap
MAX_RETRIES = 3

CN_REGION_MAP = {
    "Beijing": "北京", "Tianjin": "天津", "Shanghai": "上海", "Chongqing": "重庆",
    "Hebei": "河北", "Shanxi": "山西", "Inner Mongolia": "内蒙古",
    "Liaoning": "辽宁", "Jilin": "吉林", "Heilongjiang": "黑龙江",
    "Jiangsu": "江苏", "Zhejiang": "浙江", "Anhui": "安徽", "Fujian": "福建",
    "Jiangxi": "江西", "Shandong": "山东", "Henan": "河南", "Hubei": "湖北",
    "Hunan": "湖南", "Guangdong": "广东", "Guangxi": "广西", "Hainan": "海南",
    "Sichuan": "四川", "Guizhou": "贵州", "Yunnan": "云南", "Tibet": "西藏",
    "Shaanxi": "陕西", "Gansu": "甘肃", "Qinghai": "青海", "Ningxia": "宁夏",
    "Xinjiang": "新疆",
    "Hong Kong": "香港", "Macau": "澳门", "Macao": "澳门", "Taiwan": "台湾",
}

COUNTRY_CN = {
    "United States": "美国", "Japan": "日本", "Singapore": "新加坡",
    "South Korea": "韩国", "Korea": "韩国", "Republic of Korea": "韩国",
    "United Kingdom": "英国", "Germany": "德国", "France": "法国",
    "Netherlands": "荷兰", "Russia": "俄罗斯", "India": "印度",
    "Canada": "加拿大", "Australia": "澳大利亚", "Brazil": "巴西",
    "Mexico": "墨西哥", "Turkey": "土耳其", "Indonesia": "印度尼西亚",
    "Malaysia": "马来西亚", "Thailand": "泰国", "Vietnam": "越南",
    "Philippines": "菲律宾", "Italy": "意大利", "Spain": "西班牙",
    "Switzerland": "瑞士", "Sweden": "瑞典", "Finland": "芬兰",
    "Norway": "挪威", "Denmark": "丹麦", "Poland": "波兰",
    "Ukraine": "乌克兰", "Iran": "伊朗", "Iraq": "伊拉克",
    "Saudi Arabia": "沙特阿拉伯", "United Arab Emirates": "阿联酋",
    "Israel": "以色列", "Egypt": "埃及", "South Africa": "南非",
    "New Zealand": "新西兰", "Ireland": "爱尔兰", "Belgium": "比利时",
    "Austria": "奥地利", "Czech Republic": "捷克", "Czechia": "捷克",
    "Bulgaria": "保加利亚", "Romania": "罗马尼亚", "Hungary": "匈牙利",
    "Greece": "希腊", "Portugal": "葡萄牙", "Argentina": "阿根廷",
    "Chile": "智利", "Colombia": "哥伦比亚", "Peru": "秘鲁",
    "Myanmar": "缅甸", "Cambodia": "柬埔寨", "Laos": "老挝",
    "Pakistan": "巴基斯坦", "Bangladesh": "孟加拉国", "Sri Lanka": "斯里兰卡",
    "Nepal": "尼泊尔", "Mongolia": "蒙古",
}

IP_TOKEN_RE = re.compile(
    r"\b("
    r"(?:\d{1,3}\.){3}\d{1,3}"          # IPv4
    r"|[0-9a-fA-F:]+:[0-9a-fA-F:]+"      # naive IPv6
    r")\b"
)


def parse_ips_from_text(text: str) -> list[str]:
    """Pull IPv4/IPv6 tokens out of any blob — supports one-per-line, comma-sep, JSON array, or noisy text."""
    text = text.strip()
    if not text:
        return []
    # Try JSON array first
    if text.startswith("["):
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except json.JSONDecodeError:
            pass
    # Otherwise regex-extract
    return IP_TOKEN_RE.findall(text)


def validate_and_dedupe(ips: list[str]) -> tuple[list[str], list[str]]:
    seen, valid, invalid = set(), [], []
    for raw in ips:
        ip = raw.strip()
        if not ip or ip in seen:
            continue
        try:
            ipaddress.ip_address(ip)
            valid.append(ip)
            seen.add(ip)
        except ValueError:
            invalid.append(ip)
    return valid, invalid


def query_batch(batch: list[str]) -> list[dict]:
    body = json.dumps(batch).encode()
    req = urllib.request.Request(
        API_URL, data=body, headers={"Content-Type": "application/json"}
    )
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            # Backoff a bit longer on subsequent retries
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"batch failed after {MAX_RETRIES} retries: {last_err}")


def aggregate(rows: list[dict]) -> tuple[Counter, Counter, list[str]]:
    cn_counter, foreign_counter, failed = Counter(), Counter(), []
    for row in rows:
        ip = row.get("query")
        if row.get("status") != "success":
            failed.append(ip)
            continue
        cc = row.get("countryCode")
        country = row.get("country", "") or ""
        region = row.get("regionName", "") or ""
        if cc == "CN":
            label = CN_REGION_MAP.get(region) or (f"中国-未知({region})" if region else "中国-未知")
            cn_counter[label] += 1
        elif cc == "HK":
            cn_counter["香港"] += 1
        elif cc == "MO":
            cn_counter["澳门"] += 1
        elif cc == "TW":
            cn_counter["台湾"] += 1
        else:
            label = COUNTRY_CN.get(country) or (country if country else f"未知({cc or '?'})")
            foreign_counter[label] += 1
    return cn_counter, foreign_counter, failed


CN_MAINLAND = {
    "北京", "天津", "上海", "重庆", "河北", "山西", "内蒙古", "辽宁", "吉林",
    "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北",
    "湖南", "广东", "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西",
    "甘肃", "青海", "宁夏", "新疆",
}
HK_MO_TW = {"香港", "澳门", "台湾"}


def render_markdown(cn_counter: Counter, foreign_counter: Counter, total: int, failed: list[str]) -> str:
    mainland = sum(v for k, v in cn_counter.items() if k in CN_MAINLAND or k.startswith("中国-未知"))
    hkmotw = sum(v for k, v in cn_counter.items() if k in HK_MO_TW)
    foreign = sum(foreign_counter.values())

    out = []
    out.append("## 总体概览\n")
    out.append("| 区域 | 数量 | 占比 |")
    out.append("|------|------|------|")
    out.append(f"| 中国大陆 | {mainland} | {mainland*100/total:.2f}% |")
    out.append(f"| 港澳台 | {hkmotw} | {hkmotw*100/total:.2f}% |")
    out.append(f"| 海外 | {foreign} | {foreign*100/total:.2f}% |")
    if failed:
        out.append(f"| 查询失败 | {len(failed)} | {len(failed)*100/total:.2f}% |")
    out.append(f"| **合计** | **{total}** | **100.00%** |\n")

    out.append("## 国内（含港澳台，按省份/地区）\n")
    out.append("| 省份/地区 | 数量 | 占比 |")
    out.append("|----------|------|------|")
    for region, n in cn_counter.most_common():
        out.append(f"| {region} | {n} | {n*100/total:.2f}% |")
    out.append("")

    if foreign_counter:
        out.append("## 海外（按国家）\n")
        out.append("| 国家 | 数量 | 占比 |")
        out.append("|------|------|------|")
        for c, n in foreign_counter.most_common():
            out.append(f"| {c} | {n} | {n*100/total:.2f}% |")
        out.append("")

    if failed:
        out.append("## 查询失败 IP（私有地址 / 保留段 / API 暂时不可用）\n")
        for ip in failed:
            out.append(f"- {ip}")

    return "\n".join(out)


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ip", "country_code", "country", "region", "bucket"])
        for r in rows:
            if r.get("status") != "success":
                w.writerow([r.get("query"), "", "", "", "failed"])
                continue
            cc = r.get("countryCode") or ""
            if cc == "CN":
                bucket = "中国大陆"
            elif cc in {"HK", "MO", "TW"}:
                bucket = "港澳台"
            else:
                bucket = "海外"
            w.writerow([r.get("query"), cc, r.get("country", ""), r.get("regionName", ""), bucket])


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch IP geolocation → Markdown table")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="Path to a file containing IPs (one per line, comma-sep, or JSON array)")
    src.add_argument("--ips", help="Comma-separated IPs on the command line")
    src.add_argument("--stdin", action="store_true", help="Read IPs from stdin")
    ap.add_argument("--csv", help="Write per-IP CSV to this path")
    ap.add_argument("--raw", help="Write raw ip-api JSON response to this path")
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    elif args.stdin:
        text = sys.stdin.read()
    else:
        text = args.ips

    ips = parse_ips_from_text(text)
    valid, invalid = validate_and_dedupe(ips)

    if invalid:
        print(f"# Skipped {len(invalid)} invalid tokens (not valid IPs)", file=sys.stderr)
    if not valid:
        print("ERROR: no valid IPs found in input", file=sys.stderr)
        return 1

    print(f"# Querying {len(valid)} IPs in {(len(valid)+BATCH_SIZE-1)//BATCH_SIZE} batches...", file=sys.stderr)

    rows: list[dict] = []
    for i in range(0, len(valid), BATCH_SIZE):
        batch = valid[i:i + BATCH_SIZE]
        idx = i // BATCH_SIZE + 1
        try:
            res = query_batch(batch)
            rows.extend(res)
            print(f"#   batch {idx}: {len(res)} returned", file=sys.stderr)
        except Exception as e:
            print(f"#   batch {idx} FAILED: {e}", file=sys.stderr)
            for ip in batch:
                rows.append({"status": "fail", "query": ip})
        if i + BATCH_SIZE < len(valid):
            time.sleep(PER_BATCH_SLEEP)

    if args.raw:
        with open(args.raw, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"# raw JSON → {args.raw}", file=sys.stderr)

    if args.csv:
        write_csv(args.csv, rows)
        print(f"# CSV → {args.csv}", file=sys.stderr)

    cn, foreign, failed = aggregate(rows)
    print(render_markdown(cn, foreign, len(rows), failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
