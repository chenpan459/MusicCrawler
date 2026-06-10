# -*- coding: utf-8 -*-
"""Kuwo Secret header and reqId helpers."""

from __future__ import annotations

import math
import random
import time
from ctypes import c_uint32
from typing import Any

IUVT_COOKIE_PREFIX = "Hm_Iuvt_"


def find_iuvt_cookie(cookies: dict[str, str] | Any) -> tuple[str, str] | None:
    items = cookies.items() if hasattr(cookies, "items") else cookies
    for key, value in items:
        if str(key).startswith(IUVT_COOKIE_PREFIX) and value:
            return str(key), str(value)
    return None


def _int_overflow(val: int) -> int:
    max_int = 2 ** 31
    if not -max_int <= val <= max_int - 1:
        val = (val + max_int) % (2 * max_int) - max_int
    return val


def _unsigned_right_shift(n: int, i: int) -> int:
    if n < 0:
        n = c_uint32(n).value
    if i < 0:
        return -_int_overflow(n << abs(i))
    return _int_overflow(n >> i)


def reqid_factory() -> Any:
    r = None
    o = None
    d = 0

    def get_reqid() -> str:
        nonlocal r, o, d
        b: list[int] = []
        f = r
        v = o
        if f is None or v is None:
            m = [random.randrange(256) for _ in range(16)]
            r = f = f or [1 | m[0], m[1], m[2], m[3], m[4], m[5]]
            o = v = v or 16383 & (_int_overflow(m[6] << 8) | 7)
        y = int(time.time() * 1000)
        w = d + 1
        d = w
        x = (10000 * (268435455 & (y := y + 12219292800000)) + w) % 4294967296
        b.append(_unsigned_right_shift(x, 24) & 255)
        b.append(_unsigned_right_shift(x, 16) & 255)
        b.append(_unsigned_right_shift(x, 8) & 255)
        b.append(255 & x)
        _x = int(y / 4294967296 * 10000) & 268435455
        b.append(_unsigned_right_shift(_x, 8) & 255)
        b.append(255 & _x)
        b.append(_unsigned_right_shift(_x, 24) & 15 | 16)
        b.append(_unsigned_right_shift(_x, 16) & 255)
        b.append(_unsigned_right_shift(v, 8) | 128)
        b.append(255 & v)
        b.extend(f)
        result = [f"{hex(i)[2:]:0>2}" for i in b]
        result.insert(10, "-")
        result.insert(8, "-")
        result.insert(6, "-")
        result.insert(4, "-")
        return "".join(result)

    return get_reqid


def calc_secret(cookie_value: str, cookie_key: str) -> str:
    o = 60950
    l = 20
    c = 2 ** 31 - 1
    key = 798334170
    f = ""
    for ch in cookie_value:
        h = ord(ch) ^ math.floor(key / c * 255)
        f += f"0{hex(h)[2:]}" if h < 16 else hex(h)[2:]
        key = (o * int(key) + l) % c
    return f + "002523df"
