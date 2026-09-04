#!/usr/bin/env python3
"""
scripts/parse_hours.py
Parses raw opening hours strings into structured objects.

Hard rules (Section 13.7):
- The original string is always preserved in `raw`.
- Anything unrecognised becomes `ok: false`.
"""

import re
from typing import Any, Dict, List, Optional

RE_TIME_RANGE = re.compile(r'^\s*(\d{1,2})(?::(\d{2}))?\s*[-–—]\s*(\d{1,2})(?::(\d{2}))?\s*$')

def fmt_time(h_str: str, m_str: Optional[str]) -> str:
    h = int(h_str)
    m = int(m_str) if m_str else 0
    return f"{h:02d}:{m:02d}"

def parse_hours_str(raw: str) -> Dict[str, Any]:
    raw_clean = (raw or "").strip()
    if not raw_clean or raw_clean.lower() in ("-", "—", "–", "n/a", "check", "varies", "unknown"):
        return {"ok": False, "raw": raw_clean, "reason": "unspecified"}

    v = raw_clean.lower().lstrip("~").strip()

    # Pattern: 09:00-18:00 or 9-18 or 9:00 - 18:00
    m = RE_TIME_RANGE.match(v)
    if m:
        open_time = fmt_time(m.group(1), m.group(2))
        close_time = fmt_time(m.group(3), m.group(4))
        slot = {"open": open_time, "close": close_time}
        # Applies Mon-Sun
        weekly = [ [slot] for _ in range(7) ]
        return {
            "ok": True,
            "weekly": weekly,
            "notes": "",
            "raw": raw_clean
        }

    # "24/7" or "open" or "24h" or "open access"
    if v in ("24/7", "24h", "open", "open access"):
        slot = {"open": "00:00", "close": "23:59"}
        weekly = [ [slot] for _ in range(7) ]
        return {
            "ok": True,
            "weekly": weekly,
            "notes": "24 hours",
            "raw": raw_clean
        }

    # Default fallback for complex/unrecognised strings
    return {
        "ok": False,
        "raw": raw_clean,
        "reason": "unrecognised_format"
    }

if __name__ == "__main__":
    import sys
    test_str = sys.argv[1] if len(sys.argv) > 1 else "09:00-18:00"
    import json
    print(json.dumps(parse_hours_str(test_str), indent=2))
