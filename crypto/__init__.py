# -*- coding: utf-8 -*-
"""Platform crypto helpers."""

from crypto.kugou_sign import signature_android, signature_web
from crypto.kuwo_secret import calc_secret, find_iuvt_cookie, reqid_factory
from crypto.netease_weapi import encrypt_weapi

__all__ = [
    "calc_secret",
    "encrypt_weapi",
    "find_iuvt_cookie",
    "reqid_factory",
    "signature_android",
    "signature_web",
]
