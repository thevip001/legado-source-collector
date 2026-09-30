"""
Legado/阅读 APP 书源抓取 + 去重 + 校验工具
功能：
1. 从多个公开书源地址批量下载书源 JSON
2. 合并并去重（按 bookSourceUrl + bookSourceName）
3. 并发校验书源可用性（检查书源 URL 是否可访问）
4. 输出有效书源和无效书源到两个 JSON 文件

使用前：
- 安装 Python 3.8+
- 安装依赖：pip install requests aiohttp
- 将本脚本放在一个空目录中运行
"""

import json
import os
import asyncio
import aiohttp
from typing import List, Dict, Any
from datetime import datetime

# ==================== 配置区 ====================

# 公开书源合集地址（可以自行增删）
SOURCE_URLS = [
    "https://raw.githubusercontent.com/liufuyou/read/main/bangdan.json",
    "https://raw.githubusercontent.com/XIU2/Yuedu/main/bookSource.json",
    "https://gitee.com/zoeybai/read/raw/Xiaobai/bangdan.json",
    "https://raw.githubusercontent.com/cjj200011222/legado-booksource/main/all.json",
    # 可以在此添加更多书源地址
]

# 测试关键词（用于后续可扩展的搜索校验）
TEST_KEYWORD = "系统"

# 并发数（根据网络情况调整，一般 10-50）
MAX_CONCURRENT = 20

# 单个书源请求超时时间（秒）
TIMEOUT_SECONDS = 5

# 输出文件名
OUTPUT_VALID = "valid_sources.json"
OUTPUT_INVALID = "invalid_sources.json"

# ==================== 工具函数 ====================

def load_sources_from_url(url: str) -> List[Dict[str, Any]]:
    """从 URL 加载书源列表"""
    import requests
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # 有些合集是直接列表，有些是 {"bookSources": [...]} 结构
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for key in ["bookSources", "sources", "data"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []
    except Exception as e:
        print(f"[!] 加载书源失败 {url}: {e}")
        return []

def deduplicate_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    去重策略：
    - 优先使用 bookSourceUrl + bookSourceName 作为唯一键
    - 如果没有 bookSourceUrl，则用 bookSourceName
    """
    seen = set()
    result = []
    for src in sources:
        url = src.get("bookSourceUrl", "")
        name = src.get("bookSourceName", "")
        key = f"{url}||{name}" if url else name
        if key not in seen:
            seen.add(key)
            result.append(src)
    return result

async def check_source_available(
    session: aiohttp.ClientSession,
    source: Dict[str, Any],
    semaphore: asyncio.Semaphore
) -> tuple[Dict[str, Any], bool]:
    """
    校验书源是否可用：
    - 尝试访问 bookSourceUrl（如果有）
    - 如果无法访问或超时，则标记为无效
    返回：(书源，是否有效)
    """
    async with semaphore:
        url = source.get("bookSourceUrl", "")
        if not url:
            # 没有 URL 的书源，暂时认为无效
            return source, False

        try:
            # 只检查 URL 是否可访问，不深入搜索
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)) as resp:
                if resp.status < 400:
                    return source, True
                else:
                    return source, False
        except Exception:
            return source, False

async def validate_sources(sources: List[Dict[str, Any]]) -> tuple[List[Dict], List[Dict]]:
    """并发校验所有书源"""
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [check_source_available(session, src, semaphore) for src in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    valid = []
    invalid = []
    for res in results:
        if isinstance(res, Exception):
            # 异常也视为无效
            continue
        src, is_ok = res
        if is_ok:
            valid.append(src)
        else:
            invalid.append(src)

    return valid, invalid

def save_json(data: List[Dict], filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_local_sources(filename: str) -> List[Dict[str, Any]]:
    """加载本地书源文件（可选）"""
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for key in ["bookSources", "sources", "data"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
    return []

# ==================== 主流程 ====================

async def main():
    print("[*] 开始抓取网络书源...")
    all_sources: List[Dict[str, Any]] = []

    # 1. 从网络抓取
    for url in SOURCE_URLS:
        print(f"    下载：{url}")
        sources = load_sources_from_url(url)
        print(f"    获得 {len(sources)} 条书源")
        all_sources.extend(sources)

    # 2. 可选：加载本地额外书源
    local_file = "local_sources.json"
    if os.path.exists(local_file):
        print(f"[*] 加载本地书源：{local_file}")
        local_sources = load_local_sources(local_file)
        all_sources.extend(local_sources)

    print(f"[*] 合并后总数：{len(all_sources)} 条")

    # 3. 去重
    print("[*] 开始去重...")
    deduped = deduplicate_sources(all_sources)
    print(f"[*] 去重后数量：{len(deduped)} 条")

    # 4. 校验
    print(f"[*] 开始校验书源（并发数={MAX_CONCURRENT}, 超时={TIMEOUT_SECONDS}s）...")
    valid, invalid = await validate_sources(deduped)

    print(f"[*] 校验完成：")
    print(f"    有效书源：{len(valid)} 条")
    print(f"    无效书源：{len(invalid)} 条")

    # 5. 保存结果
    save_json(valid, OUTPUT_VALID)
    save_json(invalid, OUTPUT_INVALID)

    print(f"[*] 结果已保存：")
    print(f"    有效书源 -> {OUTPUT_VALID}")
    print(f"    无效书源 -> {OUTPUT_INVALID}")
    print(f"[*] 完成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    # 需要安装：pip install requests aiohttp
    asyncio.run(main())
