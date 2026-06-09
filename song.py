# -*- coding: utf-8 -*-
"""Shared music models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Song:
    """Search result song."""

    id: str
    mid: str
    name: str
    singer: str
    downloadable: bool | None = None
    platform: str = "qq"

    def display(self, index: int) -> str:
        if self.downloadable is True:
            status = "[可下载]"
        elif self.downloadable is False:
            status = "[VIP/版权受限]"
        else:
            status = ""
        return f"{index:>2}. {self.name} - {self.singer}  {status} [{self.mid}]"


class DownloadError(Exception):
    """Download related error."""
