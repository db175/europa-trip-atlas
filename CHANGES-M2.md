# M2: coordinates into the pipeline

Append this to `CHANGES.md` after the M1 entry. Built 4 September 2026.

Groundwork for Feature A (nearby suggestions). No user-visible change: the site
looks and behaves exactly as it did after M1. What changes is that every place
now carries a resolved position and a record of where that position came from,
which is what M3 needs to rank anything by distance.

Follows the coordinate decision taken after the M0 audit: **Option B, fill the
master file, Gdansk first.** No geocoding. Nothing here makes a network call.

## What was added

| File | Status | Purpose |
|---|---|---|
| `scripts/coords.py` | new | One implementation of coordinate parsing, distance and city lookup, imported by all five other scripts |
| `scripts/coord_worksheet.py` | new | Export a per-city CSV, fill in lat/lon, get back master-file rows to paste |
| `scripts/make_master_fixture.py` | new | Rebuilds a master-file fixture from the JSON, so extractor changes are testable without the real master file |
| `scripts/extract_trip_data.py` | modified | Emits `lat`, `lon`, `coordSource`, `coordPrecision`; cities gain `slug`, `tz`, `placeCount`; reads `city_reference.json` instead of its own city table |
| `scripts/validate_trip_data.py` | modified | Coordinate invariants from handoff section 13.5 |
| `scripts/add_place.py` | modified | Refactored onto `coords.py`; now also reads `!3d/!4d` and `@lat,lon` maps links |
| `scripts/audit_places.py` | modified | Refactored onto `coords.py`, 127 lines shorter, output byte-identical |

`data/trip-data.json` was not touched. It is still the pre-M2 file and stays
that way until you re-run the extractor against the master file yourself.

## The duplicate city table is gone

`extract_trip_data.py` carried its own hardcoded 28-city `CITIES` dict, and M1
added `scripts/city_reference.json` with the same 28 centroids. Two
hand-maintained copies of the same data drift apart the moment one is edited.
The extractor now reads the JSON file. The two were verified identical before
the switch, so no value changed.

`cities` entries in the output gain `slug`, `tz` and `placeCount`. The `tz`
values are IANA zone identifiers, each checked to exist in the system tz
database and to shift by one hour across 25 October 2026, the end of EU summer
time under Directive 2000/84/EC. That date falls inside the 26 September to
10 December window, so a single UTC offset would make every "open now" answer
wrong by an hour for the back half of the trip. `placeCount` counts tracker
places only. The structure stays an object keyed by city name rather than
becoming the array section 13.4 proposed: nothing reads it positionally, and a
name-keyed lookup is what both the app and the validator want.

## Coordinates are read, never invented

`derive_coords()` tries, in descending order of trust: an explicit pair in the
tracker's own `address or coordinates` column, then a pair embedded in the
`maps link`, then the city centroid. A centroid is always flagged
`coordPrecision: "approx"` and never published as exact. The extractor prints
coverage on every run, so a refresh that improves or regresses it is visible
immediately rather than discovered later.

Current coverage is **75 of 406 exact, 18.5%**, which reproduces the M0 audit
figure exactly from a completely separate code path.

## No allowlist was needed

Handoff section 13.5 proposed a hand-curated allowlist of legitimate day trips
to stop the centroid-distance check firing on them, seeded from the 20 largest
distances. The M0 audit made that unnecessary: **every place further than 5 km
from its centroid is already typed `day trip` in the tracker**, including
Auschwitz-Birkenau, Westerplatte, Malbork Castle, Rotterdam and Zaanse Schans.
The validator keys on the type column instead, so there is nothing to maintain.

Bounds are 12 km for an ordinary place and 150 km for a day trip. Measured
maxima are 3.8 km and 57.4 km, so both have real headroom, while sitting orders
of magnitude below the error a parsing bug produces.

## The worksheet keeps the street address

`coord_worksheet.py --apply` appends the pair in brackets rather than
overwriting: `ul. Elzbietanska 4/8 (54.3533, 18.6497)`. The column is "address
or coordinates", holding both loses nothing, the row stays readable by a human,
and the extractor finds the pair anywhere in the string. The coordinate pattern
requires a decimal point and three decimal places on both halves, so a street
number like `4/8` cannot be mistaken for a coordinate. Verified.

Rows left blank are skipped, so a city can be filled a few places at a time
without losing work. Filled rows are sanity-checked against the city centroid
before being printed, so a swapped pair is caught at the worksheet rather than
reaching the master file.

## Testing without the master file

The master file is gitignored and lives only on one Mac, so extractor changes
could not previously be tested here at all. `make_master_fixture.py`
reconstructs a master-file fixture from `trip-data.json` in the exact shape the
two table parsers expect. Running the unmodified extractor over it reproduced
the committed JSON field for field, which is what made the M2 changes safe to
make.

This is a test fixture, not a substitute for the master file. It contains only
what survived into the JSON, so it catches a regression in how the extractor
reads, not a change in how the master file is written.

## Verification

- Round trip: extractor output matches committed `trip-data.json` exactly, with
  `lat`, `lon`, `coordSource`, `coordPrecision` added to places and `slug`,
  `tz`, `placeCount` added to cities. No existing field changed on any of the
  406 places, and `route`, `itinerary` and `meta` are byte-identical.
- `placeCount` across all cities sums to 406.
- 7 of 7 injected coordinate faults caught: latitude and longitude swapped
  (6,306 km), decimal point misplaced (4,965 km), wrong hemisphere sign
  (11,033 km), a centroid published as exact, an unknown `coordSource`, only
  one of lat/lon present, and an out-of-range latitude.
- No false positive: Rotterdam at 57 km under Amsterdam still passes.
- Worksheet rejects a swapped pair, a half-filled row and non-numeric input,
  and prints nothing for them.
- End to end with three Gdansk rows filled: coverage 75 to 78, street address
  preserved, `4/8` not misread, validator passes.
- The app renders correctly against both the pre-M2 and post-M2 data shapes:
  36 of 36 M1 assertions pass on each.
- `audit_places.py` output is byte-identical after being refactored onto the
  shared module.

## What is still not built

M3 (the nearby panel) and M4 (opening hours). M3 is now unblocked technically,
but on current data 328 of 406 places resolve to a city centroid, so a distance
ranking would put every place in 24 of the 27 cities at the same point. Filling
Gdansk is what makes M3 worth building.
