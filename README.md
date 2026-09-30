# legado-source-collector

Legado/阅读 APP 书源抓取 + 去重 + 校验工具

## 功能

- 从多个公开书源地址批量下载书源 JSON
- 自动合并并去重（按 bookSourceUrl + bookSourceName）
- 并发校验书源 URL 是否可访问
- 输出有效书源和无效书源到两个 JSON 文件

## 使用方法

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行脚本

```bash
python legado_source_collector.py
```

运行后会生成：
- `valid_sources.json`：有效书源
- `invalid_sources.json`：无效书源

### 导入阅读 APP

1. 打开「阅读」APP → 我的 → 书源管理 → 本地导入
2. 选择 `valid_sources.json` 即可

## 配置

在脚本顶部的 `SOURCE_URLS` 列表中添加或修改书源地址：

```python
SOURCE_URLS = [
    "https://raw.githubusercontent.com/liufuyou/read/main/bangdan.json",
    "https://raw.githubusercontent.com/XIU2/Yuedu/main/bookSource.json",
    "https://gitee.com/zoeybai/read/raw/Xiaobai/bangdan.json",
    "https://raw.githubusercontent.com/cjj200011222/legado-booksource/main/all.json",
]
```

### 加载本地书源

将本地书源文件命名为 `local_sources.json` 放在同一目录，脚本会自动加载并一起校验。

## 参数调整

- `MAX_CONCURRENT`：并发数（根据网络情况调整，一般 10-50）
- `TIMEOUT_SECONDS`：单个书源请求超时时间（秒）

## License

MIT
