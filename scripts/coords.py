#!/usr/bin/env python3
"""
Shared coordinate helpers.

One implementation, imported by extract_trip_data.py, validate_trip_data.py,
validate_my_places.py, add_place.py and audit_places.py, so the parsing rules
cannot drift apart between the script that writes coordinates and the script
that checks them.

The M0 audit (4 September 2026) measured what the master file actually holds:

  * 75 of 406 places carry an explicit "lat, lon" pair in the
    `address or coordinates` column, and they are concentrated in three
    cities: Amsterdam 29/31, Ghent 27/27, Luxembourg City 19/19.
  * ZERO of the 406 `maps link` values carry coordinates. They are all
    name-search URLs of the form https://maps.google.com/?q=Some+Place+Name.
    The link patterns below are therefore currently unused, and are kept
    because the intended fix is to paste real place URLs into the master file,
    at which point they start matching.
  * There are no short links, so no redirect resolution is needed.

Nothing here makes a network call. Coordinates are only ever read from text the
user already saved; they are never geocoded, guessed or invented.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

# IUGG mean Earth radius, km. The same constant the browser side will use, so
# distances agree between the validator and the app.
R_KM = 6371.0088

COORD_SOURCES = ("tracker", "mapsLink", "geocoded", "cityCentroid", "none")
COORD_PRECISION = ("exact", "approx")

# A bare decimal pair. Both halves need a decimal point and at least three
# decimal places, so street numbers, postcodes and price ranges cannot match.
COORD_PAIR = re.compile(
    r"(?<![\d.])(-?\d{1,3}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})(?![\d.])"
)

# Short links carry no coordinates and would need one HTTP redirect each to
# resolve. That is slow, rate-limited and fragile, so they are reported as
# their own category rather than followed.
SHORT_LINK_HOSTS = ("maps.app.goo.gl", "goo.gl/maps", "g.co/kgs")

# Ordered most reliable first.
LINK_PATTERNS = (
    # !3d<lat>!4d<lon> is the place record: the pin itself.
    ("bang3d4d", re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")),
    # An explicit query parameter.
    ("query", re.compile(
        r"[?&](?:q|query|destination|daddr|ll|center|sll)="
        r"(-?\d+\.\d+)(?:,|%2C)(-?\d+\.\d+)", re.I)),
    # @lat,lon,zoom is the map viewport, not necessarily the pin. Accurate to
    # the neighbourhood at worst, so it is accepted but ranked last.
    ("at", re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")),
)


def fold(s) -> str:
    """NFD normalise and strip combining marks, so Gdansk matches Gdańsk."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s or ""))
        if not unicodedata.combining(c)
    )


def slugify(s) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in fold(s))
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def in_range(lat, lon) -> bool:
    return (
        isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        and -90 <= lat <= 90 and -180 <= lon <= 180
    )


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(a))


def coords_from_text(text):
    """An explicit pair sitting in free text. Returns (lat, lon) or None."""
    if not text:
        return None
    m = COORD_PAIR.search(str(text))
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    return (lat, lon) if in_range(lat, lon) else None


def coords_from_link(url):
    """Offline extraction from a maps URL. Returns (lat, lon, pattern) or None."""
    if not url:
        return None
    for label, pat in LINK_PATTERNS:
        m = pat.search(str(url))
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if in_range(lat, lon):
                return (lat, lon, label)
    return None


def is_short_link(url) -> bool:
    return bool(url) and any(h in str(url) for h in SHORT_LINK_HOSTS)


def derive_coords(place, centroid=None):
    """Resolve one place to (lat, lon, coordSource, coordPrecision).

    Order of trust: an explicit pair in the tracker's own address column, then
    coordinates embedded in a maps link, then the city centroid.

    A centroid is NEVER reported as exact. Presenting an inferred position as a
    precise one is the specific failure this function exists to prevent: the
    app shows an "approximate location" note off the back of coordPrecision,
    and the distance validator applies a looser bound to approx rows.
    """
    hit = coords_from_text(place.get("address or coordinates"))
    if hit:
        return hit[0], hit[1], "tracker", "exact"

    hit = coords_from_link(place.get("maps link"))
    if hit:
        return hit[0], hit[1], "mapsLink", "exact"

    if centroid and in_range(centroid.get("lat"), centroid.get("lon")):
        return centroid["lat"], centroid["lon"], "cityCentroid", "approx"

    return None, None, "none", None


def load_city_reference(path=None) -> dict:
    """Read scripts/city_reference.json into {canonical name: row}.

    This file is the single source of truth for city centroids, countries and
    timezones. The extractor used to carry its own hardcoded copy; keeping two
    lists in sync by hand is how they drift.
    """
    path = Path(path) if path else Path(__file__).resolve().parent / "city_reference.json"
    if not path.exists():
        raise SystemExit(f"FATAL: {path} not found. It is a required input.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FATAL: {path} is not valid JSON: {exc}")
    rows = doc.get("cities")
    if not rows:
        raise SystemExit(f"FATAL: {path} has no 'cities' array.")
    out = {}
    for row in rows:
        for field in ("name", "country", "lat", "lon", "tz", "slug"):
            if field not in row:
                raise SystemExit(
                    f"FATAL: {path}: city {row.get('name')!r} is missing '{field}'"
                )
        if not in_range(row["lat"], row["lon"]):
            raise SystemExit(
                f"FATAL: {path}: city {row['name']!r} has out-of-range coordinates"
            )
        out[row["name"]] = row
    return out


def alias_index(reference: dict) -> dict:
    """{folded lowercase spelling: canonical name} across names and aliases."""
    idx = {}
    for name, row in reference.items():
        for candidate in [name] + list(row.get("aliases", [])):
            idx[fold(candidate).strip().lower()] = name
    return idx
