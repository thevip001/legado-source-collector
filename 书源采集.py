#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone
from typing import Any, Dict, List

INPUT_FILE = "书源合集列表.txt"
OUTPUT_DIR = "output"
VALID_SOURCES_FILE = os.path.join(OUTPUT_DIR, "valid_sources.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.json")
SOURCE_TIMEOUT = 10

def fetch_text(url: str, timeout: int = 30) -> str:
    print(f"Fetching: {url}", flush=True)
    headers = {"User-Agent": "Mozilla/5.0 LegadoSourceCollector/7.0"}
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
        rule_search and isinstance(rule_search, dict) and rule_search,
        rule_book_info and isinstance(rule_book_info, dict) and rule_book_info,
        rule_toc and isinstance(rule_toc, dict) and rule_toc,
        rule_content and isinstance(rule_content, dict) and rule_content,
    ])
    return has_rule

def test_source_availability(src: Dict[str, Any], timeout: int = 10) -> bool:
    url = normalize_url(src.get("bookSourceUrl", ""))
    if not url or url.startswith("墨辰整理") or "example.com" in url.lower():
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False

def dedup_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {}
    result = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        url = normalize_url(src.get("bookSourceUrl", ""))
        if not url or url in seen:
            continue
        seen[url] = True
        result.append(src)
    return result

def load_input_urls() -> List[str]:
    if not os.path.exists(INPUT_FILE):
        return []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "collections": [], "final_count": 0, "tested": 0, "passed": 0}
    input_urls = load_input_urls()
    print(f"Found {len(input_urls)} collection URLs", flush=True)
    if not input_urls:
        print("No input URLs found in", INPUT_FILE, flush=True)
        report["error"] = "No input URLs"
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return
    all_valid = []
    per_url_status = []
    for i, url in enumerate(input_urls):
        print(f"[{i+1}/{len(input_urls)}] Processing: {url}", flush=True)
        status = {"url": url, "success": False, "count": 0, "error": None}
        try:
            text = fetch_text(url)
            data = json.loads(text)
            if isinstance(data, list):
                valid = [s for s in data if is_legado_source(s)]
                status["success"] = True
                status["count"] = len(valid)
                all_valid.extend(valid)
                print(f"  -> Got {len(valid)} valid sources", flush=True)
            else:
                status["error"] = "Not a list"
                print(f"  -> Error: Not a list", flush=True)
        except Exception as e:
            status["error"] = str(e)
            print(f"  -> Error: {e}", flush=True)
        per_url_status.append(status)
    report["collections"] = per_url_status
    print(f"\nTotal: {len(all_valid)} sources, starting dedup...", flush=True)
    deduped = dedup_sources(all_valid)
    print(f"After dedup: {len(deduped)} sources, starting availability test (10s timeout)...", flush=True)
    passed = []
    for i, src in enumerate(deduped):
        if test_source_availability(src, timeout=SOURCE_TIMEOUT):
            passed.append(src)
        if (i + 1) % 50 == 0:
            print(f"Tested {i + 1}/{len(deduped)}, passed: {len(passed)}", flush=True)
    report["tested"] = len(deduped)
    report["passed"] = len(passed)
    report["final_count"] = len(passed)
    if len(passed) == 0:
        print("No valid sources after test, keeping old files.", flush=True)
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return
    with open(VALID_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(passed, f, ensure_ascii=False, indent=2)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nDone! Tested: {len(deduped)}, Passed: {len(passed)}", flush=True)

if __name__ == "__main__":
    main()
