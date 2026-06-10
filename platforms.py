# -*- coding: utf-8 -*-
"""Platform registry and client factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from credential import Credential, load_credential_if_exists
from credential_verify import (
    verify_kugou_credential,
    verify_kuwo_credential,
    verify_netease_credential,
    verify_qq_credential,
)
from http_client import ClientConfig
from kugou_client import KugouMusicClient
from kugou_login import KugouCredential
from kuwo_client import KuwoMusicClient
from kuwo_login import KuwoCredential
from netease_client import NeteaseMusicClient
from netease_login import NeteaseCredential
from platform_cred import load_json_credential, resolve_credential_path
from qqmusic_client import QQMusicClient

PLATFORM_NAMES = {
    "qq": "QQ音乐 (y.qq.com)",
    "kuwo": "酷我音乐 (kuwo.cn)",
    "kugou": "酷狗音乐 (kugou.com)",
    "netease": "网易云音乐 (music.163.com)",
}


@dataclass
class PlatformSpec:
    id: str
    client_cls: type
    build: Callable[[ClientConfig, Any | None], Any]
    verify: Callable[[Any, ClientConfig], bool] | None = None


def _build_qq(config: ClientConfig, cred_path: str | None) -> QQMusicClient:
    credential = load_credential_if_exists(cred_path) if cred_path else None
    return QQMusicClient(config=config, credential=credential)


def _build_kugou(config: ClientConfig, cred_path: str | None) -> KugouMusicClient:
    credential = None
    if cred_path:
        data = load_json_credential(cred_path)
        if data:
            credential = KugouCredential.from_dict(data)
    return KugouMusicClient(config=config, credential=credential)


def _build_kuwo(config: ClientConfig, cred_path: str | None) -> KuwoMusicClient:
    credential = None
    if cred_path:
        data = load_json_credential(cred_path)
        if data:
            credential = KuwoCredential.from_dict(data)
    return KuwoMusicClient(config=config, credential=credential)


def _build_netease(config: ClientConfig, cred_path: str | None) -> NeteaseMusicClient:
    credential = None
    if cred_path:
        data = load_json_credential(cred_path)
        if data:
            credential = NeteaseCredential.from_dict(data)
    return NeteaseMusicClient(config=config, credential=credential)


PLATFORMS: dict[str, PlatformSpec] = {
    "qq": PlatformSpec("qq", QQMusicClient, _build_qq, verify_qq_credential),
    "kugou": PlatformSpec("kugou", KugouMusicClient, _build_kugou, verify_kugou_credential),
    "kuwo": PlatformSpec("kuwo", KuwoMusicClient, _build_kuwo, verify_kuwo_credential),
    "netease": PlatformSpec("netease", NeteaseMusicClient, _build_netease, verify_netease_credential),
}


def build_client(
    platform: str,
    *,
    config: ClientConfig,
    cred_path: str | None = None,
    verify: bool = True,
) -> Any:
    spec = PLATFORMS[platform]
    client = spec.build(config, cred_path)
    if verify and cred_path and spec.verify:
        cred = _extract_credential(client)
        if cred and not spec.verify(cred, config):
            import logging

            logging.getLogger("musiccrawler").warning(
                "凭证可能已过期: %s (将继续尝试使用)", cred_path
            )
    return client


def _extract_credential(client: Any) -> Any | None:
    return getattr(client, "credential", None)
