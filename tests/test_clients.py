# -*- coding: utf-8 -*-
"""Client integration tests with mocked HTTP responses."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from credential import Credential
from credential_verify import verify_qq_credential
from http_client import ClientConfig
from kugou_client import KugouMusicClient
from kuwo_client import KuwoMusicClient
from netease_client import NeteaseMusicClient
from netease_login import NeteaseCredential
from qqmusic_client import QQMusicClient
from song import Song


def _song(**kwargs) -> Song:
    defaults = {
        "id": "1",
        "mid": "001",
        "name": "测试",
        "singer": "歌手",
        "platform": "qq",
    }
    defaults.update(kwargs)
    return Song(**defaults)


class TestQQCredentialVerify:
    def test_verify_qq_calls_user_info_api(self):
        credential = Credential(musicid=123456, musickey="test_musickey_abc")
        config = ClientConfig(timeout=5, retries=1)

        mock_response = MagicMock()
        mock_response.json.return_value = {"req": {"code": 0, "data": {"nick": "test"}}}

        with patch("credential_verify.HttpSession") as session_cls:
            session = session_cls.return_value
            session.get.return_value = mock_response
            assert verify_qq_credential(credential, config) is True
            session.get.assert_called_once()
            url = session.get.call_args[0][0]
            assert "music.userCenter.UserInfo" in url

    def test_verify_qq_rejects_invalid_response(self):
        credential = Credential(musicid=1, musickey="key")
        config = ClientConfig(timeout=5, retries=1)
        mock_response = MagicMock()
        mock_response.json.return_value = {"req": {"code": 1000}}

        with patch("credential_verify.HttpSession") as session_cls:
            session_cls.return_value.get.return_value = mock_response
            assert verify_qq_credential(credential, config) is False


class TestQQBatchProbe:
    def test_batch_probe_vkey(self):
        client = QQMusicClient(config=ClientConfig(retries=1))
        payload = {
            "req_0": {
                "data": {
                    "midurlinfo": [
                        {"songmid": "mid1", "purl": "abc", "result": 0},
                        {"songmid": "mid2", "purl": "", "result": 104003},
                    ]
                }
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = payload

        with patch.object(client.http, "get", return_value=mock_response):
            result = client._batch_probe_vkey(["mid1", "mid2"], "mp3_128")

        assert result["mid1"] is True
        assert result["mid2"] is False

    def test_probe_downloadable_uses_batch(self):
        client = QQMusicClient(config=ClientConfig(retries=1))
        songs = [_song(mid="mid1"), _song(mid="mid2")]
        with patch.object(
            client,
            "_batch_probe_vkey",
            return_value={"mid1": True, "mid2": False},
        ) as batch_mock:
            probed = client.probe_downloadable(songs, quality="mp3_128")
        batch_mock.assert_called_once()
        assert probed[0].downloadable is True
        assert probed[1].downloadable is False


def _netease_client() -> NeteaseMusicClient:
    cred = NeteaseCredential(csrf_token="test", cookies={"MUSIC_U": "1"})
    return NeteaseMusicClient(credential=cred, config=ClientConfig(retries=1))


class TestNeteaseProbe:
    def test_fee_heuristic_skips_api(self):
        with patch.object(NeteaseMusicClient, "_bootstrap"):
            client = NeteaseMusicClient(config=ClientConfig(retries=1))
        songs = [
            _song(mid="1", platform="netease", meta={"fee": 0}),
            _song(mid="2", platform="netease", meta={"fee": 1}),
        ]
        with patch.object(client, "_batch_probe") as batch_mock:
            probed = client.probe_downloadable(songs)
        batch_mock.assert_not_called()
        assert probed[0].downloadable is True
        assert probed[1].downloadable is False

    def test_batch_probe_for_unknown_fee(self):
        client = _netease_client()
        songs = [_song(mid="99", platform="netease", meta={"fee": 4})]
        with patch.object(client, "_batch_probe", return_value={"99": True}) as batch_mock:
            probed = client.probe_downloadable(songs)
        batch_mock.assert_called_once_with(["99"], "mp3_128")
        assert probed[0].downloadable is True


class TestKugouProbe:
    def test_vip_heuristic_without_login(self):
        client = KugouMusicClient(config=ClientConfig(retries=1))
        song = _song(
            platform="kugou",
            meta={"hash": "abc", "pay_type": 1, "privilege": 8},
        )
        with patch.object(client, "_batch_probe_tracker") as batch_mock:
            probed = client.probe_downloadable([song])
        batch_mock.assert_not_called()
        assert probed[0].downloadable is False

    def test_batch_tracker_probe(self):
        client = KugouMusicClient(config=ClientConfig(retries=1))
        song = _song(
            platform="kugou",
            meta={"hash": "deadbeef", "pay_type": 0, "privilege": 0},
        )
        with patch.object(
            client,
            "_batch_probe_tracker",
            return_value={"deadbeef": True},
        ) as batch_mock:
            probed = client.probe_downloadable([song], quality="mp3_128")
        batch_mock.assert_called_once()
        assert probed[0].downloadable is True


class TestKuwoProbe:
    def test_tpay_heuristic_free_song(self):
        client = KuwoMusicClient(config=ClientConfig(retries=1))
        song = _song(platform="kuwo", meta={"tpay": 1, "fee_song": 1})
        with patch.object(client, "_batch_probe_download") as batch_mock:
            probed = client.probe_downloadable([song])
        batch_mock.assert_not_called()
        assert probed[0].downloadable is True

    def test_tpay_heuristic_blocked_song(self):
        client = KuwoMusicClient(config=ClientConfig(retries=1))
        song = _song(platform="kuwo", meta={"tpay": 0, "fee_song": 0})
        with patch.object(client, "_batch_probe_download") as batch_mock:
            probed = client.probe_downloadable([song])
        batch_mock.assert_not_called()
        assert probed[0].downloadable is False

    def test_batch_probe_when_heuristic_unknown(self):
        client = KuwoMusicClient(config=ClientConfig(retries=1))
        song = _song(platform="kuwo", mid="123", meta={"tpay": -1, "fee_song": -1})
        with patch.object(
            client,
            "_batch_probe_download",
            return_value={"123": True},
        ) as batch_mock:
            probed = client.probe_downloadable([song])
        batch_mock.assert_called_once()
        assert probed[0].downloadable is True


class TestBaseClientHelpers:
    def test_quality_chain(self):
        from base_client import BaseMusicClient

        chain = BaseMusicClient.quality_chain("mp3_320", ["mp3_128", "m4a", "flac"])
        assert chain == ["mp3_320", "mp3_128", "m4a", "flac"]

    def test_safe_filename(self):
        from base_client import BaseMusicClient

        assert BaseMusicClient.safe_filename('a/b:c?d"e') == "a_b_c_d_e"
