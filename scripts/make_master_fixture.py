#!/usr/bin/env python3
"""
Reconstruct a master-file FIXTURE from data/trip-data.json.

The real Europe_2026_Master_Trip_File.md is personal, gitignored and lives only
on one Mac, so extractor changes cannot be tested against it here. This rebuilds
a markdown file in the exact shape the extractor's two table parsers expect,
from data the extractor itself produced.

That gives a genuine round-trip test: run the extractor over this fixture and
the output must match the committed trip-data.json field for field, apart from
the generatedAt timestamp and the source filename.

This is a TEST fixture, not a substitute for the master file. It contains only
what survived into the JSON, so it cannot catch a change in how the master file
is written, only a regression in how the extractor reads it.
"""

import json
import sys
from pathlib import Path

TRACKER_COLUMNS = [
    "city", "neighbourhood", "name", "type", "why it made the list",
    "source and date", "confidence", "address or coordinates", "maps link",
    "opening hours", "approx cost", "priority", "best time", "notes",
]

MONTH_NAME = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def cell(v):
    """Markdown table cells cannot contain a raw pipe."""
    return str(v or "").replace("|", "/")


def build(data, extra_coords=None):
    """extra_coords: {place name: "lat, lon"} to inject into the address column,
    for exercising the coordinate path without touching the real file."""
    extra_coords = extra_coords or {}
    out = []
    a = out.append

    a("# Europe 2026 Master Trip File (FIXTURE, reconstructed for testing)")
    a("")
    a("## Part 4: day by day")
    a("")
    a("| Date | Day | Base for the night | The day |")
    a("| --- | --- | --- | --- |")
    for r in data["itinerary"]:
        y, m, d = (int(x) for x in r["date"].split("-"))
        date_txt = f"{d} {MONTH_NAME[m]}"
        day_txt = ("**[H]** " if r["heavy"] else "") + cell(r["notes"])
        a(f"| {date_txt} | {cell(r['dow'])} | {cell(r['base'])} | {day_txt} |")
    a("")
    a("## Part 8: master tracker")
    a("")
    a("| " + " | ".join(TRACKER_COLUMNS) + " |")
    a("| " + " | ".join("---" for _ in TRACKER_COLUMNS) + " |")
    for p in data["places"]:
        row = []
        for col in TRACKER_COLUMNS:
            v = p.get(col, "")
            if col == "address or coordinates" and p["name"] in extra_coords:
                v = extra_coords[p["name"]]
            row.append(cell(v))
        a("| " + " | ".join(row) + " |")
    a("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/trip-data.json")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/master_fixture.md")
    data = json.loads(src.read_text(encoding="utf-8"))
    dst.write_text(build(data), encoding="utf-8")
    print(f"Wrote {dst} from {src}")
    print(f"  {len(data['places'])} tracker rows, {len(data['itinerary'])} day rows")
