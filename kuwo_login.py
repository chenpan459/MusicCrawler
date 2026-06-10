# -*- coding: utf-8 -*-
"""Kuwo Music login helpers (username + password)."""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any
import requests

from crypto.kuwo_secret import calc_secret as _calc_secret
from crypto.kuwo_secret import find_iuvt_cookie
from crypto.kuwo_secret import reqid_factory as _reqid_factory
from platform_cred import default_credential_path, save_json_credential

BASE_URL = "https://www.kuwo.cn/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Content-Type": "application/json;charset=utf-8",
    "Host": "www.kuwo.cn",
}

CAPTCHA_FILE = Path("kuwo_login_captcha.jpg")


class LoginError(Exception):
    """Login related error."""


@dataclass
class KuwoCredential:
    cookies: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"cookies": self.cookies}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KuwoCredential:
        cookies = data.get("cookies", {})
        if isinstance(cookies, str):
            cookies = _parse_cookie_string(cookies)
        return cls(cookies={str(k): str(v) for k, v in cookies.items()})


def _parse_cookie_string(text: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in re.split(r"[;\n]", text):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


class KuwoLoginSession:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._gen_reqid = _reqid_factory()
        self._captcha_token = ""
        self._captcha_img = ""

    def _bootstrap(self) -> None:
        self.session.get(BASE_URL, timeout=self.timeout)

    def _apply_secret(self) -> None:
        cookie = find_iuvt_cookie(self.session.cookies.get_dict())
        if not cookie:
            raise LoginError("初始化酷我会话失败，未获取到 Cookie")
        key, value = cookie
        self.session.headers["Secret"] = _calc_secret(value, key)

    def _fetch_captcha(self) -> bytes:
        self._bootstrap()
        self._apply_secret()
        url = "http://www.kuwo.cn/api/common/captcha/getcode"
        params = {
            "reqId": self._gen_reqid(),
            "httpsStatus": "1",
        }
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise LoginError(payload.get("msg", "获取验证码失败"))
        captcha = payload["data"]["img"]
        self._captcha_token = payload["data"]["token"]
        self._captcha_img = captcha
        prefix = "data:image/jpeg;base64,"
        if not captcha.startswith(prefix):
            raise LoginError("验证码格式异常")
        return base64.b64decode(captcha[len(prefix):])

    def login_by_password(
        self,
        username: str,
        password: str,
        captcha: str,
    ) -> dict[str, str]:
        self._bootstrap()
        self._apply_secret()
        url = "https://wapi.kuwo.cn/api/www/login/loginByKw"
        params = {
            "reqId": self._gen_reqid(),
            "httpsStatus": "1",
        }
        data = {
            "userIp": "www.kuwo.cn",
            "uname": username,
            "password": password,
            "verifyCode": captcha,
            "img": self._captcha_img,
            "verifyCodeToken": self._captcha_token,
        }
        response = self.session.post(
            url,
            params=params,
            data=json.dumps(data),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise LoginError(payload.get("msg", "登录失败"))
        cookies = payload.get("data", {}).get("cookies", {})
        if not cookies:
            raise LoginError("登录成功但未返回 cookies")
        self.session.cookies.update(cookies)
        return {str(k): str(v) for k, v in cookies.items()}


def login_by_password(
    username: str,
    password: str,
    *,
    captcha: str | None = None,
    path: str | Path | None = None,
) -> KuwoCredential:
    username = username.strip()
    password = password.strip()
    if not username or not password:
        raise LoginError("用户名和密码不能为空")

    output = Path(path or default_credential_path("kuwo"))
    client = KuwoLoginSession()
    captcha_bytes = client._fetch_captcha()
    CAPTCHA_FILE.write_bytes(captcha_bytes)
    print(f"验证码已保存: {CAPTCHA_FILE.resolve()}")
    print("请打开图片查看验证码")

    if not captcha:
        captcha = input("请输入验证码: ").strip()
    if not captcha:
        raise LoginError("验证码不能为空")

    cookies = client.login_by_password(username, password, captcha)
    merged = {cookie.name: cookie.value for cookie in client.session.cookies}
    merged.update(cookies)
    cred = KuwoCredential(cookies=merged)
    save_json_credential(cred.to_dict(), output)
    print(f"登录成功，凭证已保存: {output.resolve()}")
    return cred


def run_login(
    mode: str,
    *,
    username: str | None = None,
    password: str | None = None,
    path: str | Path | None = None,
) -> KuwoCredential:
    mode = mode.lower()
    if mode in {"password", "user", "account", "pwd"}:
        if not username:
            username = input("酷我用户名(手机号/邮箱): ").strip()
        if not password:
            password = getpass("酷我密码: ").strip()
        return login_by_password(username, password, path=path)
    raise LoginError(f"酷我暂不支持登录方式: {mode}，请使用 --login password")
