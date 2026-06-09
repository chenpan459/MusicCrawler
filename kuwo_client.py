# -*- coding: utf-8 -*-
"""Kuwo Music (kuwo.cn) search and download API client."""

from __future__ import annotations

import ast
import html
import json
import re
from typing import Any
from urllib.parse import quote

import requests

from kuwo_login import KuwoCredential, _calc_secret, _reqid_factory, find_iuvt_cookie
from song import DownloadError, Song

BASE_URL = "https://www.kuwo.cn/"
SEARCH_URL = "https://search.kuwo.cn/r.s"
DOWNLOAD_URL = "https://antiserver.kuwo.cn/anti.s"
LYRIC_URL = "https://www.kuwo.cn/openapi/v1/www/lyric/getlyric"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept": "*/*",
}

QUALITY_MAP = {
    "mp3_128": ("mp3", ""),
    "mp3_320": ("mp3", "320kmp3"),
    "m4a": ("aac", ""),
    "flac": ("mp3", "2000kflac"),
}

QUALITY_FALLBACK = ["mp3_128", "mp3_320", "m4a", "flac"]


class KuwoMusicClient:
    """酷我音乐爬虫客户端."""

    def __init__(self, timeout: int = 30, credential: KuwoCredential | None = None):
        self.timeout = timeout
        self.credential = credential
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._gen_reqid = _reqid_factory()
        if credential:
            self._apply_credential(credential)

    def _apply_credential(self, credential: KuwoCredential) -> None:
        for key, value in credential.cookies.items():
            self.session.cookies.set(key, value, domain=".kuwo.cn")
        cookie = find_iuvt_cookie(credential.cookies)
        if cookie:
            key, value = cookie
            self.session.headers["Secret"] = _calc_secret(value, key)

    def _ensure_secret(self) -> None:
        if "Secret" in self.session.headers:
            return
        self.session.get(BASE_URL, timeout=self.timeout)
        cookie = find_iuvt_cookie(self.session.cookies.get_dict())
        if cookie:
            key, value = cookie
            self.session.headers["Secret"] = _calc_secret(value, key)

    def search(self, keyword: str, limit: int = 20) -> list[Song]:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("搜索关键词不能为空")

        page_size = min(limit, 50)
        url = (
            f"{SEARCH_URL}?all={quote(keyword)}&ft=music&itemset=web_2013"
            f"&client=kt&pn=0&rn={page_size}&rformat=json&encoding=utf8"
        )
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = ast.literal_eval(response.text)
        songs: list[Song] = []
        for item in payload.get("abslist", []):
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
                    platform="kuwo",
                )
            )
        return probed

    def is_downloadable(self, music_id: str, quality: str = "mp3_128") -> bool:
        try:
            self.resolve_download_url(music_id, quality=quality)
            return True
        except DownloadError:
            return False

    def _parse_song(self, item: dict[str, Any]) -> Song:
        music_id = str(item.get("DC_TARGETID") or item.get("MUSICRID", "").replace("MUSIC_", ""))
        name = self._clean_text(item.get("SONGNAME", ""))
        singer = self._clean_text(item.get("ARTIST", ""))
        return Song(
            id=music_id,
            mid=music_id,
            name=name or "未知歌曲",
            singer=singer or "未知歌手",
            platform="kuwo",
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        text = html.unescape(text)
        text = text.replace("\\u0026", "&").replace("\\&", "&").replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _request_vip_play_url(self, music_id: str) -> str | None:
        self._ensure_secret()
        url = "https://www.kuwo.cn/api/v1/www/music/playUrl"
        params = {
            "mid": music_id,
            "type": "music",
            "httpsStatus": "1",
            "reqId": self._gen_reqid(),
            "plat": "web_www",
            "from": "",
        }
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            return None
        play_url = payload.get("data", {}).get("url", "")
        return play_url if play_url else None

    def get_download_url(
        self,
        music_id: str,
        quality: str = "mp3_128",
    ) -> tuple[str | None, str]:
        if quality not in QUALITY_MAP:
            raise ValueError(f"不支持的音质: {quality}，可选: {', '.join(QUALITY_MAP)}")

        if self.credential:
            vip_url = self._request_vip_play_url(music_id)
            if vip_url:
                return vip_url, self._guess_extension(quality, vip_url)

        fmt, br = QUALITY_MAP[quality]
        params = f"type=convert_url3&rid=MUSIC_{music_id}&format={fmt}&response=url"
        if br:
            params += f"&br={br}"
        url = f"{DOWNLOAD_URL}?{params}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        text = response.text.strip()
        if text.startswith("{"):
            try:
                payload = json.loads(text)
                download_url = payload.get("url", "")
                if download_url:
                    ext = self._guess_extension(quality, download_url)
                    return download_url, ext
            except json.JSONDecodeError:
                pass
        if text.startswith("http"):
            return text, self._default_ext(quality)
        return None, self._default_ext(quality)

    def resolve_download_url(self, music_id: str, quality: str = "mp3_128") -> tuple[str, str]:
        qualities = [quality] + [q for q in QUALITY_FALLBACK if q != quality]
        for q in qualities:
            url, ext = self.get_download_url(music_id, q)
            if url:
                return url, ext
        raise DownloadError("无法获取酷我音乐下载链接，该歌曲可能不可用或受版权限制。")

    def get_lyric(self, music_id: str) -> str | None:
        url = f"{LYRIC_URL}?musicId={music_id}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        lrclist = payload.get("data", {}).get("lrclist", [])
        if not lrclist:
            return None
        return self._lrclist_to_lrc(lrclist)

    @staticmethod
    def _lrclist_to_lrc(lrclist: list[dict[str, Any]]) -> str:
        lines = ["[by:MusicCrawler]"]
        for item in lrclist:
            lyric = str(item.get("lineLyric", "")).strip()
            if not lyric:
                continue
            try:
                seconds = float(item.get("time", 0))
            except (TypeError, ValueError):
                seconds = 0.0
            minutes = int(seconds // 60)
            secs = seconds % 60
            lines.append(f"[{minutes:02d}:{secs:05.2f}]{lyric}")
        return "\n".join(lines) + "\n"

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
        if quality == "m4a":
            return "m4a"
        if quality == "flac":
            return "flac"
        return "mp3"

    @staticmethod
    def _guess_extension(quality: str, url: str) -> str:
        lowered = url.lower()
        if ".flac" in lowered:
            return "flac"
        if ".m4a" in lowered or ".aac" in lowered:
            return "m4a"
        return KuwoMusicClient._default_ext(quality)

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip() or "unknown"
