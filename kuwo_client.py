# -*- coding: utf-8 -*-
"""Kuwo Music (kuwo.cn) search and download API client."""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote

from base_client import BaseMusicClient
from crypto.kuwo_secret import calc_secret, find_iuvt_cookie, reqid_factory
from http_client import ClientConfig, HttpSession
from kuwo_login import KuwoCredential
from kuwo_parse import parse_kuwo_search_payload
from song import DownloadError, Song

BASE_URL = "https://www.kuwo.cn/"
SEARCH_URL = "https://search.kuwo.cn/r.s"
DOWNLOAD_URL = "https://antiserver.kuwo.cn/anti.s"
LYRIC_URL = "https://www.kuwo.cn/openapi/v1/www/lyric/getlyric"

DEFAULT_HEADERS = {
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


class KuwoMusicClient(BaseMusicClient):
    """酷我音乐爬虫客户端."""

    platform = "kuwo"

    def __init__(
        self,
        timeout: int = 30,
        credential: KuwoCredential | None = None,
        *,
        config: ClientConfig | None = None,
    ):
        self.credential = credential
        self.config = config or ClientConfig(timeout=timeout)
        self.http = HttpSession(headers=DEFAULT_HEADERS, config=self.config)
        self._gen_reqid = reqid_factory()
        if credential:
            self._apply_credential(credential)

    def _apply_credential(self, credential: KuwoCredential) -> None:
        for key, value in credential.cookies.items():
            self.http.session.cookies.set(key, value, domain=".kuwo.cn")
        cookie = find_iuvt_cookie(credential.cookies)
        if cookie:
            key, value = cookie
            self.http.session.headers["Secret"] = calc_secret(value, key)

    def _ensure_secret(self) -> None:
        if "Secret" in self.http.session.headers:
            return
        self.http.get(BASE_URL)
        cookie = find_iuvt_cookie(self.http.session.cookies.get_dict())
        if cookie:
            key, value = cookie
            self.http.session.headers["Secret"] = calc_secret(value, key)

    def search(self, keyword: str, limit: int = 20) -> list[Song]:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("搜索关键词不能为空")

        page_size = min(limit, 50)
        url = (
            f"{SEARCH_URL}?all={quote(keyword)}&ft=music&itemset=web_2013"
            f"&client=kt&pn=0&rn={page_size}&rformat=json&encoding=utf8"
        )
        response = self.http.get(url)
        payload = parse_kuwo_search_payload(response.text)
        songs: list[Song] = []
        for item in payload.get("abslist", []):
            songs.append(self._parse_song(item))
        return songs[:limit]

    @staticmethod
    def _guess_from_pay_meta(meta: dict, *, has_login: bool) -> bool | None:
        tpay = int(meta.get("tpay", -1))
        fee_song = int(meta.get("fee_song", -1))
        if tpay == 0 or fee_song == 0:
            return False
        if (tpay == 1 or fee_song == 1) and not has_login:
            return True
        if not has_login and tpay in {2, 3}:
            return False
        return None

    def _batch_probe_download(self, music_ids: list[str], quality: str) -> dict[str, bool]:
        mapping: dict[str, bool] = {}
        for music_id in dict.fromkeys(mid for mid in music_ids if mid):
            mapping[music_id] = self._probe_single_quality(music_id, quality)
        return mapping

    def _probe_single_quality(self, music_id: str, quality: str) -> bool:
        try:
            url, _ = self.get_download_url(music_id, quality)
            return bool(url)
        except ValueError:
            return False

    def probe_downloadable(self, songs: list[Song], quality: str = "mp3_128") -> list[Song]:
        has_login = self.credential is not None
        probed: list[Song] = []
        need_api: list[Song] = []

        for song in songs:
            guess = self._guess_from_pay_meta(song.meta, has_login=has_login)
            if guess is not None:
                probed.append(self.copy_song(song, guess))
            else:
                need_api.append(song)

        if need_api:
            batch = self._batch_probe_download([song.mid for song in need_api], quality)
            for song in need_api:
                downloadable = batch.get(song.mid, False)
                probed.append(self.copy_song(song, downloadable))

        return probed

    def is_downloadable(self, music_id: str, quality: str = "mp3_128") -> bool:
        return self._probe_single_quality(music_id, quality)

    def _parse_song(self, item: dict[str, Any]) -> Song:
        music_id = str(item.get("DC_TARGETID") or item.get("MUSICRID", "").replace("MUSIC_", ""))
        name = self._clean_text(item.get("SONGNAME", ""))
        singer = self._clean_text(item.get("ARTIST", ""))
        pay_info = item.get("payInfo") or {}
        fee_type = pay_info.get("feeType") or {}
        return Song(
            id=music_id,
            mid=music_id,
            name=name or "未知歌曲",
            singer=singer or "未知歌手",
            platform="kuwo",
            meta={
                "tpay": int(item.get("tpay", -1) or -1),
                "fee_song": int(fee_type.get("song", -1) or -1),
            },
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
        response = self.http.get(url, params=params)
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
        response = self.http.get(url)

        text = response.text.strip()
        if text.startswith("{"):
            try:
                payload = json.loads(text)
                download_url = payload.get("url", "")
                if download_url:
                    return download_url, self._guess_extension(quality, download_url)
            except json.JSONDecodeError:
                pass
        if text.startswith("http"):
            return text, self._default_ext(quality)
        return None, self._default_ext(quality)

    def resolve_download_url(self, music_id: str, quality: str = "mp3_128") -> tuple[str, str]:
        qualities = self.quality_chain(quality, QUALITY_FALLBACK)
        for q in qualities:
            url, ext = self.get_download_url(music_id, q)
            if url:
                return url, ext
        raise DownloadError("无法获取酷我音乐下载链接，该歌曲可能不可用或受版权限制。")

    def get_lyric(self, music_id: str) -> str | None:
        url = f"{LYRIC_URL}?musicId={music_id}"
        response = self.http.get(url)
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
    def _guess_extension(quality: str, url: str) -> str:
        lowered = url.lower()
        if ".flac" in lowered:
            return "flac"
        if ".m4a" in lowered or ".aac" in lowered:
            return "m4a"
        return BaseMusicClient.default_ext(quality)
