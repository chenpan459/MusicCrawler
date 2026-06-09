# -*- coding: utf-8 -*-
"""QQ Music login helpers (QR code / phone + SMS)."""

from __future__ import annotations

import asyncio
import json
from getpass import getpass
from pathlib import Path
from typing import Any

from credential import Credential

DEFAULT_CREDENTIAL_PATH = Path("qqmusic_cred.json")


class LoginError(Exception):
    """Login related error."""


def _to_local_credential(api_cred: Any) -> Credential:
    musicid = api_cred.str_musicid or str(api_cred.musicid)
    musickey = api_cred.musickey
    if not musicid or not musickey:
        raise LoginError("登录成功但未获取到 musicid/musickey")
    return Credential(musicid=musicid, musickey=musickey)


def save_login_result(
    api_cred: Any,
    path: str | Path = DEFAULT_CREDENTIAL_PATH,
) -> Credential:
    """Save API credential to local JSON file."""
    local = _to_local_credential(api_cred)
    payload = {
        "musicid": local.musicid,
        "musickey": local.musickey,
        "refresh_token": getattr(api_cred, "refresh_token", "") or "",
        "refresh_key": getattr(api_cred, "refresh_key", "") or "",
        "str_musicid": getattr(api_cred, "str_musicid", "") or str(local.musicid),
        "login_type": getattr(api_cred, "login_type", 0),
    }
    output = Path(path)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return local


async def login_by_qr(path: str | Path = DEFAULT_CREDENTIAL_PATH) -> Credential:
    """Login via QQ QR code scan."""
    from qqmusic_api import Client
    from qqmusic_api.models.login import QRCodeLoginEvents, QRLoginType

    output = Path(path)
    async with Client() as client:
        qr = await client.login.get_qrcode(QRLoginType.QQ)
        qr_file = qr.save(output.parent / "qq_login_qr.png")
        print("请使用手机 QQ 扫描下方二维码登录:")
        if qr_file:
            print(f"  二维码文件: {qr_file.resolve()}")
        print("  (也可在文件管理器中打开 qq_login_qr.png)")
        print("等待扫码确认...")

        while True:
            result = await client.login.check_qrcode(qr)
            event = result.event
            if event == QRCodeLoginEvents.DONE:
                if not result.credential:
                    raise LoginError("扫码成功但未返回登录凭证")
                local = save_login_result(result.credential, output)
                print(f"登录成功，凭证已保存: {output.resolve()}")
                return local
            if event == QRCodeLoginEvents.SCAN:
                print("  已扫码，请在手机上确认登录...")
            elif event == QRCodeLoginEvents.CONF:
                print("  已确认，正在获取凭证...")
            elif event == QRCodeLoginEvents.TIMEOUT:
                raise LoginError("二维码已过期，请重新运行登录")
            elif event == QRCodeLoginEvents.REFUSE:
                raise LoginError("登录被拒绝或已取消")
            await asyncio.sleep(2)


async def login_by_phone(
    phone: str,
    code: str | None = None,
    path: str | Path = DEFAULT_CREDENTIAL_PATH,
) -> Credential:
    """Login via phone number and SMS verification code."""
    from qqmusic_api import Client
    from qqmusic_api.models.login import PhoneLoginEvents

    phone = phone.strip()
    if not phone.isdigit() or len(phone) < 11:
        raise LoginError("手机号格式不正确")

    output = Path(path)
    async with Client() as client:
        send_result = await client.login.send_authcode(int(phone))
        if send_result.event == PhoneLoginEvents.FREQUENCY:
            raise LoginError("验证码发送过于频繁，请稍后再试")
        if send_result.event == PhoneLoginEvents.CAPTCHA:
            raise LoginError("需要图形验证码，请改用扫码登录 (--login qr)")
        if send_result.event != PhoneLoginEvents.SEND:
            raise LoginError("验证码发送失败，请稍后重试")

        if not code:
            code = getpass("请输入短信验证码: ").strip()
        if not code:
            raise LoginError("验证码不能为空")

        api_cred = await client.login.phone_authorize(int(phone), code)
        local = save_login_result(api_cred, output)
        print(f"登录成功，凭证已保存: {output.resolve()}")
        return local


async def login_by_password(
    username: str,
    password: str,
    path: str | Path = DEFAULT_CREDENTIAL_PATH,
) -> Credential:
    """Login with username + password.

    QQ Music does not expose a stable QQ号+密码 HTTP API.
    If username looks like a phone number, use phone+SMS login instead.
    """
    username = username.strip()
    password = password.strip()
    if not username or not password:
        raise LoginError("用户名和密码不能为空")

    if username.isdigit() and len(username) == 11:
        return await login_by_phone(username, password, path)

    raise LoginError(
        "QQ号+密码登录暂不支持（腾讯需验证码/扫码）。\n"
        "请改用以下方式之一:\n"
        "  1) 手机号+验证码: python3 main.py --login phone --user 手机号\n"
        "  2) QQ扫码登录:   python3 main.py --login qr\n"
        "  3) 浏览器Cookie: python3 main.py --init-credential qqmusic_cred.json"
    )


def run_login(
    mode: str,
    *,
    username: str | None = None,
    password: str | None = None,
    path: str | Path = DEFAULT_CREDENTIAL_PATH,
) -> Credential:
    """Sync entry for CLI login."""
    mode = mode.lower()
    if mode == "qr":
        return asyncio.run(login_by_qr(path))
    if mode == "phone":
        if not username:
            username = input("手机号: ").strip()
        return asyncio.run(login_by_phone(username, password, path))
    if mode in {"password", "user", "account"}:
        if not username:
            username = input("用户名(手机号): ").strip()
        if not password:
            password = getpass("密码(短信验证码或按提示操作): ").strip()
        return asyncio.run(login_by_password(username, password, path))
    raise LoginError(f"未知登录方式: {mode}，可选 qr / phone")
