# -*- coding: utf-8 -*-

from unittest.mock import MagicMock

from download_manager import download_songs
from song import DownloadError, Song


def _song(name: str = "测试") -> Song:
    return Song(id="1", mid="001", name=name, singer="歌手", platform="qq")


def test_download_sequential_success():
    client = MagicMock()
    client.download.return_value = ("/tmp/a.mp3", "/tmp/a.lrc")
    success = download_songs(client, [_song()], "/tmp", "mp3_128", workers=1)
    assert success == 1
    client.download.assert_called_once()


def test_download_concurrent_partial_failure(capsys):
    client = MagicMock()

    def side_effect(song, output_dir, quality, with_lyric=True):
        if song.name == "失败":
            raise DownloadError("blocked")
        return (f"/tmp/{song.name}.mp3", None)

    client.download.side_effect = side_effect
    songs = [_song("成功1"), _song("失败"), _song("成功2")]
    success = download_songs(client, songs, "/tmp", "mp3_128", workers=2, with_lyric=False)
    assert success == 2
    assert client.download.call_count == 3
    output = capsys.readouterr().out
    assert "并发下载" in output
    assert "成功 2/3" in output
