# -*- coding: utf-8 -*-
"""Verify platform credentials after load."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote

from credential import Credential, calc_g_tk
from crypto.netease_weapi import encrypt_weapi
from http_client import ClientConfig, HttpSession
from kugou_login import KugouCredential
from kuwo_login import KuwoCredential
from netease_login import NeteaseCredential

logger = logging.getLogger("musiccrawler")


def verify_qq_credential(credential: Credential, config: ClientConfig) -> bool:
    if not credential.musickey or not credential.uin_str:
        return False
    http = HttpSession(config=config)
    uin = credential.uin_str
    g_tk = calc_g_tk(credential.musickey)
    http.session.cookies.set("uin", uin, domain=".qq.com")
    http.session.cookies.set("qqmusic_key", credential.musickey, domain=".qq.com")
    comm_uin: str | int = int(uin) if uin.isdigit() else uin
    data = {
        "comm": {
            "uin": comm_uin,
            "format": "json",
            "ct": 24,
            "cv": 0,
            "g_tk": g_tk,
            "g_tk_new_20200303": g_tk,
        },
        "req": {
            "module": "music.userCenter.UserInfo",
            "method": "GetUserInfo",
            "param": {"uin": uin},
        },
    }
    url = (
        "https://u.y.qq.com/cgi-bin/musicu.fcg?format=json&data="
        + quote(json.dumps(data, separators=(",", ":")))
    )
    try:
        response = http.get(url, headers={"Referer": "https://y.qq.com/"})
        payload = response.json()
        return payload.get("req", {}).get("code", -1) == 0
    except Exception as exc:
        logger.debug("QQ credential verify failed: %s", exc)
        return False


def verify_kugou_credential(credential: KugouCredential, config: ClientConfig) -> bool:
    if not credential.token or not credential.userid:
        return False
    http = HttpSession(config=config)
    http.session.cookies.set("token", credential.token, domain=".kugou.com")
    http.session.cookies.set("userid", credential.userid, domain=".kugou.com")
    try:
        response = http.get(
            "https://gateway.kugou.com/v3/user/info",
            headers={"x-router": "user.kugou.com"},
            params={"userid": credential.userid, "token": credential.token, "appid": 1005},
            timeout=config.timeout,
        )
        payload = response.json()
        return payload.get("status") == 1
    except Exception as exc:
        logger.debug("Kugou credential verify failed: %s", exc)
        return credential.token != ""


def verify_kuwo_credential(credential: KuwoCredential, config: ClientConfig) -> bool:
    if not credential.cookies:
        return False
    return bool(credential.cookies.get("userid") or credential.cookies.get("uname"))


def verify_netease_credential(credential: NeteaseCredential, config: ClientConfig) -> bool:
    http = HttpSession(
        headers={"Referer": "https://music.163.com/", "Origin": "https://music.163.com"},
        config=config,
    )
    for key, value in credential.cookies.items():
        http.session.cookies.set(key, value, domain=".163.com")
    csrf = credential.csrf_token or credential.cookies.get("__csrf", "")
    try:
        response = http.post(
            "https://music.163.com/weapi/w/nuser/account/get",
            params={"csrf_token": csrf},
            data=encrypt_weapi({"csrf_token": csrf}),
        )
        payload = response.json()
        return payload.get("code") == 200 and bool(payload.get("profile"))
    except Exception as exc:
        logger.debug("Netease credential verify failed: %s", exc)
        return bool(credential.cookies.get("MUSIC_U"))
