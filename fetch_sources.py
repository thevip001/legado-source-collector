#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全网书源采集器 v5：
- Yiove 单书源列表遍历（抓取前 N 页）
- 保底直链
- GitHub API 发现书源仓库和 JSON 文件
- 结构验证、去重、失败不覆盖旧版
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ============ 配置 ============

OUTPUT_DIR = "output"
VALID_SOURCES_FILE = os.path.join(OUTPUT_DIR, "valid_sources.json")
REPORT_FILE = os.path.join(OUTPUT_DIR, "report.json")

# 保底直链
BASELINE_URLS = [
    "https://raw.githubusercontent.com/XIU2/Yuedu/master/shuyuan",
    "https://someok.github.io/booksources/data.json",
    "https://raw.githubusercontent.com/wuying283/yuedu/master/shuyuan.json",
    "https://raw.githubusercontent.com/cyao2q/yuedu/master/shuyuan",
    "https://raw.githubusercontent.com/liufuyou/read/master/shuyuan.json",
]

# Yiove 配置
YIOVE_BASE = "https://shuyuan.yiove.com"
YIOVE_LIST_URL = YIOVE_BASE + "/book-sources?page={page}&page_size={page_size}"
YIOVE_MAX_PAGES = 5  # 每次抓几页
YIOVE_PAGE_SIZE = 20

# GitHub API
GITHUB_API_BASE = "https://api.github.com"
GITHUB_SEARCH_QUERIES = [
    "legado bookSource in:name,description",
    "阅读 书源 in:name,description",
    "开源阅读 书源",
    "legado shuyuan",
]

# ============ 工具函数 ============

def fetch_text(url: str, timeout: int = 30, headers: Optional[Dict[str, str]] = None) -> str:
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LegadoSourceCollector/5.0"
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")

def fetch_json(url: str, timeout: int = 30, headers: Optional[Dict[str, str]] = None) -> Any:
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LegadoSourceCollector/5.0",
        "Accept": "application/json"
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        text = resp.read().decode(charset, errors="replace")
        return json.loads(text)

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
    # 至少有一个规则字段非空
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

# ============ Yiove 发现 ============

def discover_yiove_sources() -> List[Dict[str, Any]]:
    """
    遍历 Yiove 书源列表页，从详情页 HTML 中提取书源 JSON。
    """
    all_sources = []
    for page in range(1, YIOVE_MAX_PAGES + 1):
        list_url = YIOVE_LIST_URL.format(page=page, page_size=YIOVE_PAGE_SIZE)
        try:
            html = fetch_text(list_url)
            # 提取书源详情页链接：/book-source/{uuid}
            pattern = r'href="(/book-source/[^"]+)"'
            detail_paths = re.findall(pattern, html)
            if not detail_paths:
                break
            for path in detail_paths[:YIOVE_PAGE_SIZE]:  # 每页最多处理 page_size 个
                detail_url = YIOVE_BASE + path
                try:
                    detail_html = fetch_text(detail_url)
                    # 提取 "书源原始 JSON" 后的 JSON 文本
                    json_pattern = r'(\{\s*"bookSourceComment".*\})'
                    m = re.search(json_pattern, detail_html, re.DOTALL)
                    if m:
                        json_text = m.group(1)
                        src = json.loads(json_text)
                        if is_legado_source(src):
                            all_sources.append(src)
                except Exception:
                    continue
        except Exception:
            break
    return all_sources

# ============ GitHub 发现 ============

def discover_from_github_api(query: str) -> List[Dict[str, Any]]:
    urls = []
    try:
        search_url = f"{GITHUB_API_BASE}/search/repositories?q={urllib.parse.quote(query)}&sort=updated&order=desc&per_page=10"
        data = fetch_json(search_url)
        items = data.get("items", [])
        for repo in items:
            full_name = repo["full_name"]
            default_branch = repo.get("default_branch", "main")
            tree_url = f"{GITHUB_API_BASE}/repos/{full_name}/git/trees/{default_branch}?recursive=1"
            try:
                tree_data = fetch_json(tree_url)
                tree = tree_data.get("tree", [])
                for item in tree:
                    path = item.get("path", "")
                    if path.endswith(".json") and any(kw in path.lower() for kw in ["shuyuan", "booksource", "source"]):
                        raw_url = f"https://raw.githubusercontent.com/{full_name}/{default_branch}/{path}"
                        urls.append(raw_url)
            except Exception:
                pass
    except Exception:
        pass

    # 抓取这些 URL
    all_sources = []
    for url in urls:
        try:
            text = fetch_text(url)
            data = json.loads(text)
            if isinstance(data, list):
                for src in data:
                    if is_legado_source(src):
                        all_sources.append(src)
        except Exception:
            pass
    return all_sources

# ============ 保底直链抓取 ============

def fetch_baseline() -> List[Dict[str, Any]]:
    all_sources = []
    for url in BASELINE_URLS:
        try:
            text = fetch_text(url)
            data = json.loads(text)
            if isinstance(data, list):
                for src in data:
                    if is_legado_source(src):
                        all_sources.append(src)
        except Exception:
            pass
    return all_sources

# ============ 主流程 ============

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "baseline": {"count": 0},
            "yiove": {"count": 0},
            "github": {"count": 0}
        },
        "merged": {
            "raw_count": 0,
            "valid_count": 0,
            "dedup_count": 0
        },
        "final_count": 0
    }

    all_valid = []

    # 1. 保底
    baseline_sources = fetch_baseline()
    report["sources"]["baseline"]["count"] = len(baseline_sources)
    all_valid.extend(baseline_sources)

    # 2. Yiove
    yiove_sources = discover_yiove_sources()
    report["sources"]["yiove"]["count"] = len(yiove_sources)
    all_valid.extend(yiove_sources)

    # 3. GitHub
    github_sources = []
    for query in GITHUB_SEARCH_QUERIES:
        srcs = discover_from_github_api(query)
        github_sources.extend(srcs)
    report["sources"]["github"]["count"] = len(github_sources)
    all_valid.extend(github_sources)

    report["merged"]["raw_count"] = len(all_valid)
    report["merged"]["valid_count"] = len(all_valid)

    # 去重
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

    print(f"Baseline: {report['sources']['baseline']['count']}")
    print(f"Yiove: {report['sources']['yiove']['count']}")
    print(f"GitHub: {report['sources']['github']['count']}")
    print(f"Valid sources after dedup: {len(deduped)}")
    print(f"Report written to: {REPORT_FILE}")

if __name__ == "__main__":
    main()
