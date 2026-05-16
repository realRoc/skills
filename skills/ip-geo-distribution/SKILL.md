---
name: ip-geo-distribution
description: Geolocate a batch of IPv4 addresses and produce a Markdown distribution table — Chinese IPs broken down by province (incl. HK/MO/TW), foreign IPs by country, with counts and percentages. Optionally exports CSV. Uses the free ip-api.com batch endpoint (no key, no signup, HTTP only, 15 batches × 100 IPs per minute). Use when the user pastes a list of IPs and asks for "IP 分布", "IP 归属地分布", "省份分布", "where are these IPs from", "geolocate these IPs", or wants an IP-region breakdown table.
---

# IP Geo Distribution

Resolves an arbitrary list of IPv4 addresses to country (and Chinese province) and outputs a clean distribution table.

## What it produces

1. **Overall summary** — 中国大陆 / 港澳台 / 海外 三段汇总
2. **国内表** — 按省份/地区排序（含香港、澳门、台湾），列：地区 | 数量 | 占比
3. **海外表** — 按国家排序，列：国家 | 数量 | 占比
4. **(可选)** CSV：每个 IP 一行，包含 `ip, country_code, country, region, bucket`

## Data source

Uses **ip-api.com 批量接口** (`http://ip-api.com/batch`):

- 免费，无需 API key
- 限制：每分钟 ≤ 15 个 batch，每个 batch ≤ 100 IPs（即 ≤ 1500 IPs/min）
- 仅 HTTP（HTTPS 是付费版）
- 仅限非商业用途（如果用户场景是商用，提醒切换到 ip-api Pro 或本地 ip2region/MaxMind）

字段：`status,country,countryCode,regionName,query`。

省份准确率 80-90%（移动 4G/5G 出口 IP 偶有归错），国家级 ≈ 99%。

## Workflow

### 1. 收集 IP 列表

按用户提供方式接收输入：

- **粘贴在对话里**：把 IP 抽取出来传给 `--ips` 参数（逗号分隔）或写入临时文件传 `--file`
- **本地文件**：传 `--file <path>`，脚本自动识别每行一个 / 逗号分隔 / JSON 数组三种格式
- **stdin**：`cat ips.txt | python3 scripts/lookup_ips.py --stdin`

如果列表超过 ~5000 IPs，先告诉用户预计耗时（按 1500 IPs/min 估算）并征求确认。

### 2. 调用脚本

```bash
python3 scripts/lookup_ips.py \
  --file /tmp/ips.txt \
  [--csv /tmp/result.csv] \
  [--raw /tmp/raw.json]
```

或直接传 IPs：

```bash
python3 scripts/lookup_ips.py --ips "1.2.3.4,5.6.7.8,..."
```

脚本会：

- 自动去重 + 校验 IPv4 格式
- 按 100 切批，批次间 sleep 4.5s（保守低于 15 req/min）
- 失败的批次自动重试 3 次
- 把结果按 `countryCode` 分桶（CN 走省份映射，HK/MO/TW 单列，其它进国家桶）
- 把结果直接 print 成 Markdown 表格到 stdout
- 如果指定 `--csv`，同时落盘 CSV
- 如果指定 `--raw`，把 ip-api 原始 JSON 落盘

### 3. 输出结果

把脚本的 stdout 内容**原样**回给用户。前面加一句简短总览（"X 个 IP，其中国内 Y 个，海外 Z 个"），后面可以挑 1-2 个数据洞察补充（top 省份占比、海外集中度等）。

不要再二次加工省份名（脚本已经映射成中文）。

## Edge cases

- **私有/保留地址**（10.x、172.16-31.x、192.168.x、127.x 等）：ip-api 会返回 `status: fail`，脚本会把它们汇到 "查询失败" 列表里单独列出。
- **IPv6**：ip-api 支持，脚本也接受，但表格仍然按 country/region 维度统计，不区分 v4/v6。
- **`regionName` 为空**：极少见的边界 IP，归到 `中国-未知` 桶，提醒用户人工核查。
- **限速被拒**：HTTP 429 / `status: fail` 全批次失败 → 等 60s 再重试一次；仍失败则把这批 IP 报告给用户。
- **网络墙**：如果用户机器访问 ip-api.com 超时（罕见但可能），提示用户用代理或切换到本地 ip2region 数据库（不在本 skill 范围内）。

## Output format example

```markdown
## 总体概览

| 区域 | 数量 | 占比 |
|------|------|------|
| 中国大陆 | 1102 | 94.43% |
| 港澳台 | 20 | 1.71% |
| 海外 | 45 | 3.86% |

## 国内（含港澳台，按省份/地区）

| 省份/地区 | 数量 | 占比 |
|----------|------|------|
| 广东 | 289 | 24.76% |
| 北京 | 99 | 8.48% |
| ...

## 海外（按国家）

| 国家 | 数量 | 占比 |
|------|------|------|
| 美国 | 17 | 1.46% |
| ...
```
