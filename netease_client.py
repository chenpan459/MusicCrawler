# -*- coding: utf-8 -*-
"""NetEase Cloud Music (music.163.com) search and download API client."""

from __future__ import annotations

import json
import re
from typing import Any

from base_client import BaseMusicClient
from crypto.netease_weapi import encrypt_weapi
from http_client import ClientConfig, HttpSession
from netease_login import NeteaseCredential
from song import DownloadError, Song

BASE_URL = "https://music.163.com/"

DEFAULT_HEADERS = {
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

# fee: 0/8 通常可免费获取；1 为 VIP；4 为数字专辑
FREE_FEE_VALUES = {0, 8}


class NeteaseMusicClient(BaseMusicClient):
    """网易云音乐爬虫客户端."""

    platform = "netease"

    def __init__(
        self,
        timeout: int = 30,
        credential: NeteaseCredential | None = None,
        *,
        config: ClientConfig | None = None,
    ):
        self.credential = credential
        self.config = config or ClientConfig(timeout=timeout)
        self.http = HttpSession(headers=DEFAULT_HEADERS, config=self.config)
        self.csrf_token = credential.csrf_token if credential else ""
        if credential:
            self._apply_credential(credential)
        else:
            self._bootstrap()

    def _apply_credential(self, credential: NeteaseCredential) -> None:
        self.csrf_token = credential.csrf_token
        for key, value in credential.cookies.items():
            self.http.session.cookies.set(key, value, domain=".163.com")

    def _bootstrap(self) -> None:
        self.http.get(BASE_URL)
        token = self.http.session.cookies.get("__csrf", domain=".163.com")
        if token:
            self.csrf_token = token

    def _post_weapi(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = data.copy()
        payload.setdefault("csrf_token", self.csrf_token)
        response = self.http.post(
            f"https://music.163.com{path}",
            params={"csrf_token": self.csrf_token},
            data=encrypt_weapi(payload),
        )
        result = response.json()
        token = self.http.session.cookies.get("__csrf", domain=".163.com")
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

    @staticmethod
    def _guess_from_fee(fee: int, *, has_login: bool) -> bool | None:
        if fee in FREE_FEE_VALUES:
            return True
        if fee == 1 and not has_login:
            return False
        return None

    def probe_downloadable(self, songs: list[Song], quality: str = "mp3_128") -> list[Song]:
        has_login = self.credential is not None
        probed: list[Song] = []
        need_api: list[Song] = []

        for song in songs:
            fee = int(song.meta.get("fee", -1))
            guess = self._guess_from_fee(fee, has_login=has_login)
            if guess is not None:
                probed.append(self.copy_song(song, guess))
            else:
                need_api.append(song)

        if need_api:
            batch = self._batch_probe([s.mid for s in need_api], quality)
            for song in need_api:
                downloadable = batch.get(song.mid)
                if downloadable is None:
                    downloadable = self.is_downloadable(song.mid, quality=quality)
                probed.append(self.copy_song(song, downloadable))

        return probed

    def _batch_probe(self, song_ids: list[str], quality: str) -> dict[str, bool]:
        if not song_ids:
            return {}
        profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["mp3_128"])
        result = self._post_weapi(
            "/weapi/song/enhance/player/url/v1",
            {
                "ids": json.dumps([int(sid) for sid in song_ids]),
                "level": profile["level"],
                "encodeType": profile["encodeType"],
            },
        )
        mapping: dict[str, bool] = {}
        if result.get("code") != 200:
            return mapping
        for item in result.get("data") or []:
            sid = str(item.get("id", ""))
            mapping[sid] = bool(item.get("url"))
        return mapping

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
                "fee": int(item.get("fee", -1)),
            },
        )

    def _request_play_url(self, song_id: str, quality: str) -> tuple[str | None, str]:
        batch = self._batch_probe([song_id], quality)
        if batch.get(song_id):
            profile = QUALITY_PROFILES.get(quality, QUALITY_PROFILES["mp3_128"])
            result = self._post_weapi(
                "/weapi/song/enhance/player/url/v1",
                {
                    "ids": f"[{song_id}]",
                    "level": profile["level"],
                    "encodeType": profile["encodeType"],
                },
            )
            if result.get("code") == 200:
                data = result.get("data") or []
                if data and data[0].get("url"):
                    item = data[0]
                    return item["url"], str(item.get("type") or self._default_ext(quality))
        return None, self._default_ext(quality)

    def resolve_download_url(self, song_id: str, quality: str = "mp3_128") -> tuple[str, str]:
        qualities = self.quality_chain(quality, QUALITY_FALLBACK)
        for q in qualities:
            url, ext = self._request_play_url(song_id, q)
            if url:
                return url, ext
        raise DownloadError("无法获取网易云音乐下载链接，该歌曲可能受版权/VIP限制。")

    def get_lyric(self, song_id: str) -> str | None:
        result = self._post_weapi(
            "/weapi/song/lyric",
            {"id": song_id, "lv": -1, "kv": -1, "tv": -1},
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

    def _resolve_song_url(self, song: Song, quality: str) -> tuple[str, str]:
        return self.resolve_download_url(song.mid, quality)

    def download(
        self,
        song: Song,
        output_dir: str,
        quality: str = "mp3_128",
        filename: str | None = None,
        *,
        with_lyric: bool = True,
    ) -> tuple[str, str | None]:
        return self.download_song_file(
            song,
            output_dir,
            quality,
            resolve_url=self._resolve_song_url,
            save_lyric=self.save_lyric,
            filename=filename,
            with_lyric=with_lyric,
        )

    @staticmethod
    def _default_ext(quality: str) -> str:
        return BaseMusicClient.default_ext(quality)
