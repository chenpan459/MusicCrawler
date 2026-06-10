# -*- coding: utf-8 -*-
"""Concurrent song download orchestration."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from base_client import MusicClient
from song import DownloadError, Song

logger = logging.getLogger("musiccrawler")


@dataclass
class DownloadOutcome:
    song: Song
    ok: bool
    audio_path: str | None = None
    lyric_path: str | None = None
    error: str | None = None


def _download_one(
    client: MusicClient,
    song: Song,
    output_dir: str,
    quality: str,
    *,
    with_lyric: bool,
) -> DownloadOutcome:
    try:
        audio_path, lyric_path = client.download(
            song,
            output_dir,
            quality=quality,
            with_lyric=with_lyric,
        )
        return DownloadOutcome(
            song=song,
            ok=True,
            audio_path=audio_path,
            lyric_path=lyric_path,
        )
    except DownloadError as exc:
        logger.warning("download failed song=%s error=%s", song.mid, exc)
        return DownloadOutcome(song=song, ok=False, error=str(exc))
    except Exception as exc:
        logger.exception("download error song=%s", song.mid)
        return DownloadOutcome(song=song, ok=False, error=str(exc))


def _print_outcome(outcome: DownloadOutcome, *, with_lyric: bool) -> None:
    song = outcome.song
    print(f"正在下载: {song.name} - {song.singer} ...")
    if outcome.ok:
        print(f"  ✓ 音频: {outcome.audio_path}")
        if with_lyric:
            if outcome.lyric_path:
                print(f"  ✓ 歌词: {outcome.lyric_path}")
            else:
                print("  - 歌词: 暂无")
    else:
        print(f"  ✗ 失败: {outcome.error}")


def download_songs(
    client: MusicClient,
    songs: list[Song],
    output_dir: str,
    quality: str,
    *,
    workers: int = 1,
    with_lyric: bool = True,
) -> int:
    """Download songs sequentially or concurrently. Returns success count."""
    if not songs:
        return 0

    worker_count = max(1, workers)
    if worker_count == 1 or len(songs) == 1:
        success = 0
        for song in songs:
            outcome = _download_one(
                client, song, output_dir, quality, with_lyric=with_lyric
            )
            _print_outcome(outcome, with_lyric=with_lyric)
            if outcome.ok:
                success += 1
        print(f"\n完成: 成功 {success}/{len(songs)} 首")
        return success

    print(f"并发下载: {len(songs)} 首, workers={worker_count}")
    success = 0
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _download_one,
                client,
                song,
                output_dir,
                quality,
                with_lyric=with_lyric,
            ): song
            for song in songs
        }
        for future in as_completed(futures):
            outcome = future.result()
            _print_outcome(outcome, with_lyric=with_lyric)
            if outcome.ok:
                success += 1

    print(f"\n完成: 成功 {success}/{len(songs)} 首")
    return success
