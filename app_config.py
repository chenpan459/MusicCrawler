# -*- coding: utf-8 -*-
"""Application config file loader."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILENAME = "musiccrawler.json"

DEFAULTS: dict[str, Any] = {
    "platform": "qq",
    "num": 10,
    "quality": "mp3_128",
    "output": "./downloads",
    "proxy": None,
    "retries": 3,
    "timeout": 30,
    "rate_limit": 0.0,
    "workers": 1,
    "verbose": False,
    "json_log": False,
    "no_probe": False,
    "only_downloadable": False,
    "no_lyric": False,
    "no_verify_credential": False,
}


def _config_search_paths(explicit: str | None = None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit))
    env_path = os.environ.get("MUSICCRAWLER_CONFIG")
    if env_path:
        paths.append(Path(env_path))
    paths.append(Path(DEFAULT_CONFIG_FILENAME))
    paths.append(Path.home() / ".config" / "musiccrawler" / "config.json")
    return paths


def load_config_file(explicit: str | None = None) -> dict[str, Any]:
    """Load the first existing config file; return empty dict if none found."""
    for path in _config_search_paths(explicit):
        if not path.exists() or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def config_defaults(explicit: str | None = None) -> dict[str, Any]:
    """Merge built-in defaults with config file values."""
    merged = dict(DEFAULTS)
    merged.update(load_config_file(explicit))
    return merged
