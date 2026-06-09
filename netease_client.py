# -*- coding: utf-8 -*-
"""NetEase Cloud Music (music.163.com) search and download API client."""

from __future__ import annotations

import re
from typing import Any

import requests

from netease_crypto import encrypt_weapi
from netease_login import NeteaseCredential
from song import DownloadError, Song

BASE_URL = "https://music.163.com/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Origin": "https://music.163.com",
}

QUALITY_PROFILES = {
    "mp3_128": {"level": "standard", "encodeType": "mp3"},
    "mp3_320": {"level": "exhigh", "encodeType": "mp3"},
    "m4a": {"level": "higher", "encodeType": "aac"},
    "flac": {"level": "lossless", "encodeType": "flac"},
}

QUALITY_FALLBACK = ["mp3_128", "mp3_320", "m4a", "flac"]


class NeteaseMusicClient:
    """网易云音乐爬虫客户端."""

    def __init__(self, timeout: int = 30, credential: NeteaseCredential | None = None):
        self.timeout = timeout
        self.credential = credential
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.csrf_token = credential.csrf_token if credential else ""
        if credential:
            self._apply_credential(credential)
        else:
            self._bootstrap()

    def _apply_credential(self, credential: NeteaseCredential) -> None:
        self.csrf_token = credential.csrf_token
        for key, value in credential.cookies.items():
            self.session.cookies.set(key, value, domain=".163.com")

    def _bootstrap(self) -> None:
        self.session.get(BASE_URL, timeout=self.timeout)
        token = self.session.cookies.get("__csrf", domain=".163.com")
        if token:
            self.csrf_token = token

    def _post_weapi(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = data.copy()
        payload.setdefault("csrf_token", self.csrf_token)
        response = self.session.post(
            f"https://music.163.com{path}",
            params={"csrf_token": self.csrf_token},
            data=encrypt_weapi(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        token = self.session.cookies.get("__csrf", domain=".163.com")
        if token:
            self.csrf_token = token
        return result

    def search(self, keyword: str, limit: int = 20) -> list[Song]:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("搜索关键词不能为空")

        result = self._post_weapi(
            "/weapi/cloudsearch/pc",
            {
                "s": keyword,
                "type": "1",
                "offset": "0",
                "total": "true",
                "limit": str(min(limit, 50)),
            },
        )
        if result.get("code") != 200:
            raise RuntimeError(result.get("msg") or result.get("message") or "搜索失败")

        songs: list[Song] = []
        for item in result.get("result", {}).get("songs", []):
            songs.append(self._parse_song(item))
        return songs[:limit]

    def probe_downloadable(self, songs: list[Song], quality: str = "mp3_128") -> list[Song]:
        probed: list[Song] = []
        for song in songs:
            downloadable = self.is_downloadable(song.mid, quality=quality)
            probed.append(
                Song(
                    id=song.id,
                    mid=song.mid,
                    name=song.name,
                    singer=song.singer,
                    downloadable=downloadable,
                    platform="netease",
                    meta=dict(song.meta),
                )
            )
        return probed

    def is_downloadable(self, song_id: str, quality: str = "mp3_128") -> bool:
        try:
            self.resolve_download_url(song_id, quality=quality)
            return True
        except DownloadError:
            return False

    def _parse_song(self, item: dict[str, Any]) -> Song:
        song_id = str(item.get("id", ""))
        singers = item.get("ar") or item.get("artists") or []
        singer = "/".join(str(artist.get("name", "")) for artist in singers if artist.get("name"))
        return Song(
            id=song_id,
            mid=song_id,
            name=str(item.get("name", "未知歌曲")),
            singer=singer or "未知歌手",
            platform="netease",
            meta={
                "album": (item.get("al") or {}).get("name", ""),
                "duration": int(item.get("dt", 0) or 0),
            },
        )

    def _request_play_url(self, song_id: str, quality: str) -> tuple[str | None, str]:
        profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["mp3_128"])
        result = self._post_weapi(
            "/weapi/song/enhance/player/url/v1",
            {
                "ids": f"[{song_id}]",
                "level": profile["level"],
                "encodeType": profile["encodeType"],
            },
        )
        if result.get("code") != 200:
            return None, self._default_ext(quality)

        data = result.get("data") or []
        if not data:
            return None, self._default_ext(quality)
        item = data[0]
        url = item.get("url")
        if not url:
            return None, self._default_ext(quality)
        ext = str(item.get("type") or self._default_ext(quality))
        return url, ext

    def resolve_download_url(self, song_id: str, quality: str = "mp3_128") -> tuple[str, str]:
        qualities = [quality] + [q for q in QUALITY_FALLBACK if q != quality]
        for q in qualities:
            url, ext = self._request_play_url(song_id, q)
            if url:
                return url, ext
        raise DownloadError("无法获取网易云音乐下载链接，该歌曲可能受版权/VIP限制。")

    def get_lyric(self, song_id: str) -> str | None:
        result = self._post_weapi(
            "/weapi/song/lyric",
            {
                "id": song_id,
                "lv": -1,
                "kv": -1,
                "tv": -1,
            },
        )
        if result.get("code") != 200:
            return None
        lrc = (result.get("lrc") or {}).get("lyric", "")
        tlyric = (result.get("tlyric") or {}).get("lyric", "")
        if not lrc and not tlyric:
            return None
        if lrc and tlyric:
            return f"{lrc.rstrip()}\n\n{tlyric.lstrip()}"
        return lrc or tlyric

    def save_lyric(self, song: Song, output_dir: str, base_name: str) -> str | None:
        import os

        lyric = self.get_lyric(song.mid)
        if not lyric:
            return None
        os.makedirs(output_dir, exist_ok=True)
        lyric_path = os.path.join(output_dir, f"{base_name}.lrc")
        with open(lyric_path, "w", encoding="utf-8") as file:
            file.write(lyric)
        return lyric_path

    def download(
        self,
        song: Song,
        output_dir: str,
        quality: str = "mp3_128",
        filename: str | None = None,
        *,
        with_lyric: bool = True,
    ) -> tuple[str, str | None]:
        import os

        url, ext = self.resolve_download_url(song.mid, quality)
        safe_name = filename or self._safe_filename(f"{song.name} - {song.singer}")
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{safe_name}.{ext}")

        response = self.session.get(url, timeout=self.timeout, stream=True)
        response.raise_for_status()
        with open(filepath, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

        if os.path.getsize(filepath) < 1024:
            os.remove(filepath)
            raise DownloadError("下载文件过小，可能下载失败")

        lyric_path = self.save_lyric(song, output_dir, safe_name) if with_lyric else None
        return filepath, lyric_path

    @staticmethod
    def _default_ext(quality: str) -> str:
        if quality == "flac":
            return "flac"
        if quality == "m4a":
            return "m4a"
        return "mp3"

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip() or "unknown"
