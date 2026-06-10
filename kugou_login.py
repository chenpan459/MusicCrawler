# -*- coding: utf-8 -*-
"""Kugou Music login helpers (username + password)."""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA

from crypto.kugou_sign import signature_android
from platform_cred import default_credential_path, save_json_credential

APPID = 1005
CLIENTVER = 20489
PUBLIC_RSA_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDIAG7QOELSYoIJvTFJhMpe1s/g
bjDJX51HBNnEl5HXqTW6lQ7LC8jr9fWZTwusknp+sVGzwd40MwP6U5yDE27M/X1+UR
4tvOGOqp94TJtQ1EPnWGWXngpeIW5GxoQGao1rmYWAu6oi1z9XkChrsUdC6DJE5E2
21wf/4WLFxwAtRQIDAQAB
-----END PUBLIC KEY-----"""

LOGIN_T1 = (
    "562a6f12a6e803453647d16a08f5f0c2ff7eee692cba2ab74cc4c8ab47fc467561a7c6b586ce7dc46a63613b246737c"
    "03a1dc8f8d162d8ce1d2c71893d19f1d4b797685a4c6d3d81341cbde65e488c4829a9b4d42ef2df470eb102979fa5adcdd9b"
    "4eecfea8b909ff7599abeb49867640f10c3c70fc444effca9d15db44a9a6c907731e2bb0f22cd9b3536380169995693e5f0e"
    "2424e3378097d3813186e3fe96bbe7023808a0981b4e2b6135a76faac"
)
LOGIN_T2 = (
    "31c4daf4cf480169ccea1cb7d4a209295865a9d2b788510301694db229b87807469ea0d41b4d4b9173c2151da7294aeebfc"
    "9738df154bbdf11a4e117bb5dff6a3af8ce5ce333e681c1f29a44038f27567d58992eb81283e080778ac77db1400fdf49b7"
    "cf7e26be2e5af4da7830cc3be4"
)
LOGIN_T3 = "MCwwLDAsMCwwLDAsMCwwLDA="

DEFAULT_HEADERS = {
    "User-Agent": "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi",
    "kg-rc": "1",
    "kg-thash": "5d816a0",
    "kg-rec": "1",
    "kg-rf": "B9EDA08A64250DEFFBCADDEE00F8F25F",
}


class LoginError(Exception):
    """Login related error."""


@dataclass
class KugouCredential:
    token: str
    userid: str
    vip_token: str = ""
    vip_type: int = 0
    mid: str = ""
    dfid: str = "-"

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "userid": self.userid,
            "vip_token": self.vip_token,
            "vip_type": self.vip_type,
            "mid": self.mid,
            "dfid": self.dfid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KugouCredential:
        return cls(
            token=str(data.get("token", "")),
            userid=str(data.get("userid", "")),
            vip_token=str(data.get("vip_token", "")),
            vip_type=int(data.get("vip_type", 0) or 0),
            mid=str(data.get("mid", "")),
            dfid=str(data.get("dfid", "-")),
        )


def _random_string(length: int = 16) -> str:
    chars = "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(random.choice(chars) for _ in range(length))


def _calculate_mid(seed: str) -> str:
    return str(int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16))


def _pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - len(data) % block_size
    return data + bytes([pad_len]) * pad_len


def _unpad(data: bytes) -> bytes:
    return data[:-data[-1]]


def _md5_hex(data: Any) -> str:
    if isinstance(data, (dict, list)):
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    elif isinstance(data, bytes):
        text = data
        return hashlib.md5(text).hexdigest()
    else:
        text = str(data)
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _aes_encrypt_payload(payload: dict[str, Any]) -> tuple[str, str]:
    temp_key = _random_string(16).lower()
    aes_key = _md5_hex(temp_key)[:32]
    iv = aes_key[-16:]
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    encrypted_hex = cipher.encrypt(_pad(raw)).hex()
    return encrypted_hex, temp_key


def _aes_decrypt_hex(data_hex: str, temp_key: str) -> Any:
    aes_key = _md5_hex(temp_key)[:32]
    iv = aes_key[-16:]
    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    decrypted = _unpad(cipher.decrypt(bytes.fromhex(data_hex)))
    text = decrypted.decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _rsa_encrypt(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encrypted = PKCS1_v1_5.new(RSA.import_key(PUBLIC_RSA_KEY)).encrypt(raw)
    return encrypted.hex().upper()


def _init_device_cookies() -> dict[str, str]:
    guid = str(uuid.uuid4())
    mid = _calculate_mid(guid)
    return {
        "KUGOU_API_GUID": guid,
        "KUGOU_API_MID": mid,
        "KUGOU_API_MAC": _random_string(12),
        "KUGOU_API_DEV": _random_string(16),
        "dfid": "-",
    }


def _send_gateway_request(
    session: requests.Session,
    *,
    method: str,
    path: str,
    cookies: dict[str, str],
    data: dict[str, Any] | None = None,
    router: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    clienttime = int(time.time())
    mid = cookies.get("KUGOU_API_MID", "-")
    dfid = cookies.get("dfid", "-")
    token = cookies.get("token", "")
    userid = cookies.get("userid", "0")

    params: dict[str, Any] = {
        "dfid": dfid,
        "mid": mid,
        "uuid": "-",
        "appid": APPID,
        "clientver": CLIENTVER,
        "clienttime": clienttime,
    }
    if token:
        params["token"] = token
    if userid and userid != "0":
        params["userid"] = userid

    data_str = ""
    if data is not None:
        data_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    params["signature"] = signature_android(params, data_str)

    headers = {
        **DEFAULT_HEADERS,
        "dfid": dfid,
        "clienttime": str(clienttime),
        "mid": mid,
    }
    if router:
        headers["x-router"] = router

    response = session.request(
        method,
        f"https://gateway.kugou.com{path}",
        params=params,
        json=data,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    cookies.update(response.cookies.get_dict())
    payload = response.json()
    if payload.get("status") != 1:
        message = payload.get("error_msg") or payload.get("msg") or "请求失败"
        raise LoginError(message)
    return payload


def login_by_password(
    username: str,
    password: str,
    path: str | Path | None = None,
) -> KugouCredential:
    """Login with Kugou username (phone/email) and password."""
    username = username.strip()
    password = password.strip()
    if not username or not password:
        raise LoginError("用户名和密码不能为空")

    output = Path(path or default_credential_path("kugou"))
    cookies = _init_device_cookies()
    session = requests.Session()

    clienttime_ms = int(time.time() * 1000)
    encrypted_params, temp_key = _aes_encrypt_payload(
        {"pwd": password, "code": "", "clienttime_ms": clienttime_ms}
    )
    body = {
        "plat": 1,
        "support_multi": 1,
        "clienttime_ms": clienttime_ms,
        "t1": LOGIN_T1,
        "t2": LOGIN_T2,
        "t3": LOGIN_T3,
        "username": username,
        "params": encrypted_params,
        "pk": _rsa_encrypt({"clienttime_ms": clienttime_ms, "key": temp_key}),
    }

    payload = _send_gateway_request(
        session,
        method="POST",
        path="/v9/login_by_pwd",
        cookies=cookies,
        data=body,
        router="login.user.kugou.com",
    )
    data = payload.get("data", {})
    token_info: Any = None
    if data.get("secu_params"):
        token_info = _aes_decrypt_hex(str(data["secu_params"]), temp_key)
    elif data.get("token"):
        token_info = {"token": data["token"]}

    if not token_info:
        raise LoginError("登录成功但未返回 token")

    if isinstance(token_info, dict):
        token = str(token_info.get("token") or "")
        cookies.update({k: str(v) for k, v in token_info.items() if v})
    else:
        token = str(token_info)
        cookies["token"] = token

    userid = str(data.get("userid") or cookies.get("userid") or "")
    if not token or not userid:
        raise LoginError("登录成功但未获取到 token/userid")

    cookies["token"] = token
    cookies["userid"] = userid
    cookies["vip_token"] = str(data.get("vip_token", ""))
    cookies["vip_type"] = str(data.get("vip_type", 0))

    cred = KugouCredential(
        token=token,
        userid=userid,
        vip_token=str(data.get("vip_token", "")),
        vip_type=int(data.get("vip_type", 0) or 0),
        mid=cookies.get("KUGOU_API_MID", ""),
        dfid=cookies.get("dfid", "-"),
    )
    save_json_credential(cred.to_dict(), output)
    print(f"登录成功，凭证已保存: {output.resolve()}")
    return cred


def run_login(
    mode: str,
    *,
    username: str | None = None,
    password: str | None = None,
    path: str | Path | None = None,
) -> KugouCredential:
    mode = mode.lower()
    if mode in {"password", "user", "account", "pwd"}:
        if not username:
            username = input("酷狗用户名(手机号/邮箱): ").strip()
        if not password:
            password = getpass("酷狗密码: ").strip()
        return login_by_password(username, password, path)
    raise LoginError(f"酷狗暂不支持登录方式: {mode}，请使用 --login password")
