# -*- coding: utf-8 -*-

import json

import pytest

from kuwo_parse import parse_kuwo_search_payload


def test_parse_json_object():
    data = {"abslist": [{"SONGNAME": "稻香", "ARTIST": "周杰伦", "DC_TARGETID": "123"}]}
    result = parse_kuwo_search_payload(json.dumps(data))
    assert len(result["abslist"]) == 1


def test_parse_legacy_repr():
    text = '{"abslist": [{"SONGNAME": "test", "ARTIST": "a", "DC_TARGETID": "1"}]}'
    result = parse_kuwo_search_payload(text)
    assert result["abslist"][0]["SONGNAME"] == "test"


def test_parse_empty():
    assert parse_kuwo_search_payload("") == {}
