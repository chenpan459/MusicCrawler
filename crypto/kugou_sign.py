# -*- coding: utf-8 -*-
"""Kugou signature helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SIGNATURE_WEB_SECRET = "NVPh5oo715z5DIWAeQlhMDsWXXQV4hwt"
SIGNATURE_ANDROID_SECRET = "OIlwieks28dk2k092lksi2UIkp"


def _md5_hex(data: str) -> str:
    return hashlib.md5(data.encode("utf-8")).hexdigest()


def signature_web(params: dict[str, Any]) -> str:
    parts = [f"{key}={params[key]}" for key in sorted(params)]
    return _md5_hex(f"{SIGNATURE_WEB_SECRET}{''.join(parts)}{SIGNATURE_WEB_SECRET}")


def signature_android(params: dict[str, Any], data: str = "") -> str:
    parts = []
    for key in sorted(params):
        value = params[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        parts.append(f"{key}={value}")
    body = "".join(parts)
    return _md5_hex(f"{SIGNATURE_ANDROID_SECRET}{body}{data}{SIGNATURE_ANDROID_SECRET}")
