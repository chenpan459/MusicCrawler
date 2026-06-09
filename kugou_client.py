# -*- coding: utf-8 -*-
"""Kugou Music (kugou.com) search and download API client."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import quote

import requests

from kugou_login import KugouCredential
from song import DownloadError, Song

BASE_URL = "https://www.kugou.com/"
SEARCH_URL = "http://mobilecdn.kugou.com/api/v3/search/song"
TRACKER_URLS = [
    "http://trackercdn.kugou.com/i/v2/?appid=1005&pid=2&cmd=25&behavior=play",
    "http://trackercdnbj.kugou.com/i/v2/?cmd=23&pid=1&behavior=download",
    "http://trackercdn.kugou.com/i/v2/?cmd=23&pid=1&behavior=download",
]
LYRIC_SEARCH_URL = "https://lyrics.kugou.com/search"
LYRIC_DOWNLOAD_URL = "https://lyrics.kugou.com/download"
SIGN_SALT = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept": "*/*",
}

QUALITY_HASH_KEYS = {
    "mp3_128": "hash",
    "mp3_320": "hash_320",
    "m4a": "hash",
    "flac": "hash_sq",
}

QUALITY_FALLBACK = ["mp3_128", "mp3_320", "m4a", "flac"]


class KugouMusicClient:
    """酷狗音乐爬虫客户端."""

    def __init__(self, timeout: int = 30, credential: KugouCredential | None = None):
        self.timeout = timeout
        self.credential = credential
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if credential:
            self._apply_credential(credential)

    def _apply_credential(self, credential: KugouCredential) -> None:
        self.session.cookies.set("token", credential.token, domain=".kugou.com")
        self.session.cookies.set("userid", credential.userid, domain=".kugou.com")
        if credential.vip_token:
            self.session.cookies.set("vip_token", credential.vip_token, domain=".kugou.com")
        if credential.mid:
            self.session.cookies.set("KUGOU_API_MID", credential.mid, domain=".kugou.com")
        if credential.dfid:
            self.session.cookies.set("dfid", credential.dfid, domain=".kugou.com")

    def _auth_params(self) -> tuple[str, str]:
        if self.credential:
            return self.credential.token, self.credential.userid
        return "", "0"

    def search(self, keyword: str, limit: int = 20) -> list[Song]:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("搜索关键词不能为空")

        page_size = min(limit, 30)
        url = (
            f"{SEARCH_URL}?format=json&keyword={quote(keyword)}"
            f"&page=1&pagesize={page_size}&showtype=1"
        )
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 1:
            return []

        songs: list[Song] = []
        for item in payload.get("data", {}).get("info", []):
            songs.append(self._parse_song(item))
        return songs[:limit]

    def probe_downloadable(self, songs: list[Song], quality: str = "mp3_128") -> list[Song]:
        probed: list[Song] = []
        for song in songs:
            downloadable = self.is_downloadable(song, quality=quality)
            probed.append(
                Song(
                    id=song.id,
                    mid=song.mid,
                    name=song.name,
                    singer=song.singer,
                    downloadable=downloadable,
                    platform="kugou",
                    meta=dict(song.meta),
                )
            )
        return probed

    def is_downloadable(self, song: Song, quality: str = "mp3_128") -> bool:
        try:
            self.resolve_download_url(song, quality=quality)
            return True
        except DownloadError:
            return False

    def _parse_song(self, item: dict[str, Any]) -> Song:
        file_hash = str(item.get("hash", "")).lower()
        album_audio_id = str(item.get("album_audio_id", ""))
        singer = self._clean_text(item.get("singername", ""))
        name = self._clean_text(item.get("songname", ""))
        return Song(
            id=album_audio_id,
            mid=file_hash,
            name=name or "未知歌曲",
            singer=singer or "未知歌手",
            platform="kugou",
            meta={
                "hash": file_hash,
                "hash_320": str(item.get("320hash", "")).lower(),
                "hash_sq": str(item.get("sqhash", "")).lower(),
                "album_audio_id": album_audio_id,
                "album_id": str(item.get("album_id", "")),
                "duration": int(item.get("duration", 0) or 0),
            },
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    def _pick_hash(self, song: Song, quality: str) -> str:
        meta = song.meta or {}
        key = QUALITY_HASH_KEYS.get(quality, "hash")
        selected = str(meta.get(key, "")).lower()
        if selected:
            return selected
        return str(meta.get("hash", song.mid)).lower()

    @staticmethod
    def _tracker_key(file_hash: str) -> str:
        return hashlib.md5(f"{file_hash}kgcloudv2".encode()).hexdigest()

    def _request_tracker(self, file_hash: str) -> str | None:
        file_hash = file_hash.lower()
        key = self._tracker_key(file_hash)
        for base in TRACKER_URLS:
            url = f"{base}&hash={file_hash}&key={key}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != 1:
                continue
            download_url = payload.get("url")
            if isinstance(download_url, list):
                download_url = download_url[0] if download_url else ""
            if isinstance(download_url, str) and download_url.startswith("http"):
                return download_url
        return None

    def _request_songinfo(self, song: Song) -> str | None:
        album_audio_id = str(song.meta.get("album_audio_id", song.id))
        token, userid = self._auth_params()
        mid = (
            self.credential.mid
            if self.credential and self.credential.mid
            else hashlib.md5(str(time.time()).encode()).hexdigest()
        )
        dfid = self.credential.dfid if self.credential else "-"
        clienttime = str(int(time.time() * 1000))
        signature = hashlib.md5(
            "".join(
                [
                    SIGN_SALT,
                    "appid=1014",
                    f"clienttime={clienttime}",
                    "clientver=20000",
                    f"dfid={dfid}",
                    f"encode_album_audio_id={album_audio_id}",
                    f"mid={mid}",
                    "platid=4",
                    "srcappid=2919",
                    f"token={token}",
                    f"userid={userid}",
                    f"uuid={mid}",
                    SIGN_SALT,
                ]
            ).encode()
        ).hexdigest()
        params = {
            "srcappid": "2919",
            "clientver": "20000",
            "clienttime": clienttime,
            "mid": mid,
            "uuid": mid,
            "dfid": dfid,
            "appid": "1014",
            "platid": "4",
            "encode_album_audio_id": album_audio_id,
            "token": token,
            "userid": userid,
            "signature": signature,
        }
        response = self.session.get(
            "https://wwwapi.kugou.com/play/songinfo",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 1:
            return None
        play_url = payload.get("data", {}).get("play_url", "")
        return play_url if play_url else None

    def resolve_download_url(self, song: Song, quality: str = "mp3_128") -> tuple[str, str]:
        qualities = [quality] + [q for q in QUALITY_FALLBACK if q != quality]
        for q in qualities:
            file_hash = self._pick_hash(song, q)
            if not file_hash:
                continue
            url = self._request_tracker(file_hash)
            if not url and q == quality:
                url = self._request_songinfo(song)
            if url:
                return url, self._guess_extension(q, url)
        raise DownloadError("无法获取酷狗音乐下载链接，该歌曲可能受版权/VIP限制。")

    def get_lyric(self, song: Song) -> str | None:
        meta = song.meta or {}
        file_hash = str(meta.get("hash", song.mid)).lower()
        album_audio_id = str(meta.get("album_audio_id", song.id))
        duration = int(meta.get("duration", 0) or 0) * 1000
        search_url = (
            f"{LYRIC_SEARCH_URL}?ver=1&man=yes&client=pc&keyword="
            f"&duration={duration}&hash={file_hash}&album_audio_id={album_audio_id}"
        )
        response = self.session.get(search_url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates", [])
        if not candidates:
            return None

        candidate = candidates[0]
        lyric_id = candidate.get("id")
        accesskey = candidate.get("accesskey", "")
        if not lyric_id or not accesskey:
            return None

        download_url = (
            f"{LYRIC_DOWNLOAD_URL}?ver=1&client=pc&id={lyric_id}"
            f"&accesskey={accesskey}&fmt=lrc&charset=utf8"
        )
        lyric_response = self.session.get(download_url, timeout=self.timeout)
        lyric_response.raise_for_status()
        lyric_payload = lyric_response.json()
        content = lyric_payload.get("content", "")
        if not content:
            return None

        try:
            return base64.b64decode(content).decode("utf-8")
        except Exception:
            return content

    def save_lyric(self, song: Song, output_dir: str, base_name: str) -> str | None:
        import os

        lyric = self.get_lyric(song)
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

        url, ext = self.resolve_download_url(song, quality)
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
    def _guess_extension(quality: str, url: str) -> str:
        lowered = url.lower()
        if ".flac" in lowered:
            return "flac"
        if ".m4a" in lowered or ".aac" in lowered:
            return "m4a"
        return KugouMusicClient._default_ext(quality)

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip() or "unknown"
