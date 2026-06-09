# -*- coding: utf-8 -*-
"""QQ Music login credential helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Credential:
    """QQ Music session credential (from browser cookies or API login)."""

    musicid: int | str
    musickey: str

    @property
    def uin_str(self) -> str:
        return str(self.musicid)


def load_credential(path: str | Path) -> Credential:
    """Load credential from JSON file or browser cookie string file."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"凭证文件为空: {path}")

    if text.startswith("{"):
        return _from_json(text)

    return _from_cookie_string(text)


def _from_json(text: str) -> Credential:
    data: dict[str, Any] = json.loads(text)
    musicid = data.get("musicid") or data.get("uin") or data.get("qqmusic_uin")
    musickey = data.get("musickey") or data.get("qqmusic_key") or data.get("qm_keyst")
    if not musicid or not musickey:
        raise ValueError("JSON 凭证需包含 musicid/uin 和 musickey/qqmusic_key")
    return Credential(musicid=musicid, musickey=str(musickey))


def _from_cookie_string(text: str) -> Credential:
    """Parse 'uin=xxx; qqmusic_key=yyy' style cookie text."""
    pairs: dict[str, str] = {}
    for part in re.split(r"[;\n]", text):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        pairs[key.strip()] = value.strip()

    musicid = (
        pairs.get("musicid")
        or pairs.get("qqmusic_uin")
        or pairs.get("uin")
    )
    musickey = pairs.get("qqmusic_key") or pairs.get("qm_keyst") or pairs.get("musickey")
    if not musicid or not musickey:
        raise ValueError(
            "Cookie 凭证需包含 uin/qqmusic_uin 和 qqmusic_key/qm_keyst\n"
            "获取方式: 浏览器登录 y.qq.com -> F12 -> Application -> Cookies"
        )
    return Credential(musicid=musicid, musickey=musickey)


def calc_g_tk(musickey: str) -> int:
    """Calculate g_tk from qqmusic_key (hash33)."""
    h = 0
    for char in musickey:
        h = (h << 5) + h + ord(char)
    return 2147483647 & h


def save_credential(credential: Credential, path: str | Path) -> None:
    """Save credential to JSON file."""
    payload = {
        "musicid": credential.musicid,
        "musickey": credential.musickey,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def default_credential_path() -> Path:
    return Path("qqmusic_cred.json")


def load_credential_if_exists(path: str | Path | None = None) -> Credential | None:
    """Load credential when file exists."""
    target = Path(path) if path else default_credential_path()
    if not target.exists():
        return None
    try:
        return load_credential(target)
    except (ValueError, json.JSONDecodeError, OSError):
        return None


def save_credential_template(path: str | Path) -> None:
    """Write an example credential template."""
    template = {
        "musicid": "你的QQ号或qqmusic_uin",
        "musickey": "从浏览器复制的qqmusic_key",
    }
    Path(path).write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
