# -*- coding: utf-8 -*-
"""QQ Music (y.qq.com) search and download API client."""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Any
from urllib.parse import quote

from base_client import BaseMusicClient
from credential import Credential, calc_g_tk
from http_client import ClientConfig, HttpSession
from song import DownloadError, Song

BASE_URL = "https://y.qq.com/"
SEARCH_URL = "https://c.y.qq.com/splcloud/fcgi-bin/smartbox_new.fcg"
VKEY_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
LYRIC_URL = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"

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
    "mp3_128": ("M500", "mp3"),
    "mp3_320": ("M800", "mp3"),
    "m4a": ("C400", "m4a"),
    "flac": ("F000", "flac"),
}

QUALITY_FALLBACK = ["mp3_128", "m4a", "mp3_320", "flac"]

# result=0 表示可下载；104003 表示版权/VIP 限制（需会员登录）
DOWNLOAD_BLOCKED_RESULTS = {104003}


class QQMusicClient(BaseMusicClient):
    """QQ音乐爬虫客户端."""

    platform = "qq"

    def __init__(
        self,
        timeout: int = 30,
        credential: Credential | None = None,
        *,
        config: ClientConfig | None = None,
    ):
        self.credential = credential
        self.config = config or ClientConfig(timeout=timeout)
        self.http = HttpSession(headers=DEFAULT_HEADERS, config=self.config)
        self._guid = str(uuid.uuid4().int)[:10]
        if credential:
            self._apply_credential(credential)

    def _apply_credential(self, credential: Credential) -> None:
        uin = credential.uin_str
        self.http.session.cookies.set("uin", uin, domain=".qq.com")
        self.http.session.cookies.set("qqmusic_uin", uin, domain=".qq.com")
        self.http.session.cookies.set("qqmusic_key", credential.musickey, domain=".qq.com")
        self.http.session.cookies.set("qm_keyst", credential.musickey, domain=".qq.com")

    def _uin_value(self) -> str | int:
        if self.credential:
            return self.credential.uin_str
        return "0"

    def search(self, keyword: str, limit: int = 20) -> list[Song]:
        """按关键词搜索歌曲."""
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("搜索关键词不能为空")

        songs: list[Song] = []
        seen: set[str] = set()

        smartbox_songs = self._search_smartbox(keyword)
        for item in smartbox_songs:
            mid = item.get("mid", "")
            if mid and mid not in seen:
                seen.add(mid)
                songs.append(self._parse_song(item))

        if len(songs) < limit:
            extra = self._search_mobile(keyword, limit - len(songs), seen)
            songs.extend(extra)

        return songs[:limit]

    def probe_downloadable(self, songs: list[Song], quality: str = "mp3_128") -> list[Song]:
        """检测每首歌是否可下载，批量请求减少 API 调用。"""
        if not songs:
            return []
        batch = self._batch_probe_vkey([song.mid for song in songs], quality)
        probed: list[Song] = []
        for song in songs:
            downloadable = batch.get(song.mid)
            if downloadable is None:
                downloadable = self.is_downloadable(song.mid, quality=quality)
            probed.append(self.copy_song(song, downloadable))
        return probed

    def _batch_probe_vkey(self, song_mids: list[str], quality: str) -> dict[str, bool]:
        if not song_mids or quality not in QUALITY_MAP:
            return {}
        prefix, ext = QUALITY_MAP[quality]
        filenames = [f"{prefix}{mid}{mid}.{ext}" for mid in song_mids]
        uin = self._uin_value()
        param: dict[str, Any] = {
            "guid": self._guid,
            "songmid": song_mids,
            "songtype": [0] * len(song_mids),
            "uin": str(uin),
            "filename": filenames,
            "ctx": 0,
        }
        if self.credential:
            param["loginflag"] = 1
        data = {
            "comm": self._build_comm(),
            "req_0": {
                "module": "music.vkey.GetVkey",
                "method": "UrlGetVkey",
                "param": param,
            },
        }
        url = f"{VKEY_URL}?format=json&data={quote(json.dumps(data, separators=(',', ':')))}"
        try:
            response = self.http.get(url)
            payload = response.json()
        except Exception:
            return {}
        mapping: dict[str, bool] = {}
        for item in payload.get("req_0", {}).get("data", {}).get("midurlinfo", []):
            mid = item.get("songmid", "")
            mapping[mid] = bool(item.get("purl")) and item.get("result", -1) not in DOWNLOAD_BLOCKED_RESULTS
        return mapping

    def is_downloadable(self, song_mid: str, quality: str = "mp3_128") -> bool:
        """快速检测歌曲当前是否可获取下载链接。"""
        try:
            self.resolve_download_url(song_mid, quality=quality)
            return True
        except DownloadError:
            return False

    def _build_comm(self) -> dict[str, Any]:
        if not self.credential:
            return {"uin": 0, "format": "json", "ct": 24, "cv": 0}

        uin = self.credential.uin_str
        comm_uin: str | int = int(uin) if uin.isdigit() else uin
        g_tk = calc_g_tk(self.credential.musickey)
        return {
            "uin": comm_uin,
            "format": "json",
            "ct": 24,
            "cv": 0,
            "platform": "yqq.json",
            "g_tk": g_tk,
            "g_tk_new_20200303": g_tk,
            "needNewCode": 1,
        }

    def _get_media_mid(self, song_mid: str) -> str | None:
        """查询歌曲真实媒体文件 ID（原版资源标识）。"""
        data = {
            "comm": self._build_comm(),
            "req": {
                "module": "music.trackInfo.UniformRuleCtrl",
                "method": "CgiGetTrackInfo",
                "param": {
                    "mids": [song_mid],
                    "types": [0],
                    "modify_stamp": [0],
                    "ctx": 0,
                    "client": 1,
                },
            },
        }
        url = f"{VKEY_URL}?format=json&data={quote(json.dumps(data, separators=(',', ':')))}"
        response = self.http.get(url)
        response.raise_for_status()
        tracks = response.json().get("req", {}).get("data", {}).get("tracks", [])
        if not tracks:
            return None
        file_info = tracks[0].get("file", {})
        if isinstance(file_info, dict):
            return file_info.get("media_mid") or None
        return None

    def _search_smartbox(self, keyword: str) -> list[dict[str, Any]]:
        url = f"{SEARCH_URL}?format=json&key={quote(keyword)}"
        response = self.http.get(url)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            return []
        data = payload.get("data", {})
        return data.get("song", {}).get("itemlist", [])

    def _search_mobile(
        self,
        keyword: str,
        limit: int,
        seen: set[str],
    ) -> list[Song]:
        """尝试通过移动端搜索接口获取更多结果（可能受风控影响）."""
        if limit <= 0:
            return []

        import random
        import time

        search_id = f"{int(time.time() * 1000)}{random.randint(1, 20)}"
        data = {
            "comm": {"ct": 11, "cv": 12030008, "v": 12030008, "uin": 0, "format": "json"},
            "req": {
                "module": "music.search.SearchCgiService",
                "method": "DoSearchForQQMusicMobile",
                "param": {
                    "searchid": search_id,
                    "query": keyword,
                    "search_type": 0,
                    "num_per_page": limit,
                    "page_num": 1,
                    "highlight": 1,
                    "grp": 1,
                },
            },
        }
        url = f"{VKEY_URL}?format=json&data={quote(json.dumps(data, separators=(',', ':')))}"
        mobile_headers = {
            **DEFAULT_HEADERS,
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 12; SM-G991B) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/100.0.4896.127 Mobile Safari/537.36"
            ),
        }
        response = self.http.get(url, headers=mobile_headers)
        response.raise_for_status()
        payload = response.json()

        songs: list[Song] = []
        body = payload.get("req", {}).get("data", {}).get("body", {})
        for item in body.get("item_song", []):
            mid = item.get("mid", "")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            singers = "/".join(s.get("name", "") for s in item.get("singer", []))
            songs.append(
                Song(
                    id=str(item.get("id", "")),
                    mid=mid,
                    name=item.get("title", item.get("name", "")),
                    singer=singers or "未知歌手",
                    platform="qq",
                )
            )
        return songs[:limit]

    def _parse_song(self, item: dict[str, Any]) -> Song:
        singer = item.get("singer", "")
        if isinstance(singer, list):
            singer = "/".join(s.get("name", "") for s in singer)
        return Song(
            id=str(item.get("id", "")),
            mid=item.get("mid", ""),
            name=item.get("name", ""),
            singer=singer or "未知歌手",
            platform="qq",
        )

    def get_download_url(
        self,
        song_mid: str,
        quality: str = "mp3_128",
    ) -> tuple[str | None, int, str]:
        """获取歌曲下载链接，返回 (url, result_code, extension)。"""
        if quality not in QUALITY_MAP:
            raise ValueError(f"不支持的音质: {quality}，可选: {', '.join(QUALITY_MAP)}")

        prefix, ext = QUALITY_MAP[quality]
        media_mid = self._get_media_mid(song_mid)
        if media_mid:
            filename = f"{prefix}{media_mid}.{ext}"
        else:
            filename = f"{prefix}{song_mid}{song_mid}.{ext}"

        uin = self._uin_value()
        param: dict[str, Any] = {
            "guid": self._guid,
            "songmid": [song_mid],
            "songtype": [0],
            "uin": str(uin),
            "filename": [filename],
            "ctx": 0,
        }
        if self.credential:
            param["loginflag"] = 1

        data = {
            "comm": self._build_comm(),
            "req_0": {
                "module": "music.vkey.GetVkey",
                "method": "UrlGetVkey",
                "param": param,
            },
        }
        url = f"{VKEY_URL}?format=json&data={quote(json.dumps(data, separators=(',', ':')))}"
        response = self.http.get(url)
        response.raise_for_status()
        payload = response.json()

        info = payload.get("req_0", {}).get("data", {})
        mid_info = info.get("midurlinfo", [{}])[0]
        result_code = mid_info.get("result", -1)
        purl = mid_info.get("purl", "")
        if not purl:
            return None, result_code, ext

        sip = info.get("sip") or ["http://isure.stream.qqmusic.qq.com/"]
        base = sip[0] if sip else "http://isure.stream.qqmusic.qq.com/"
        return base + purl, result_code, ext

    def resolve_download_url(
        self,
        song_mid: str,
        quality: str = "mp3_128",
    ) -> tuple[str, str]:
        """按音质优先级解析可下载链接，返回 (url, extension)。"""
        qualities = self.quality_chain(quality, QUALITY_FALLBACK)
        last_code = -1
        for q in qualities:
            url, code, ext = self.get_download_url(song_mid, q)
            last_code = code
            if url:
                return url, ext
        if not self.credential:
            raise DownloadError(
                "原版资源受版权/VIP保护 (result=104003)。"
                "QQ音乐不会公开原版直链，下载地址必须由服务端按账号权限签发。"
                "请使用 --credential 导入已开通绿钻的QQ音乐账号 Cookie 后重试。"
            )
        raise DownloadError(
            "原版资源下载被拒绝 (result=104003)。"
            "请确认: 1) 账号已开通绿钻/付费包  2) Cookie 未过期  3) 该曲支持下载"
        )

    def get_lyric(self, song_mid: str) -> str | None:
        """获取歌曲 LRC 歌词文本。"""
        url = (
            f"{LYRIC_URL}?songmid={quote(song_mid)}"
            "&format=json&nobase64=1&g_tk=5381"
        )
        response = self.http.get(url)
        response.raise_for_status()
        payload = response.json()
        if payload.get("retcode") == 0 or payload.get("code") == 0:
            lyric = payload.get("lyric", "")
            if isinstance(lyric, str) and lyric.strip():
                return lyric.strip()

        data = {
            "comm": self._build_comm(),
            "req": {
                "module": "music.musichallSong.PlayLyricInfo",
                "method": "GetPlayLyricInfo",
                "param": {
                    "songMid": song_mid,
                    "crypt": 0,
                    "trans": 0,
                    "roma": 0,
                    "qrc": 0,
                    "type": 1,
                },
            },
        }
        fallback_url = (
            f"{VKEY_URL}?format=json&data={quote(json.dumps(data, separators=(',', ':')))}"
        )
        response = self.http.get(fallback_url)
        response.raise_for_status()
        lyric = response.json().get("req", {}).get("data", {}).get("lyric", "")
        if not lyric:
            return None
        if lyric.startswith("W3") or lyric.startswith("["):
            try:
                decoded = base64.b64decode(lyric).decode("utf-8").strip()
                return decoded or None
            except Exception:
                return lyric.strip() or None
        return lyric.strip() or None

    def save_lyric(self, song: Song, output_dir: str, base_name: str) -> str | None:
        """保存歌词文件，返回 .lrc 路径；无歌词时返回 None。"""
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
        """下载歌曲到指定目录，返回 (音频路径, 歌词路径)。"""
        return self.download_song_file(
            song,
            output_dir,
            quality,
            resolve_url=self._resolve_song_url,
            save_lyric=self.save_lyric,
            filename=filename,
            with_lyric=with_lyric,
        )
