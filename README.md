# MusicCrawler

基于 [QQ音乐](https://y.qq.com/) 的关键词搜索与歌曲下载工具。

## 功能

- 关键词搜索歌曲（对接 y.qq.com 搜索接口）
- 交互式或命令行指定下载
- 支持多种音质：MP3 128k / MP3 320k / M4A / FLAC（失败时自动降级）
- 批量下载全部搜索结果

## 环境要求

- **Python 3.10+**（本机 `python` 若是 2.7，请用 `python3`）

```bash
python --version   # 若显示 2.7.x，请改用 python3
python3 --version  # 应为 3.10+
```

## 安装

```bash
python3 -m pip install -r requirements.txt
```

## 使用方法

> 以下命令请使用 `python3` 或 `./run.sh`，不要用 `python`（Ubuntu 上 `python` 默认常为 Python 2.7）。

### 交换模式（推荐，默认）

只传 `-k` 时自动进入交换模式，支持：**搜索 → 按条目下载 → 回退重新搜索** 循环。

```bash
./run.sh -k "稻香"
```

操作流程：
1. **[1] 搜索**：显示搜索结果（含可下载状态）
2. **[2] 下载**：输入序号（如 `1`、`1,3`、`all`）进行下载
3. **回退**：输入 `search` 回到搜索，可换关键词；输入 `quit` 退出

下载阶段可用命令：

| 命令 | 说明 |
|------|------|
| `1` / `1,3` | 下载指定序号 |
| `all` | 下载全部 |
| `list` | 重新显示当前列表 |
| `search` | 回到搜索 |
| `quit` | 退出 |

### 单次搜索（仅查看结果）

```bash
python3 main.py -k "稻香" --no-exchange
```

### 下载指定序号

```bash
python3 main.py -k "两只老虎" -i 1
```

### 下载全部搜索结果

```bash
python3 main.py -k "小星星" --all -o ./downloads
```

### 交互模式

```bash
python3 main.py -k "晴天" --interactive
```

### 指定音质

```bash
python3 main.py -k "海阔天空" -i 1 -q mp3_320
```

### 歌词

下载歌曲时默认同时保存同名 `.lrc` 歌词文件：

```bash
python3 main.py -k "稻香" -i 2 -o ./downloads
# 生成: 稻香 - 白允y.mp3  和  稻香 - 白允y.lrc
```

不需要歌词时加 `--no-lyric`。

## 参数说明

| 参数 | 说明 |
|------|------|
| `-k, --keyword` | 搜索关键词（必填） |
| `-n, --num` | 搜索结果数量，默认 10 |
| `-i, --index` | 下载指定序号（从 1 开始） |
| `--all` | 下载全部搜索结果 |
| `--interactive` | 交互选择要下载的歌曲 |
| `-q, --quality` | 音质：mp3_128 / mp3_320 / m4a / flac |
| `-o, --output` | 保存目录，默认 `./downloads` |

## 关于原版 VIP 歌曲 (104003)

QQ 音乐**不存在可绕过的原版固定直链**。所有音频文件存放在 CDN 上，下载前必须向服务端申请带时效的 `vkey`，服务端会校验：

- 是否登录
- 账号是否有绿钻/付费包
- 该曲目是否允许下载

未满足条件时返回 `104003`，这不是客户端能跳过的限制。

**下载原版的唯一方式：使用已开通绿钻的 QQ 音乐账号登录。**

```bash
# 1. 生成凭证模板
python3 main.py --init-credential qqmusic_cred.json

# 2. 浏览器登录 y.qq.com，从 Cookie 复制 uin 和 qqmusic_key 填入文件

# 3. 下载原版
python3 main.py -k "稻香" -i 1 --credential qqmusic_cred.json
```

获取 Cookie：浏览器打开 [y.qq.com](https://y.qq.com) 并登录 -> F12 -> Application -> Cookies -> 复制 `uin` 和 `qqmusic_key`。

## 注意事项

- 本工具仅供技术学习研究，请尊重版权，支持正版音乐。
- 登录凭证仅保存在本地，请勿泄露 `qqmusic_key`。
- 搜索接口返回数量受平台限制，建议使用更精确的关键词。
