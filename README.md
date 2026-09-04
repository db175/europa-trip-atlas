# Europa Trip Atlas

A single-page, static view of a Europe trip running 26 September to 10 December
2026: 76 days, 75 nights, 27 cities, 406 saved places.

No build step, no framework, no server. Open `index.html` through any static
host and it works.

---

## Privacy — read this before making the repository public

This site publishes **which city one household sleeps in on each of 76
consecutive nights**. That is a machine-readable schedule of when a home is
empty.

The repository currently ships with:

- `<meta name="robots" content="noindex, nofollow, noarchive">` in `index.html`
- `robots.txt` disallowing all crawlers
- `.gitignore` excluding `Europe_2026_Master_Trip_File.md` and any `.xlsx`

Those keep it out of search results. They do **not** make it private: anyone
with the URL can still read it, and a public repo exposes the JSON directly.

If it should genuinely be private, make the repository private and use a
private Pages deployment, or move to a host with access control. Check current
GitHub terms first, since private Pages requires a paid plan.

---

## Layout

```
.
├── index.html                     the whole site
├── styles.css
├── app.js
├── sw.js                          offline shell
├── manifest.webmanifest
├── favicon.svg
├── 404.html
├── robots.txt
├── data/
│   └── trip-data.json             generated — do not hand-edit
├── scripts/
│   ├── extract_trip_data.py       master markdown -> trip-data.json
│   └── validate_trip_data.py      invariant checks, also run in CI
└── .github/workflows/pages.yml    the only deployment workflow
```

There is no `site/` directory. An earlier README described one, along with a
`scripts/extract_trip_data.py` that was never committed; neither has ever
existed in this repository's history.

---

## Refreshing the data

`data/trip-data.json` is generated. The source of truth is
`Europe_2026_Master_Trip_File.md`, which is deliberately not committed.

```sh
python3 scripts/extract_trip_data.py \
    --master /path/to/Europe_2026_Master_Trip_File.md \
    --out data/trip-data.json
```

The extractor asserts its own output and exits non-zero if anything is off:
wrong number of days, a calendar gap, a missing tracker column, an unmappable
city, or a lost 9 December branch. Then commit the regenerated JSON.

`scripts/validate_trip_data.py` re-checks those invariants against the
committed JSON alone, without needing the master file, and runs on every push
so a bad data commit cannot reach Pages.

### What the extractor guarantees

| Invariant | Why it exists |
|---|---|
| All 406 tracker rows | A previous data file shipped 45 |
| All 76 calendar days, no gaps | A previous data file shipped 23, leaving a 12-day hole |
| All 14 Section 16 columns | `opening hours`, `notes`, `confidence`, `source and date` and `address` had been dropped |
| Values copied verbatim | 58 fields had drifted from the tracker |
| Both 9 December branches | The Dortmund vs Inter match had been dropped entirely |
| Route collapses only consecutive repeats | Cologne is visited twice and must appear twice |

---

## Preview locally

The page fetches `data/trip-data.json`, and browsers block `fetch` over
`file://`. Opening `index.html` by double-clicking will show a load error.
Serve it instead:

```sh
python3 -m http.server 4173
```

Then visit <http://localhost:4173>.

---

## Map tiles

`app.js` defaults to the OpenStreetMap standard layer, which needs no API key.

The previous build used CARTO's raster basemaps without a key. CARTO now
requires one for that endpoint and stamps `API KEY REQUIRED` diagonally across
every tile, and is retiring the raster service.

To switch to CARTO, request a key at <https://carto.com/basemaps/apikey/> and
swap the commented `TILES` block at the top of `app.js`.

**Offline maps.** `sw.js` caches the app shell and the trip data, so the
itinerary and all 406 places work offline. It does **not** cache map tiles,
because the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
prohibits prefetching for offline use. If you need offline maps, move to a
provider that permits it or self-host, then add the tile host to `sw.js`.

---

## Accessibility

Colour tokens in `styles.css` were chosen by computing WCAG relative-luminance
contrast ratios against every background they appear on, and the ratios are
noted inline. The previous palette failed
[SC 1.4.3](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)
on eight pairs, the worst being the HEAVY DAY marker at 2.75:1.

If you change `--accent-text` or `--muted`, re-check them against `--paper`
(`#f7f4ed`), `--warm` (`#efe8da`), `--card` (`#fbfaf6`) and `--chip`
(`#eae5d9`). All four need at least 4.5:1, since every use is small text.

---

## Licence

MIT for the code. The trip content is personal and not licensed for reuse.
