#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书源采集器 - 从用户输入的合集链接批量抓取
- 读取 input_collections.txt
- 逐个下载 JSON
- 合并、去重、校验
- 输出 valid_sources.json 和 report.json
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ============ 配置 ============

INPUT_FILE = "input_collections.txt"
OUTPUT_DIR = "output"
VALID_SOURCES_FILE = os.path.join(OUTPUT_DIR, "valid_sources.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.json")

# ============ 工具函数 ============

def fetch_text(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LegadoSourceCollector/6.0"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")

def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.endswith("/"):
        url = url[:-1]
    return url

def is_legado_source(src: Any) -> bool:
    if not isinstance(src, dict):
        return False
    url = normalize_url(src.get("bookSourceUrl", ""))
    name = (src.get("bookSourceName") or "").strip()
    if not url or not name:
        return False

    rule_search = src.get("ruleSearch")
    rule_book_info = src.get("ruleBookInfo")
    rule_toc = src.get("ruleToc")
    rule_content = src.get("ruleContent")

    has_rule = any([
        rule_search and (isinstance(rule_search, dict) and rule_search),
        rule_book_info and (isinstance(rule_book_info, dict) and rule_book_info),
        rule_toc and (isinstance(rule_toc, dict) and rule_toc),
        rule_content and (isinstance(rule_content, dict) and rule_content),
    ])
    return has_rule

def dedup_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {}
    result = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        url = normalize_url(src.get("bookSourceUrl", ""))
        if not url:
            continue
        if url not in seen:
            seen[url] = True
            result.append(src)
    return result

def load_input_urls() -> List[str]:
    if not os.path.exists(INPUT_FILE):
        return []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    urls = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls

# ============ 主流程 ============

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_file": INPUT_FILE,
        "collections": [],
        "merged": {
            "raw_count": 0,
            "valid_count": 0,
            "dedup_count": 0
        },
        "final_count": 0
    }

    input_urls = load_input_urls()
    if not input_urls:
        print("No input URLs found in", INPUT_FILE)
        report["error"] = "No input URLs"
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return

    all_valid = []
    per_url_status = []

    for url in input_urls:
        status = {"url": url, "success": False, "count": 0, "error": None}
        try:
            text = fetch_text(url)
            data = json.loads(text)
            if not isinstance(data, list):
                status["error"] = "Not a list"
            else:
                valid = [s for s in data if is_legado_source(s)]
                status["success"] = True
                status["count"] = len(valid)
                all_valid.extend(valid)
        except Exception as e:
            status["error"] = str(e)
        per_url_status.append(status)

    report["collections"] = per_url_status
    report["merged"]["raw_count"] = sum(s["count"] for s in per_url_status if s["success"])
    report["merged"]["valid_count"] = len(all_valid)

    deduped = dedup_sources(all_valid)
    report["merged"]["dedup_count"] = len(deduped)
    report["final_count"] = len(deduped)

    if len(deduped) == 0:
        print("No valid sources fetched, keeping old files.")
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return

    with open(VALID_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Input URLs: {len(input_urls)}")
    print(f"Successful collections: {sum(1 for s in per_url_status if s['success'])}")
    print(f"Valid sources after dedup: {len(deduped)}")
    print(f"Report written to: {REPORT_FILE}")

if __name__ == "__main__":
    main()
