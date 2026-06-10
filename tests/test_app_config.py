# -*- coding: utf-8 -*-

import json
from pathlib import Path

from app_config import config_defaults, load_config_file


def test_config_defaults_without_file():
    cfg = config_defaults("/nonexistent/config.json")
    assert cfg["platform"] == "qq"
    assert cfg["workers"] == 1
    assert cfg["rate_limit"] == 0.0


def test_load_config_file(tmp_path: Path):
    config_path = tmp_path / "musiccrawler.json"
    config_path.write_text(
        json.dumps({"platform": "kuwo", "workers": 4, "rate_limit": 1.5}),
        encoding="utf-8",
    )
    loaded = load_config_file(str(config_path))
    assert loaded["platform"] == "kuwo"
    assert loaded["workers"] == 4

    merged = config_defaults(str(config_path))
    assert merged["platform"] == "kuwo"
    assert merged["retries"] == 3
