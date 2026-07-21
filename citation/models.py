from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    source_url: str
    source_title: str
    last_updated: str
