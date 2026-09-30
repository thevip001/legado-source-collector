"""Legado/阅读书源采集、结构校验和去重工具。"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

SOURCE_URLS = [
    "https://raw.githubusercontent.com/liufuyou/read/main/bangdan.json",
    "https://raw.githubusercontent.com/XIU2/Yuedu/main/bookSource.json",
    "https://gitee.com/zoeybai/read/raw/Xiaobai/bangdan.json",
    "https://raw.githubusercontent.com/cjj200011222/legado-booksource/main/all.json",
]

DOWNLOAD_TIMEOUT_SECONDS = 20
OUTPUT_VALID = "valid_sources.json"
OUTPUT_PENDING = "pending_sources.json"
OUTPUT_INVALID = "invalid_sources.json"
REQUIRED_FIELDS = (
    "bookSourceName",
    "bookSourceUrl",
    "ruleSearch",
    "ruleBookInfo",
    "ruleToc",
    "ruleContent",
)


def extract_sources(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("bookSources", "sources", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def fetch_source_list(url: str) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 LegadoSourceCollector/1.0"}
    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, headers=headers)
        response.raise_for_status()
        return extract_sources(response.json())
    except (requests.RequestException, ValueError) as exc:
        print(f"[WARN] 无法下载或解析 {url}: {exc}")
        return []


def load_local_sources(path: str = "local_sources.json") -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as file:
            return extract_sources(json.load(file))
    except (OSError, ValueError) as exc:
        print(f"[WARN] 无法读取本地书源 {path}: {exc}")
        return []


def normalize_url(url: str) -> str:
    value = url.strip()
    try:
        parts = urlsplit(value)
        scheme = parts.scheme.lower()
        host = parts.netloc.lower()
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((scheme, host, path, parts.query, ""))
    except ValueError:
        return value.rstrip("/").lower()


def has_rule(source: dict[str, Any], field: str) -> bool:
    value = source.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(bool(str(item).strip()) for item in value.values())
    return value is not None


def classify_source(source: dict[str, Any]) -> tuple[str, str]:
    name = source.get("bookSourceName")
    url = source.get("bookSourceUrl")
    if not isinstance(name, str) or not name.strip():
        return "invalid", "缺少 bookSourceName"
    if not isinstance(url, str) or not url.strip().startswith(("http://", "https://")):
        return "invalid", "缺少有效的 bookSourceUrl"

    missing = [field for field in REQUIRED_FIELDS[2:] if not has_rule(source, field)]
    if not missing:
        return "valid", "规则完整"
    return "pending", "缺少规则字段：" + ", ".join(missing)


def score(source: dict[str, Any]) -> int:
    return sum(has_rule(source, field) for field in REQUIRED_FIELDS[2:])


def deduplicate(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for source in sources:
        key = normalize_url(str(source.get("bookSourceUrl", "")))
        if not key:
            continue
        previous = selected.get(key)
        if previous is None or score(source) > score(previous):
            selected[key] = source
    return list(selected.values())


def save_json(path: str, data: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    print("[*] 开始抓取公开 Legado 书源合集")
    collected: list[dict[str, Any]] = []
    for url in SOURCE_URLS:
        sources = fetch_source_list(url)
        print(f"    {url}: {len(sources)} 条")
        collected.extend(sources)

    local_sources = load_local_sources()
    if local_sources:
        print(f"    local_sources.json: {len(local_sources)} 条")
        collected.extend(local_sources)

    print(f"[*] 抓取总数：{len(collected)}")
    unique_sources = deduplicate(collected)
    print(f"[*] URL 去重后：{len(unique_sources)}")

    valid: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for source in unique_sources:
        state, reason = classify_source(source)
        source = dict(source)
        source["_collectorStatus"] = state
        source["_collectorReason"] = reason
        if state == "valid":
            valid.append(source)
        elif state == "pending":
            pending.append(source)
        else:
            invalid.append(source)

    save_json(OUTPUT_VALID, valid)
    save_json(OUTPUT_PENDING, pending)
    save_json(OUTPUT_INVALID, invalid)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[*] 完成于 {generated_at}")
    print(f"    有效（完整规则）：{len(valid)}")
    print(f"    待验证（规则不完整）：{len(pending)}")
    print(f"    无效（基础字段错误）：{len(invalid)}")

    if not valid:
        print("[ERROR] 没有生成可导入的完整书源；拒绝发布空数组。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
