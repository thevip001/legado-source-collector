#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源书源采集器：
- 从多个公开来源抓取 Legado 书源
- 验证、去重、过滤完整书源
- 生成 valid_sources.json 和 report.json
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ============ 配置 ============

SOURCES = {
    "xiu2": {
        "name": "XIU2",
        "urls": [
            "https://raw.githubusercontent.com/XIU2/Yuedu/master/shuyuan"
        ]
    },
    "yiove": {
        "name": "Yiove",
        "list_url": "https://shuyuan.yiove.com/book-source-collections?page=1&page_size=20",
        "export_template": "https://shuyuan-api.yiove.com/import/book-source-collection/{collection_id}"
    }
}

OUTPUT_DIR = "output"
VALID_SOURCES_FILE = os.path.join(OUTPUT_DIR, "valid_sources.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.json")

# ============ 工具函数 ============

def fetch_text(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LegadoSourceCollector/1.0"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")

def parse_json_list(text: str) -> List[Any]:
    text = text.strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []

def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.endswith("/"):
        url = url[:-1]
    return url

def is_complete_source(src: Dict[str, Any]) -> bool:
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

# ============ 来源抓取逻辑 ============

def fetch_xiu2() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    status = {
        "source": "xiu2",
        "name": SOURCES["xiu2"]["name"],
        "success": False,
        "error": None,
        "raw_count": 0,
        "valid_count": 0
    }
    all_sources = []
    for url in SOURCES["xiu2"]["urls"]:
        try:
            text = fetch_text(url)
            sources = parse_json_list(text)
            status["raw_count"] += len(sources)
            all_sources.extend(sources)
            status["success"] = True
        except Exception as e:
            status["error"] = str(e)
            status["success"] = False

    valid = [s for s in all_sources if is_complete_source(s)]
    status["valid_count"] = len(valid)
    return valid, status

def fetch_yiove_collection_ids() -> List[str]:
    ids = []
    try:
        text = fetch_text(SOURCES["yiove"]["list_url"])
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        cid = item.get("id") or item.get("collection_id") or item.get("uuid")
                        if cid:
                            ids.append(str(cid))
            elif isinstance(data, dict):
                items = data.get("data") or data.get("items") or data.get("collections") or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            cid = item.get("id") or item.get("collection_id") or item.get("uuid")
                            if cid:
                                ids.append(str(cid))
        except json.JSONDecodeError:
            pattern = r"/book-source-collection/([0-9a-fA-F\-]{30,})"
            for m in re.finditer(pattern, text):
                cid = m.group(1)
                if cid and cid not in ids:
                    ids.append(cid)
    except Exception:
        pass
    return ids

def fetch_yiove() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    status = {
        "source": "yiove",
        "name": SOURCES["yiove"]["name"],
        "success": False,
        "error": None,
        "collections_total": 0,
        "collections_success": 0,
        "raw_count": 0,
        "valid_count": 0
    }

    collection_ids = fetch_yiove_collection_ids()
    status["collections_total"] = len(collection_ids)

    if not collection_ids:
        status["error"] = "No collection IDs found"
        return [], status

    all_sources = []
    last_error = None

    for cid in collection_ids:
        export_url = SOURCES["yiove"]["export_template"].format(collection_id=cid)
        try:
            text = fetch_text(export_url)
            sources = parse_json_list(text)
            status["raw_count"] += len(sources)
            all_sources.extend(sources)
            status["collections_success"] += 1
            last_error = None
        except Exception as e:
            last_error = str(e)

    if status["collections_success"] > 0:
        status["success"] = True
    else:
        status["error"] = last_error or "All collections failed"

    valid = [s for s in all_sources if is_complete_source(s)]
    status["valid_count"] = len(valid)
    return valid, status

# ============ 主流程 ============

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {},
        "merged": {
            "raw_count": 0,
            "valid_count": 0,
            "dedup_count": 0
        },
        "final_count": 0
    }

    all_valid = []

    # 1. XIU2
    try:
        xiu2_valid, xiu2_status = fetch_xiu2()
        report["sources"]["xiu2"] = xiu2_status
        all_valid.extend(xiu2_valid)
    except Exception as e:
        report["sources"]["xiu2"] = {
            "source": "xiu2",
            "name": SOURCES["xiu2"]["name"],
            "success": False,
            "error": str(e),
            "raw_count": 0,
            "valid_count": 0
        }

    # 2. Yiove
    try:
        yiove_valid, yiove_status = fetch_yiove()
        report["sources"]["yiove"] = yiove_status
        all_valid.extend(yiove_valid)
    except Exception as e:
        report["sources"]["yiove"] = {
            "source": "yiove",
            "name": SOURCES["yiove"]["name"],
            "success": False,
            "error": str(e),
            "collections_total": 0,
            "collections_success": 0,
            "raw_count": 0,
            "valid_count": 0
        }

    # 合并统计
    report["merged"]["raw_count"] = sum(
        s.get("raw_count", 0) for s in report["sources"].values()
    )
    report["merged"]["valid_count"] = len(all_valid)

    # 去重
    deduped = dedup_sources(all_valid)
    report["merged"]["dedup_count"] = len(deduped)

    report["final_count"] = len(deduped)

    with open(VALID_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Valid sources: {len(deduped)}")
    print(f"Report written to: {REPORT_FILE}")

if __name__ == "__main__":
    main()
