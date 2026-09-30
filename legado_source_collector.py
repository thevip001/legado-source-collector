"""抓取、校验并整理公开 Legado 书源。"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

# 已验证：该地址返回可导入的 Legado 书源 JSON 数组。
SOURCE_URLS = [
    "https://raw.githubusercontent.com/XIU2/Yuedu/master/shuyuan",
]

DOWNLOAD_TIMEOUT_SECONDS = 30
OUTPUT_VALID = "valid_sources.json"
OUTPUT_INVALID = "invalid_sources.json"
REQUIRED_RULES = ("ruleSearch", "ruleBookInfo", "ruleToc", "ruleContent")


def extract_sources(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("bookSources", "sources", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def fetch_sources(url: str) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LegadoSourceCollector/1.0)",
        "Accept": "application/json,text/plain,*/*",
    }
    try:
        response = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
        sources = extract_sources(response.json())
        print(f"[OK] {url}: 获取 {len(sources)} 条")
        return sources
    except (requests.RequestException, ValueError) as exc:
        print(f"[WARN] {url}: 获取失败：{exc}")
        return []


def normalize_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", parts.query, ""))
    except ValueError:
        return value.strip().rstrip("/").lower()


def rule_present(source: dict[str, Any], field: str) -> bool:
    value = source.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(bool(str(item).strip()) for item in value.values())
    return value is not None


def is_complete_legado_source(source: dict[str, Any]) -> bool:
    name = source.get("bookSourceName")
    url = source.get("bookSourceUrl")
    return (
        isinstance(name, str)
        and bool(name.strip())
        and isinstance(url, str)
        and url.startswith(("http://", "https://"))
        and all(rule_present(source, field) for field in REQUIRED_RULES)
    )


def source_score(source: dict[str, Any]) -> int:
    return sum(rule_present(source, field) for field in REQUIRED_RULES)


def deduplicate(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for source in sources:
        key = normalize_url(str(source.get("bookSourceUrl", "")))
        if not key:
            continue
        old = selected.get(key)
        if old is None or source_score(source) > source_score(old):
            selected[key] = source
    return list(selected.values())


def write_json(path: str, content: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(content, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    print("[*] 开始抓取公开书源")
    collected: list[dict[str, Any]] = []
    for url in SOURCE_URLS:
        collected.extend(fetch_sources(url))

    local_path = "local_sources.json"
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as file:
                local = extract_sources(json.load(file))
            print(f"[OK] {local_path}: 获取 {len(local)} 条")
            collected.extend(local)
        except (OSError, ValueError) as exc:
            print(f"[WARN] {local_path}: 读取失败：{exc}")

    print(f"[*] 合并前：{len(collected)} 条")
    unique = deduplicate(collected)
    valid = [source for source in unique if is_complete_legado_source(source)]
    invalid = [source for source in unique if not is_complete_legado_source(source)]

    write_json(OUTPUT_VALID, valid)
    write_json(OUTPUT_INVALID, invalid)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[*] URL 去重后：{len(unique)}")
    print(f"[*] 有效完整书源：{len(valid)}")
    print(f"[*] 不完整书源：{len(invalid)}")
    print(f"[*] 完成于 {now}")

    if not valid:
        print("[ERROR] 未抓到可导入书源，拒绝发布空文件。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
