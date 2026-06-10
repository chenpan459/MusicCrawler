# -*- coding: utf-8 -*-

from crypto.kugou_sign import signature_android, signature_web
from crypto.kuwo_secret import calc_secret
from crypto.netease_weapi import encrypt_weapi


def test_netease_encrypt_weapi_keys():
    payload = encrypt_weapi({"csrf_token": "", "s": "test"})
    assert "params" in payload
    assert "encSecKey" in payload
    assert len(payload["encSecKey"]) > 100


def test_kugou_signature_web_stable():
    params = {"appid": "1014", "clienttime": "123", "mid": "abc"}
    sig1 = signature_web(params)
    sig2 = signature_web(params)
    assert sig1 == sig2
    assert len(sig1) == 32


def test_kugou_signature_android_with_body():
    params = {"appid": 1005, "clienttime": 1}
    sig = signature_android(params, '{"a":1}')
    assert len(sig) == 32


def test_kuwo_calc_secret_length():
    secret = calc_secret("JXbannkz4r3pXFRW8YNjxzxmSkdxSPRX", "Hm_Iuvt_test")
    assert secret.endswith("002523df")
    assert len(secret) > 16
