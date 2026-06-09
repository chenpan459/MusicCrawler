# -*- coding: utf-8 -*-
"""NetEase Cloud Music login helpers."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

import requests

from netease_crypto import encrypt_weapi
from platform_cred import default_credential_path, save_json_credential

BASE_URL = "https://music.163.com/"
QR_FILE = Path("netease_login_qr.png")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Origin": "https://music.163.com",
}


class LoginError(Exception):
    """Login related error."""


@dataclass
class NeteaseCredential:
    csrf_token: str
    cookies: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "csrf_token": self.csrf_token,
            "cookies": self.cookies,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NeteaseCredential:
        cookies = data.get("cookies", {})
        if isinstance(cookies, str):
            cookies = _parse_cookie_string(cookies)
        return cls(
            csrf_token=str(data.get("csrf_token", "")),
            cookies={str(k): str(v) for k, v in cookies.items()},
        )


def _parse_cookie_string(text: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in text.replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


class NeteaseLoginSession:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.csrf_token = ""

    def _update_csrf(self) -> None:
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
        self._update_csrf()
        return result

    def bootstrap(self) -> None:
        self.session.get(BASE_URL, timeout=self.timeout)
        self._update_csrf()

    def save_credential(self, path: str | Path) -> NeteaseCredential:
        cookies = {cookie.name: cookie.value for cookie in self.session.cookies}
        cred = NeteaseCredential(csrf_token=self.csrf_token, cookies=cookies)
        save_json_credential(cred.to_dict(), path)
        return cred

    def login_by_password(self, username: str, password: str) -> None:
        self.bootstrap()
        password_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
        if "@" in username:
            data = {
                "username": username,
                "password": password_md5,
                "rememberLogin": "true",
            }
            path = "/weapi/login"
        else:
            data = {
                "phone": username,
                "password": password_md5,
                "rememberLogin": "true",
            }
            path = "/weapi/login/cellphone"
        result = self._post_weapi(path, data)
        if result.get("code") != 200:
            raise LoginError(result.get("message") or result.get("msg") or "登录失败")

    def send_sms(self, phone: str) -> None:
        self.bootstrap()
        result = self._post_weapi(
            "/weapi/sms/captcha/sent",
            {"cellphone": phone, "ctcode": 86},
        )
        if result.get("code") != 200:
            raise LoginError(result.get("message") or result.get("msg") or "验证码发送失败")

    def login_by_phone(self, phone: str, code: str) -> None:
        self.bootstrap()
        result = self._post_weapi(
            "/weapi/sms/captcha/verify",
            {
                "cellphone": phone,
                "captcha": code,
                "ctcode": 86,
            },
        )
        if result.get("code") != 200:
            raise LoginError(result.get("message") or result.get("msg") or "验证码登录失败")

    def _fetch_qr_unikey(self) -> str:
        result = self._post_weapi(
            "/weapi/login/qrcode/unikey",
            {"type": 1, "noCheckToken": "true"},
        )
        if result.get("code") != 200:
            raise LoginError("获取二维码失败")
        return str(result["unikey"])

    def login_by_qr(self) -> None:
        self.bootstrap()
        unikey = self._fetch_qr_unikey()
        qr_url = f"http://music.163.com/login?codekey={unikey}"
        try:
            import qrcode

            img = qrcode.make(qr_url)
            img.save(QR_FILE)
            print("请使用网易云音乐 APP 扫描下方二维码登录:")
            print(f"  二维码文件: {QR_FILE.resolve()}")
        except ImportError:
            print("请使用网易云音乐 APP 扫描以下链接登录:")
            print(f"  {qr_url}")

        print("等待扫码确认...")
        while True:
            result = self._post_weapi(
                "/weapi/login/qrcode/client/login",
                {"type": 1, "noCheckToken": "true", "key": unikey},
            )
            code = result.get("code")
            if code == 803:
                return
            if code == 800:
                raise LoginError("二维码已过期，请重新运行登录")
            if code == 802:
                print("  已扫码，请在手机上确认登录...")
            elif code == 801:
                print("  等待扫码...")
            else:
                raise LoginError(result.get("message") or result.get("msg") or "扫码登录失败")
            time.sleep(2)


def run_login(
    mode: str,
    *,
    username: str | None = None,
    password: str | None = None,
    path: str | Path | None = None,
) -> NeteaseCredential:
    output = Path(path or default_credential_path("netease"))
    client = NeteaseLoginSession()
    mode = mode.lower()

    if mode == "qr":
        client.login_by_qr()
    elif mode == "phone":
        if not username:
            username = input("手机号: ").strip()
        client.send_sms(username)
        if not password:
            password = getpass("短信验证码: ").strip()
        client.login_by_phone(username, password)
    elif mode in {"password", "user", "account", "pwd"}:
        if not username:
            username = input("用户名(手机号/邮箱): ").strip()
        if not password:
            password = getpass("密码: ").strip()
        client.login_by_password(username, password)
    else:
        raise LoginError(f"未知登录方式: {mode}，可选 qr / phone / password")

    cred = client.save_credential(output)
    print(f"登录成功，凭证已保存: {output.resolve()}")
    return cred
