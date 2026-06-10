# -*- coding: utf-8 -*-
"""Shared music client utilities and protocol."""

from __future__ import annotations

import os
import re
from typing import Protocol

from http_client import HttpSession
from song import DownloadError, Song


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


class BaseMusicClient:
    """Common helpers for platform clients."""

    platform: str = ""
    http: HttpSession

    def copy_song(self, song: Song, downloadable: bool) -> Song:
        return Song(
            id=song.id,
            mid=song.mid,
            name=song.name,
            singer=song.singer,
            downloadable=downloadable,
            platform=self.platform,
            meta=dict(song.meta),
        )

    @staticmethod
    def safe_filename(name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip() or "unknown"

    @staticmethod
    def quality_chain(quality: str, fallback: list[str]) -> list[str]:
        return [quality] + [q for q in fallback if q != quality]

    @staticmethod
    def default_ext(quality: str) -> str:
        if quality == "flac":
            return "flac"
        if quality == "m4a":
            return "m4a"
        return "mp3"

    def stream_to_file(self, url: str, filepath: str, *, min_size: int = 1024) -> None:
        response = self.http.get(url, stream=True)
        response.raise_for_status()
        with open(filepath, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        if os.path.getsize(filepath) < min_size:
            os.remove(filepath)
            raise DownloadError("下载文件过小，可能下载失败")

    def download_song_file(
        self,
        song: Song,
        output_dir: str,
        quality: str,
        *,
        resolve_url,
        save_lyric=None,
        filename: str | None = None,
        with_lyric: bool = True,
    ) -> tuple[str, str | None]:
        """Download audio (and optional lyric) using platform-specific resolvers."""
        url, ext = resolve_url(song, quality)
        safe_name = filename or self.safe_filename(f"{song.name} - {song.singer}")
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{safe_name}.{ext}")
        self.stream_to_file(url, filepath)
        lyric_path = save_lyric(song, output_dir, safe_name) if with_lyric and save_lyric else None
        return filepath, lyric_path
