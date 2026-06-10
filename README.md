# MusicCrawler

基于 [QQ音乐](https://y.qq.com/)、[酷我音乐](https://www.kuwo.cn/)、[酷狗音乐](https://www.kugou.com/) 和 [网易云音乐](https://music.163.com/) 的关键词搜索与歌曲下载工具。

## 支持平台

| 平台 | 参数 | 网址 |
|------|------|------|
| QQ音乐 | `-p qq`（默认） | https://y.qq.com |
| 酷我音乐 | `-p kuwo` | https://www.kuwo.cn |
| 酷狗音乐 | `-p kugou` | https://www.kugou.com |
| 网易云音乐 | `-p netease` | https://music.163.com |

## 功能

- 关键词搜索歌曲
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
./run.sh -p netease -k "稻香"
./run.sh -p kugou -k "稻香"
./run.sh -p kuwo -k "稻香"
./run.sh -p qq -k "稻香"
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

### 酷我音乐下载

```bash
python3 main.py -p kuwo -k "稻香" -i 4
python3 main.py -p kuwo -k "两只老虎" --all -o ./downloads
```

### 酷狗音乐下载

```bash
python3 main.py -p kugou -k "稻香" -i 2
python3 main.py -p kugou -k "两只老虎" --all -o ./downloads
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
| `-c, --config` | 配置文件 (默认读取 `./musiccrawler.json`) |
| `--proxy` | HTTP/HTTPS 代理 |
| `--retries` | 请求重试次数，默认 3 |
| `--timeout` | 请求超时秒数，默认 30 |
| `--rate-limit` | HTTP 限速 (请求/秒，0=不限) |
| `-j, --workers` | 并发下载线程数，默认 1 |
| `--verbose` | 调试日志 |
| `--json-log` | JSON 格式日志 |
| `--no-verify-credential` | 跳过凭证有效性检查 |

## 平台登录（VIP 账号）

各平台登录后凭证自动保存，后续下载时自动加载。

| 平台 | 凭证文件 | 支持方式 |
|------|----------|----------|
| QQ音乐 | `qqmusic_cred.json` | 扫码 / 手机验证码 / 密码(手机号) |
| 酷狗音乐 | `kugou_cred.json` | 用户名+密码 |
| 酷我音乐 | `kuwo_cred.json` | 用户名+密码（需图形验证码） |
| 网易云音乐 | `netease_cred.json` | 扫码 / 手机验证码 / 用户名+密码 |

### 网易云音乐登录

```bash
# 扫码登录（推荐）
python3 main.py -p netease --login qr

# 手机号+密码
python3 main.py -p netease --login password --user 13800138000 --password 你的密码

# 手机验证码登录
python3 main.py -p netease --login phone --user 13800138000 --password 123456

# 登录后下载
python3 main.py -p netease -k "稻香" -i 1
```

### 酷狗音乐登录

```bash
python3 main.py -p kugou --login password --user 手机号 --password 你的密码
python3 main.py -p kugou -k "稻香" -i 1
```

### 酷我音乐登录

```bash
python3 main.py -p kuwo --login password --user 手机号 --password 你的密码
# 会生成 kuwo_login_captcha.jpg，输入图片中的验证码
python3 main.py -p kuwo -k "稻香" -i 1
```

## QQ音乐登录（绿钻账号）

支持三种登录方式，登录后凭证保存到 `qqmusic_cred.json`，后续自动加载。

### 方式 1：QQ 扫码登录（推荐）

```bash
python3 main.py --login qr
# 扫描生成的 qq_login_qr.png，用手机 QQ 确认
```

### 方式 2：手机号 + 验证码

```bash
# 交互式
python3 main.py --login phone --user 13800138000

# 一步完成（已收到验证码）
python3 main.py --login phone --user 13800138000 --password 123456
```

### 方式 3：用户名 + 密码参数

```bash
# 手机号作为用户名，短信验证码作为密码
python3 main.py --login password --user 13800138000 --password 123456
```

> QQ号+QQ密码暂不支持直接登录（腾讯需扫码/验证码）。请用扫码或手机号方式。

### 登录后下载 VIP 歌曲

```bash
python3 main.py -p qq -k "稻香" -i 1
# 自动读取 ./qqmusic_cred.json
```

## 关于原版 VIP 歌曲 (104003)

QQ 音乐**不存在可绕过的原版固定直链**。所有音频文件存放在 CDN 上，下载前必须向服务端申请带时效的 `vkey`，服务端会校验：

- 是否登录
- 账号是否有绿钻/付费包
- 该曲目是否允许下载

未满足条件时返回 `104003`，这不是客户端能跳过的限制。

**下载原版的唯一方式：使用已开通绿钻的 QQ 音乐账号登录。**

```bash
# 推荐：扫码登录
python3 main.py --login qr

# 然后下载
python3 main.py -p qq -k "稻香" -i 1
```

也可手动导入浏览器 Cookie：见 `--init-credential` 说明。

### 配置文件

复制示例并按需修改：

```bash
cp musiccrawler.example.json musiccrawler.json
python3 main.py -k "稻香"
```

也可通过环境变量 `MUSICCRAWLER_CONFIG` 或 `-c /path/to/config.json` 指定配置。命令行参数优先于配置文件。

常用配置项：`platform`、`proxy`、`rate_limit`、`workers`、`output`、`quality`。

### 并发下载与限速

```bash
# 3 线程并发下载，HTTP 限速 2 请求/秒
python3 main.py -p netease -k "稻香" --all --workers 3 --rate-limit 2
```

## 工程化改进

| 模块 | 说明 |
|------|------|
| `http_client.py` | 统一 HTTP 会话，支持代理、超时、重试、线程安全、限速 |
| `download_manager.py` | 并发下载编排 |
| `app_config.py` | JSON 配置文件加载 |
| `crypto/` | 各平台签名/加密逻辑集中管理 |
| `platforms.py` | 平台注册表与客户端工厂 |
| `credential_verify.py` | 启动时检查凭证是否仍有效 |
| `platform_cred.py` | 凭证保存时自动 `chmod 600` |
| `kuwo_parse.py` | 安全解析酷我搜索响应（替代 `ast.literal_eval`） |

QQ / 网易云 probe 已改为批量查询；酷狗 / 酷我采用搜索元数据启发式 + 去重批量探测，probe 仅检测目标音质（不再逐级降级）。

### 运行测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -v
```

## 注意事项

- 本工具仅供技术学习研究，请尊重版权，支持正版音乐。
- 登录凭证仅保存在本地（`chmod 600`），请勿泄露账号凭证文件。
- 搜索接口返回数量受平台限制，建议使用更精确的关键词。
