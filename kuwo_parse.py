# -*- coding: utf-8 -*-
"""Kuwo response parsing helpers."""

from __future__ import annotations

import json
from typing import Any


def parse_kuwo_search_payload(text: str) -> dict[str, Any]:
    """Parse Kuwo search response safely (JSON or legacy Python repr)."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        return json.loads(text)
    if text.startswith("("):
        raise ValueError("酷我搜索响应格式异常")
    # Legacy repr: {key: value} without quotes on keys
    normalized = text
    if not normalized.startswith("{"):
        normalized = "{" + normalized
    if not normalized.endswith("}"):
        normalized = normalized + "}"
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        import re

        fixed = re.sub(r"([{,]\s*)([A-Za-z_][\w]*)\s*:", r'\1"\2":', normalized)
        fixed = fixed.replace("'", '"')
        return json.loads(fixed)
