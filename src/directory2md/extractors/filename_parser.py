"""Filename parsing utilities to extract timestamp, date, and clean title."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Optional, Tuple


# Regex patterns for dates and timestamps in filenames
DATE_TIME_PATTERNS = [
    # YYYY-MM-DD_HH-MM-SS or YYYY-MM-DD_HHMMSS or YYYY-MM-DDTHH-MM-SS
    re.compile(
        r"^(?P<year>\d{4})[-_.](?P<month>\d{2})[-_.](?P<day>\d{2})[T_ -]"
        r"(?P<hour>\d{2})[-_.:](?P<min>\d{2})(?:[-_.:](?P<sec>\d{2}))?(?:[_\s-]+(?P<title>.*))?$"
    ),
    # YYYYMMDD_HHMMSS
    re.compile(
        r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})[T_ -]"
        r"(?P<hour>\d{2})(?P<min>\d{2})(?P<sec>\d{2})(?:[_\s-]+(?P<title>.*))?$"
    ),
    # YYYY-MM-DD
    re.compile(
        r"^(?P<year>\d{4})[-_.](?P<month>\d{2})[-_.](?P<day>\d{2})(?:[_\s-]+(?P<title>.*))?$"
    ),
    # YYYYMMDD
    re.compile(
        r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?:[_\s-]+(?P<title>.*))?$"
    ),
]


def parse_filename(
    filepath: Path,
) -> Tuple[Optional[str], Optional[str], Optional[datetime], str]:
    """Parse a filename to extract any embedded date, time, and human-readable title.

    Args:
        filepath: Path to the target file.

    Returns:
        Tuple of (date_str 'YYYY-MM-DD', time_str 'HH:MM:SS', datetime_obj, clean_title).
    """
    stem = filepath.stem

    for pat in DATE_TIME_PATTERNS:
        match = pat.match(stem)
        if match:
            gd = match.groupdict()
            year = int(gd["year"])
            month = int(gd["month"])
            day = int(gd["day"])

            hour = int(gd.get("hour") or 0)
            minute = int(gd.get("min") or 0)
            second = int(gd.get("sec") or 0)

            if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                try:
                    dt = datetime(year, month, day, hour, minute, second)
                    date_str = f"{year:04d}-{month:02d}-{day:02d}"
                    time_str = f"{hour:02d}:{minute:02d}:{second:02d}" if "hour" in gd and gd["hour"] else None

                    raw_title = gd.get("title") or ""
                    clean_title = re.sub(r"[_-]+", " ", raw_title).strip()
                    if not clean_title:
                        clean_title = stem

                    return date_str, time_str, dt, clean_title
                except ValueError:
                    pass

    # No date pattern matched; use clean stem as title
    clean_title = re.sub(r"[_-]+", " ", stem).strip() or stem
    return None, None, None, clean_title
