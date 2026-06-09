#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Music keyword search and download crawler."""

from __future__ import annotations

import argparse
import sys
from typing import Protocol

from credential import load_credential, load_credential_if_exists, save_credential_template
from kugou_client import KugouMusicClient
from kugou_login import KugouCredential
from kugou_login import LoginError as KugouLoginError
from kugou_login import run_login as run_kugou_login
from kuwo_client import KuwoMusicClient
from kuwo_login import KuwoCredential
from kuwo_login import LoginError as KuwoLoginError
from kuwo_login import run_login as run_kuwo_login
from platform_cred import default_credential_path, load_json_credential, resolve_credential_path
from qq_login import LoginError as QQLoginError
from qq_login import run_login as run_qq_login
from qqmusic_client import QQMusicClient
from song import DownloadError, Song

PLATFORM_NAMES = {
    "qq": "QQ音乐 (y.qq.com)",
    "kuwo": "酷我音乐 (kuwo.cn)",
    "kugou": "酷狗音乐 (kugou.com)",
}


class MusicClient(Protocol):
    def search(self, keyword: str, limit: int = 20) -> list[Song]: ...
    def probe_downloadable(self, songs: list[Song], quality: str = "mp3_128") -> list[Song]: ...
    def download(
        self,
        song: Song,
        output_dir: str,
        quality: str = "mp3_128",
        filename: str | None = None,
        *,
        with_lyric: bool = True,
    ) -> tuple[str, str | None]: ...


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="音乐关键词搜索与下载工具 (支持 QQ音乐 / 酷我音乐 / 酷狗音乐)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 main.py -p kugou -k "稻香"
  python3 main.py -p kuwo -k "稻香"
  python3 main.py -p qq -k "稻香" -i 1
  python3 main.py -p kugou -k "两只老虎" --all -o ./downloads
        """,
    )
    parser.add_argument(
        "-p",
        "--platform",
        choices=["qq", "kuwo", "kugou"],
        default="qq",
        help="音乐平台: qq / kuwo / kugou，默认 qq",
    )
    parser.add_argument("-k", "--keyword", help="搜索关键词")
    parser.add_argument("-n", "--num", type=int, default=10, help="搜索结果数量 (默认: 10)")
    parser.add_argument("-i", "--index", type=int, help="下载指定序号的歌曲 (从 1 开始)")
    parser.add_argument("--all", action="store_true", help="下载全部搜索结果")
    parser.add_argument(
        "-q",
        "--quality",
        default="mp3_128",
        choices=["mp3_128", "mp3_320", "m4a", "flac"],
        help="音质 (默认: mp3_128，失败时自动降级)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./downloads",
        help="下载保存目录 (默认: ./downloads)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互模式：搜索后手动选择要下载的歌曲（单次）",
    )
    parser.add_argument(
        "--exchange",
        action="store_true",
        help="交换模式：搜索 -> 按条目下载 -> 可回退重新搜索（循环，仅 -k 时默认开启）",
    )
    parser.add_argument(
        "--no-exchange",
        action="store_true",
        help="关闭交换模式，仅执行单次搜索",
    )
    parser.add_argument(
        "--credential",
        metavar="FILE",
        help="登录凭证文件 (默认自动读取平台对应 cred 文件)",
    )
    parser.add_argument(
        "--init-credential",
        metavar="FILE",
        help="生成 QQ音乐凭证文件模板",
    )
    parser.add_argument(
        "--login",
        choices=["qr", "phone", "password"],
        help="登录: qr/phone(仅QQ), password=用户名+密码",
    )
    parser.add_argument("--user", help="登录用户名")
    parser.add_argument("--password", help="登录密码")
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="跳过可下载状态检测",
    )
    parser.add_argument(
        "--only-downloadable",
        action="store_true",
        help="仅显示/下载当前账号权限下可获取链接的歌曲",
    )
    parser.add_argument(
        "--no-lyric",
        action="store_true",
        help="下载时不保存歌词 (.lrc)",
    )
    return parser.parse_args()


def print_results(songs: list[Song], *, keyword: str = "", platform: str = "qq") -> None:
    platform_name = PLATFORM_NAMES.get(platform, platform)
    title = f'[{platform_name}] 关键词 "{keyword}" ' if keyword else f"[{platform_name}] "
    print(f"\n{title}找到 {len(songs)} 首歌曲:\n")
    for index, song in enumerate(songs, start=1):
        print(song.display(index))
    print()


def print_exchange_help() -> None:
    print("下载操作:")
    print("  1        下载第 1 首")
    print("  1,3      下载第 1、3 首")
    print("  all      下载全部")
    print("  list     重新显示当前列表")
    print("  search   回到搜索（换关键词）")
    print("  quit     退出")
    print()


def parse_selection(choice: str, songs: list[Song]) -> list[Song] | None:
    choice = choice.strip().lower()
    if not choice:
        return None
    if choice == "all":
        return list(songs)

    selected: list[Song] = []
    seen: set[int] = set()
    for part in choice.split(","):
        part = part.strip()
        if not part.isdigit():
            return None
        idx = int(part)
        if idx < 1 or idx > len(songs) or idx in seen:
            continue
        seen.add(idx)
        selected.append(songs[idx - 1])
    return selected or None


def choose_interactive(songs: list[Song]) -> list[Song]:
    print("请输入要下载的序号 (多个用逗号分隔，如 1,3 或输入 all 下载全部，q 退出):")
    choice = input("> ").strip().lower()
    if choice in {"q", "quit", "exit"}:
        return []
    result = parse_selection(choice, songs)
    return result or []


def search_songs(client: MusicClient, keyword: str, args: argparse.Namespace) -> list[Song]:
    print(f'正在搜索: "{keyword}" ...')
    songs = client.search(keyword, limit=args.num)
    if not songs:
        return []

    if not args.no_probe:
        print("正在检测可下载状态...")
        songs = client.probe_downloadable(songs, quality=args.quality)

    if args.only_downloadable:
        songs = [s for s in songs if s.downloadable]

    return songs


def download_songs(
    client: MusicClient,
    songs: list[Song],
    output_dir: str,
    quality: str,
    *,
    with_lyric: bool = True,
) -> None:
    success = 0
    for song in songs:
        print(f"正在下载: {song.name} - {song.singer} ...")
        try:
            audio_path, lyric_path = client.download(
                song, output_dir, quality=quality, with_lyric=with_lyric
            )
            print(f"  ✓ 音频: {audio_path}")
            if with_lyric:
                if lyric_path:
                    print(f"  ✓ 歌词: {lyric_path}")
                else:
                    print("  - 歌词: 暂无")
            success += 1
        except DownloadError as exc:
            print(f"  ✗ 失败: {exc}")
        except Exception as exc:
            print(f"  ✗ 失败: {exc}")

    print(f"\n完成: 成功 {success}/{len(songs)} 首")


def handle_login(args: argparse.Namespace) -> int:
    cred_path = args.credential or str(default_credential_path(args.platform))
    login_mode = args.login
    if not login_mode:
        if args.user or args.password:
            login_mode = "password"
        elif args.platform == "qq":
            print("请指定登录方式: --login qr / phone / password", file=sys.stderr)
            return 1
        else:
            login_mode = "password"

    if args.platform == "qq" and login_mode not in {"qr", "phone", "password"}:
        print("QQ音乐支持: --login qr / phone / password", file=sys.stderr)
        return 1
    if args.platform in {"kugou", "kuwo"} and login_mode != "password":
        print(f"{PLATFORM_NAMES[args.platform]} 仅支持 --login password", file=sys.stderr)
        return 1

    try:
        if args.platform == "qq":
            run_qq_login(
                login_mode,
                username=args.user,
                password=args.password,
                path=cred_path,
            )
        elif args.platform == "kugou":
            run_kugou_login(
                login_mode,
                username=args.user,
                password=args.password,
                path=cred_path,
            )
        else:
            run_kuwo_login(
                login_mode,
                username=args.user,
                password=args.password,
                path=cred_path,
            )
        return 0
    except (QQLoginError, KugouLoginError, KuwoLoginError) as exc:
        print(f"登录失败: {exc}", file=sys.stderr)
        return 1


def build_client(args: argparse.Namespace) -> MusicClient:
    cred_path = resolve_credential_path(args.platform, args.credential)

    if args.platform == "kuwo":
        credential = None
        if cred_path:
            data = load_json_credential(cred_path)
            if data:
                credential = KuwoCredential.from_dict(data)
                print(f"已加载酷我音乐登录凭证: {cred_path}")
        return KuwoMusicClient(credential=credential)

    if args.platform == "kugou":
        credential = None
        if cred_path:
            data = load_json_credential(cred_path)
            if data:
                credential = KugouCredential.from_dict(data)
                print(f"已加载酷狗音乐登录凭证: {cred_path}")
        return KugouMusicClient(credential=credential)

    credential = None
    if cred_path:
        credential = load_credential_if_exists(cred_path)
        if credential:
            print(f"已加载 QQ音乐登录凭证: {cred_path}")
    return QQMusicClient(credential=credential)


def run_exchange_mode(client: MusicClient, args: argparse.Namespace) -> int:
    platform_name = PLATFORM_NAMES.get(args.platform, args.platform)
    print(f"=== {platform_name} 交换模式 ===")
    print("流程: [1] 搜索并显示结果  [2] 按序号下载  [3] 可回退重新搜索")
    if not resolve_credential_path(args.platform, args.credential):
        if args.platform == "qq":
            print("提示: QQ音乐 VIP 歌曲需先登录: python3 main.py -p qq --login qr")
        elif args.platform == "kugou":
            print("提示: 酷狗 VIP 歌曲可先登录: python3 main.py -p kugou --login password --user 用户名 --password 密码")
        elif args.platform == "kuwo":
            print("提示: 酷我 VIP 歌曲可先登录: python3 main.py -p kuwo --login password --user 用户名 --password 密码")
    print()

    keyword = args.keyword or ""

    while True:
        print("--- [1] 搜索 ---")
        if keyword:
            prompt = f'请输入关键词 (直接回车继续搜索 "{keyword}"): '
        else:
            prompt = "请输入关键词: "
        user_kw = input(prompt).strip()
        if user_kw.lower() in {"quit", "q", "exit", "退出"}:
            print("已退出。")
            return 0
        if user_kw:
            keyword = user_kw

        if not keyword:
            print("关键词不能为空。")
            continue

        try:
            songs = search_songs(client, keyword, args)
        except Exception as exc:
            print(f"搜索失败: {exc}", file=sys.stderr)
            continue

        if not songs:
            print("未找到相关歌曲，请换关键词重试。\n")
            continue

        print_results(songs, keyword=keyword, platform=args.platform)

        while True:
            print("--- [2] 下载 ---")
            print_exchange_help()
            choice = input("> ").strip().lower()

            if choice in {"quit", "q", "exit", "退出"}:
                print("已退出。")
                return 0
            if choice in {"search", "s", "back", "b", "重新搜索", "回退"}:
                print("\n回到搜索...\n")
                break
            if choice in {"list", "l", "列表"}:
                print_results(songs, keyword=keyword, platform=args.platform)
                continue

            selected = parse_selection(choice, songs)
            if not selected:
                print("无效输入，请参考上方命令说明。\n")
                continue

            download_songs(
                client,
                selected,
                args.output,
                args.quality,
                with_lyric=not args.no_lyric,
            )
            print("可继续输入序号下载，或输入 search 回到搜索。\n")


def run_once_mode(client: MusicClient, args: argparse.Namespace) -> int:
    if not args.keyword:
        print("请提供搜索关键词: -k \"关键词\"", file=sys.stderr)
        return 1

    try:
        songs = search_songs(client, args.keyword, args)
    except Exception as exc:
        print(f"搜索失败: {exc}", file=sys.stderr)
        return 1

    if not songs:
        print("未找到相关歌曲，请尝试其他关键词。")
        return 1

    print_results(songs, keyword=args.keyword, platform=args.platform)

    to_download: list[Song] = []
    if args.interactive:
        to_download = choose_interactive(songs)
    elif args.all:
        to_download = songs
    elif args.index is not None:
        if 1 <= args.index <= len(songs):
            to_download = [songs[args.index - 1]]
        else:
            print(f"无效序号: {args.index}，可选范围 1-{len(songs)}", file=sys.stderr)
            return 1
    else:
        downloadable = [s for s in songs if s.downloadable]
        if downloadable:
            print("提示: 标有 [可下载] 的歌曲可直接下载，例如:")
            print(
                f'  python3 main.py -p {args.platform} -k "{args.keyword}" '
                f"-i {songs.index(downloadable[0]) + 1}"
            )
        print("使用 --exchange 进入交换模式，或 -i/--all/--interactive 直接下载")
        return 0

    if not to_download:
        print("未选择任何歌曲。")
        return 0

    download_songs(
        client,
        to_download,
        args.output,
        args.quality,
        with_lyric=not args.no_lyric,
    )
    return 0


def should_use_exchange_mode(args: argparse.Namespace) -> bool:
    if args.no_exchange:
        return False
    if args.exchange:
        return True
    if args.interactive or args.all or args.index is not None:
        return False
    return True


def main() -> int:
    args = parse_args()

    if args.init_credential:
        save_credential_template(args.init_credential)
        print(f"已生成凭证模板: {args.init_credential}")
        print("也可使用登录命令自动获取凭证:")
        print("  python3 main.py --login qr")
        print("  python3 main.py --login phone --user 手机号")
        return 0

    if args.login or args.user:
        return handle_login(args)

    client = build_client(args)

    if should_use_exchange_mode(args):
        return run_exchange_mode(client, args)

    return run_once_mode(client, args)


if __name__ == "__main__":
    raise SystemExit(main())
