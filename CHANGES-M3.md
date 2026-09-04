# M3: the city view

Append this to `CHANGES.md` after the M2 entry. Built 4 September 2026.

Delivers the request from handoff v3 section 5: *"can you add a city map
feature. when i click the city i am in it should lead me to the city map and
all the places i would like to visit"*, narrowed to *"just the city maps and
the major neighborhoods i should know about"*.

A city page now lives at `#city/<slug>`. It is bookmarkable, survives the back
button, and lists the areas of a city with its saved places under each. A map
sits alongside, showing only the places that have a real recorded position.

## What changed

| File | Status | Purpose |
|---|---|---|
| `app.js` | modified | The city view, hash routing, coordinate resolution, entry points |
| `index.html` | modified | The `#cityView` section; `?v=4` |
| `styles.css` | modified | City view styles, appended; nothing existing was altered |
| `sw.js` | modified | Cache version `v3` → `v4`, `?v=4` on the two shell assets |

**No new files.** Everything the feature needs fits inside the four files
already in `SHELL_FILES`, so nothing had to be added to the precache list where
one 404 would fail `cache.addAll()` and leave the site with no service worker.

`data/trip-data.json` and `data/my-places.json` are untouched.

## Why the list leads and the map follows

`scripts/audit_places.py` measured 75 of 406 places with a real position, all
of them in Amsterdam (29 of 31), Ghent (27 of 27) and Luxembourg City (19 of
19). The other 24 cities have none. Areas, by contrast, are recorded on 399 of
406.

So a map-led city page would be blank for 24 of 27 cities, and could not ship
until hundreds of coordinates were filled by hand. The areas lead instead. As
coordinates get filled, places move from the list onto the map on their own,
and no work done now is wasted either way.

## The centroid trap

The committed `data/trip-data.json` is still the pre-M2 file, so the 75 real
positions sit as text in the `address or coordinates` column. After the next
extractor run they become `lat`/`lon` fields, **and so do the other 331**:
`derive_coords()` falls those back to the city centroid, flagged
`coordSource: "cityCentroid"`, `coordPrecision: "approx"`.

That matters here more than anywhere else in the app. Reading `p.lat` without
checking the precision would put 23 markers on one pixel in Gdańsk, which is
the exact failure the whole design exists to avoid. `exactCoords()` therefore:

- rejects on `coordSource === 'cityCentroid'` **or** `coordPrecision ===
  'approx'`, so losing either field in a hand-edited row still cannot promote
  an inferred position to a real one;
- otherwise takes `lat`/`lon` when they are present and in range;
- otherwise parses the `address or coordinates` column with the same rule as
  `COORD_PAIR` in `scripts/coords.py`.

Both shapes were tested. Gdańsk plots zero markers either way, and the page
says so in words rather than showing an empty map and letting it imply there is
nothing there.

The JS regex is written **without a lookbehind**, unlike the Python one. An
unsupported `(?<!...)` is a parse-time `SyntaxError`, which would take the whole
of `app.js` down on an older browser rather than failing one function.

## `cities[].slug` does not exist yet

Handoff v3 section 5 says `cities[].slug` already exists for the hash route. It
does not: the committed JSON is pre-M2. `scripts/city_reference.json` has the
slugs but lives under `scripts/` and is never fetched by the page.

So the app uses `state.cities[name].slug` when it is there and derives the slug
otherwise. The derivation is asserted against all 28 names in
`city_reference.json` in the test suite rather than assumed to match, and it
does match, including `Gdańsk` → `gdansk`, `València` → `valencia`,
`Peñíscola` → `peniscola` and `Luxembourg City` → `luxembourg-city`.

## What a city page shows

1. **Areas ranked by weight**, place count then Must count, each opening to its
   places. Gdańsk reads `Main Town, 10 places · 4 must` then
   `Old Town, 4 places · 2 must`. The densest one opens by default; the rest
   start closed so the shape of the city is readable in one screen.
2. **Single-place areas collapsed** into one "N other areas" group. 132 of the
   208 (city, area) pairs hold exactly one place and would otherwise bury the
   areas that actually cluster.
