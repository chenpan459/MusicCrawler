# -*- coding: utf-8 -*-
"""NetEase Cloud Music weapi encryption helpers."""

from __future__ import annotations

import base64
import json
from typing import Any

from Crypto.Cipher import AES

PRESET_KEY = "0CoJUm6Qyw8W8jud"
SECOND_KEY = "jkUEeutwbd2HLFNL"
ENC_SEC_KEY = (
    "21e8dcd7b013c2e56af244ad4e55484d5840b108df255fbeccf88e8187362476af2cc881a6"
    "1884aea955937337fe3bdfe896a62c27606da8aea2f3c93b9bb6c6e0c17b85da6e3a766d58"
    "0286967975db7f0f38ef88d582b39f92058deff794b705702e70be6f26b93c206e55e55e6a"
    "51874469fd11cdff86df742c3b9dd89abe"
)
IV = b"0102030405060708"


def _aes_encrypt(text: str, key: str) -> str:
    data = text.encode("utf-8")
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, IV)
    return base64.b64encode(cipher.encrypt(data)).decode("utf-8")


def encrypt_weapi(data: dict[str, Any]) -> dict[str, str]:
    """Encrypt request body for NetEase weapi endpoints."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    first = _aes_encrypt(payload, PRESET_KEY)
    second = _aes_encrypt(first, SECOND_KEY)
    return {"params": second, "encSecKey": ENC_SEC_KEY}
