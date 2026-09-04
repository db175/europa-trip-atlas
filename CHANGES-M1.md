# M1: personally added places

Append this to `CHANGES.md`. Built 4 September 2026, after the M0 audit.

Delivers request 2 from handoff v2 section 11: "add more places that I really
want to visit ... a new tag for that, that is personally added". Nothing from
Feature A (nearby suggestions) is in here; that is M2 and M3, and M0 showed it
still needs a coordinate decision.

## What was added

| File | Status | Purpose |
|---|---|---|
| `data/my-places.json` | new | Hand-maintained personal places. Committed, validated in CI, never written by the extractor. Ships empty. |
| `scripts/add_place.py` | new | One command to add a place. Resolves the city, derives coordinates, generates the id, validates, prints the diff. |
| `scripts/validate_my_places.py` | new | CI check. A malformed personal file fails the build instead of shipping. |
| `scripts/city_reference.json` | new | 28 cities with slug, ASCII and exonym aliases, country, centroid, IANA timezone. Hand-maintained input. |
| `scripts/audit_places.py` | new | The M0 read-only audit. Re-runnable after any data refresh. |
| `index.html` | modified | Source filter, personal-count line, cache-busting to `v=3` |
| `app.js` | modified | Personal load and merge, MY PICK chip, origin filter, separate counts |
| `styles.css` | modified | MY PICK chip, personal-count note, approximate-location note |
| `sw.js` | modified | Cache version to `v3`; `my-places.json` on the data path |
| `.github/workflows/pages.yml` | modified | Runs the second validator |

`data/trip-data.json` was **not** touched, and neither were
`extract_trip_data.py`, `validate_trip_data.py` or anything in `vendor/`.

## Decisions worth not reversing later

**Personal places live in a separate committed file, not in `trip-data.json`.**
That file is regenerated wholesale on every content refresh, so a row added
there survives until the next `extract_trip_data.py` run and then disappears
with no error. Silent data loss is the exact class of bug the rebuild fixed.

**They are counted separately and never mutate `meta`.** The hero stays at
406 / 27 / 76 / 149 whatever is in the personal file; the personal figure
renders on its own line underneath. Issue 4 of the original audit was the hero
being overwritten at runtime with different numbers, so the counts are kept
structurally apart rather than trusted not to collide. `state.places` holds the
pristine 406 and is what the charts describe; `state.personal` is separate; a
merged view is derived only where it is needed, in search, filters and the grid.

**A missing, malformed, wrong-version or stalled personal file never breaks the
page.** All four yield an empty list and exactly one console warning. A 404 is
warned about too rather than silently swallowed, so a file that fails to publish
is distinguishable from having no personal places yet. The load is also raced
against a 4 second deadline, so a stalled request cannot stop the 406 rendering.

**The centroid fallback is never written into `address or coordinates`.** When
no coordinates are supplied, `add_place.py` fills `lat`/`lon` from the city
centroid but leaves the tracker column empty and sets
`coordPrecision: "approx"`. Writing the centroid into the address column would
present an inferred position as a recorded one, and would look like real data to
anyone later pasting the row into the master file. The card says "approximate,
city centre until a map link or coordinates are added". The validator rejects
`coordPrecision: "exact"` alongside `coordSource: "cityCentroid"`.

**Rows carry all 14 tracker columns in tracker order**, so any entry can be
pasted into Part 8 of the master file verbatim, with `confidence: user` as a
fourth confidence value alongside Verified, Older and Unverified.

**`my-places.json` is not precached in `SHELL_FILES`.** `cache.addAll()` rejects
as a whole if any entry 404s, which would fail the service worker install
outright and leave the site with no worker at all. It goes through the same
network-first data path as `trip-data.json` instead, so it is cached on the
first successful load and available offline after that. Verified offline.

**MY PICK uses a glyph as well as colour**, matching the ◆ HEAVY DAY treatment,
so the distinction does not rely on colour alone. Contrast was computed, not
eyeballed: `--lime` on `--deep` is 10.24:1 against an AA requirement of 4.5:1,
measured again in the browser against live computed styles. The chip carries its
own dark background, so the four page background tokens do not affect its text
contrast; its edge against them is a non-text boundary (SC 1.4.11, 3:1) and
clears at 12.68:1 or better on all four. The personal-count line uses
`--accent-on-deep` on the hero panel, 5.47:1 once the panel's translucent white
overlay is composited in.

## Verification

36 of 36 integration assertions pass in headless Chromium, covering: the file
absent, present, malformed, and wrong-version; hero stats unchanged in every
case; the origin filter; searchability; the chip and its live contrast; the
approximate-location label; offline via the service worker; and a forced throw
inside the stats step leaving Explore and Schedule alive.

Regressions re-checked and still holding: hero 406 / 27 / 76 / 149; route strip
22 buttons; itinerary 76 rows; both 9 December branches rendering; priority
donut showing all three values including "If nearby"; and search still not
matching on the maps link ("https", "com" and "maps.google" do not return
everything).

Both CI validators pass on the shipped state. A file with a bad priority, an
unknown city, a missing tracker column and a centroid claiming exactness fails
with all four errors reported.

## Known limitations

- The in-browser quick add (M5) is not built, as recommended in section 14.8.
  Adding a place needs the command line.
- `scripts/export_for_master.py` (section 14.7) is not built. Personal places
  accumulate in the second file until moved across by hand.
- Personal places do not yet participate in nearby ranking, because there is no
  nearby feature yet. Their `lat`/`lon` and `coordSource` fields are already in
  the shape M2 expects, so no migration will be needed.