3. **Day trips in their own collapsed section**, headed "3 trips out of
   Gdańsk". They are kept out of the map's `fitBounds` but still plotted, with
   a square marker rather than a round one so the two kinds are told apart
   without relying on colour. Rotterdam is 57 km from Amsterdam and would
   otherwise zoom the city out to uselessness.
4. **A coverage line in words**: "29 of 31 places have a recorded location. The
   other 2 are listed here but not on the map." Where there are none it says so
   and points at `scripts/coord_worksheet.py`.
5. **Personal places merged in**, carrying their `★ MY PICK` chip, counted on
   the city page but never into the hero.

All seven places with a blank `neighbourhood` are day trips (Bruges, Antwerp,
Brussels, Utrecht, Haarlem, Rotterdam, Zaanse Schans), so pulling day trips out
empties the "area not recorded" bucket entirely. The bucket is still built, in
case a future refresh adds a blank that is not a day trip.

## Behaviour change: what the route strip does

**The route chips now open the city page instead of only filtering Explore.**
This is the one thing here that changes something that already worked, and it
was done because the request was specifically that clicking a city should lead
to its map.

Nothing is lost. The city page carries a `Show all N in Explore` button that
runs the old `selectCity()` filter, and the city dropdown in Explore is
unchanged. The map popups gained an "Open the city page" link, as a plain hash
anchor so it keeps working if a handler ever throws and can be opened in a new
tab. The hero's next-stop city is a link too, when it has places, which is the
shortest path from "where am I" to "what is near me".

## Guards

- `routeFromHash` runs inside `step()`, last in `init()`, so a bad hash in a
  bookmark cannot stop the rest of the page rendering behind it.
- The map is built inside its own `step('cityMap', ...)`, after the areas are
  already in the DOM. A Leaflet failure costs the map and nothing else.
- An unknown slug renders a "No such city" page rather than silently showing
  the homepage, so a stale bookmark is diagnosable.
- Back is `history.replaceState`, not a push, so it goes where the user came
  from instead of bouncing between the city page and the homepage.
- The city map is a second Leaflet instance, torn down on close, so it never
  shares a container or a zoom level with the route map.

## Still true, still a problem

`sw.js` does not cache map tiles, because the OSM tile usage policy prohibits
prefetching them for offline use
(<https://operations.osmfoundation.org/policies/tiles/>). Offline, the basemap
is blank.

At country zoom that is survivable: the route shape still reads. **At city zoom
it is not.** Markers floating on white with no streets are close to useless,
and standing in a city on roaming data is exactly when this page would be
opened. This strengthens the case for the CARTO key, still open. The tile
provider was not changed.

## Verification

96 integration assertions in headless Chromium, 82 in the main suite plus 14
against a post-M2 data file built with `make_master_fixture.py` and the
extractor.

Regressions confirmed intact: hero 406 / 27 / 76 / 149, route strip 22 buttons,
itinerary 76 rows, both 9 December branches, "If nearby" in the donut, and
search on "https", "com" and "maps.google" still not matching everything.

City view: area order and counts against the audit figures, singleton
collapsing, day-trip separation, marker counts equal to the exact-coordinate
counts in Ghent (27), Amsterdam (29 of 31) and Gdańsk (0), coverage wording,
hash routing including an unknown slug, an accented city resolved from its
ASCII slug, browser Back, and the hand-off to Explore.

Degradation: Leaflet aborted mid-load, `my-places.json` missing / malformed /
wrong-version (each leaves the page working with exactly one console warning),
a forced throw inside the city map, and offline.

Contrast measured against live computed styles on all ten new text elements,
lowest 5.20:1 at 11px, against a 4.5:1 requirement
(<https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html>). The two
marker kinds differ in shape as well as colour (SC 1.4.1).

## Deploying

```bash
SRC=~/Downloads/atlas-m3
cd ~/europa-trip-atlas
cp -a "$SRC"/. .
python3 scripts/validate_trip_data.py data/trip-data.json
python3 scripts/validate_my_places.py data/my-places.json
python3 -m http.server 4174
git add -A && git commit -m "M3: city view" && git push && gh run watch
```

The package holds only the four changed files and these two notes. It does not
contain `data/trip-data.json`, so it cannot disturb it. Hard-reload with
Cmd-Shift-R afterwards: the cache version moved to `v4`, but the old service
worker will serve the old shell until it is claimed.
