# -*- coding: utf-8 -*-
"""Platform credential path helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CREDENTIAL_FILES = {
    "qq": "qqmusic_cred.json",
    "kugou": "kugou_cred.json",
    "kuwo": "kuwo_cred.json",
    "netease": "netease_cred.json",
}


def default_credential_path(platform: str) -> Path:
    return Path(CREDENTIAL_FILES.get(platform, f"{platform}_cred.json"))


def resolve_credential_path(platform: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    default_path = default_credential_path(platform)
    if default_path.exists():
        return str(default_path)
    return None


def load_json_credential(path: str | Path) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_json_credential(data: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(output, 0o600)
    except OSError:
        pass
