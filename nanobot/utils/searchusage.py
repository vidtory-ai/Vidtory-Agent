"""Stub search usage tracker.

Web search tools were removed from Vidtory. This stub satisfies any
remaining imports without introducing dead code.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchUsageInfo:
    provider: str = ""
    limit: int = 0
    used: int = 0

    def format(self) -> str:
        return ""


async def fetch_search_usage(*, provider: str = "", api_key: str | None = None) -> SearchUsageInfo:
    return SearchUsageInfo()
