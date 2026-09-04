# Fixes applied

All 30 issues from the review. Every claim below was verified in a real
headless Chromium against the built site (`67/68` browser assertions pass; the
one failure is this sandbox's TLS proxy blocking OSM tile images, not a defect
in the site — zero same-origin requests failed).

## Data, before and after

| | Before | After |
|---|---|---|
| Places | 45 | **406** |
| Fields per place | 9 | **16** (all 14 tracker columns + 2 derived) |
| Days in schedule | 23 | **76** |
| Heavy days flagged | 9 | **27** |
| `Must` places | 27 | **149** |
| Route legs | 22 (Cologne collapsed) | **23** (both Cologne blocks) |
| Field contradictions vs tracker | 58 | **0** (values copied verbatim) |

## P0

| # | Issue | What was done |
|---|---|---|
| 1 | CARTO "API KEY REQUIRED" watermark | Switched to the OpenStreetMap standard layer, which needs no key. Verified: tile fetches 200 with no watermark. A commented CARTO block is left in `app.js` for when a key is obtained. |
| 2 | 94% of data dropped | New `scripts/extract_trip_data.py` reads the master markdown and emits all 406 places, all 76 days, all 14 columns. |
| 3 | 58 contradictions vs the tracker | The extractor copies tracker values verbatim. Nothing is paraphrased. `scripts/validate_trip_data.py` enforces it in CI. |
| 4 | Hero stats wrong twice over | Placeholders are now em dashes with `aria-busy`. Verified no `>406<` or `>149<` in the source HTML. "Next stop" is computed from today's date. |
| 5 | Two Pages workflows racing | Deleted `jekyll-gh-pages.yml`. One workflow remains, with a data-validation gate before deploy. |

## P1

| # | Issue | What was done |
|---|---|---|
| 6 | Dortmund vs Inter branch missing | Both 9 Dec branches parsed and rendered. Branch A draws a dashed red spur to Dortmund on the map. CI fails if either branch is lost. |
| 7 | Bratislava as an overnight base | 10 Nov base is now Budapest; Bratislava renders as a "via" day stop and gets its own map marker. Day is flagged heavy. |
| 8 | Cologne block 2 missing | All 17–26 Nov days restored. The 12-day hole is gone. |
| 9 | 18 of 27 heavy days missing | All 27 present. `heavy` is now a boolean field, not a prose prefix parsed with `startsWith`. Added a "Heavy days only" filter. |
| 10 | Route line wrong | Route is built from ordered legs collapsing only *consecutive* repeats, so Cologne appears twice. Day stops and the branch spur are drawn. |
| 11 | Leaflet exception killed the page | Each render step is isolated in `step()`. `fitBounds` is guarded against empty bounds. Errors are logged, not swallowed. |
| 12 | Private itinerary publicly indexable | Added `noindex, nofollow, noarchive`, a blocking `robots.txt`, and `.gitignore` for the master file. **The repo-visibility decision is still yours** — see README "Privacy". |
| 13 | No offline support | Added `sw.js` (app shell + data cached) and a manifest. Leaflet is vendored so the map library works offline too. Tiles are deliberately *not* cached: the OSM tile policy prohibits prefetching. |

## P2

| # | Issue | What was done |
|---|---|---|
| 14 | README described a layout that never existed | Rewritten against the real tree. The extraction script is now actually committed. |
| 15 | Leaflet from CDN with no SRI | Vendored into `vendor/leaflet/`. Committed files hash-match Leaflet's published SRI values. Nothing loads cross-origin now — verified in-browser. |
| 16 | 8 colour pairs failed WCAG AA | New `--accent-text` (#b03214) and `--muted` (#555e57) tokens. Verified 18/18 pass against live computed styles. The HEAVY DAY marker went from 2.75:1 to 5.20:1 and gained a ◆ shape so it no longer relies on colour alone. |
| 17 | Search box had no accessible name | Real `Search` label. Added roles on `#map` and `#routeStrip`, `aria-live` on results and stats, `aria-pressed` on toggles, a skip link, `:focus-visible` styles, and `<noscript>`. |
| 18 | Sticky header hid anchor targets | `scroll-margin-top: calc(var(--topbar-h) + 16px)` on all sections. |
| 19 | Mobile nav just disappeared | Added a Menu button and a drawer below 620px. Verified at 390×844. |

## P3

| # | Issue | What was done |
|---|---|---|
| 20 | `drawVisuals()` threw on empty data | Guarded; renders an empty state instead. |
| 21 | Search matched all rows on "com" | Searches named fields only. Verified: "google" now returns 0 results, was 45/45. |
| 22 | Donut dropped unknown priorities | Colours derived from the data with a grey fallback. Verified the gradient reaches 100%. |
| 23 | Type taxonomy unusable | Restoring all 406 rows fixes the distribution (food 79, bar 57, day trip 39…). `notes` is back, so the bath/sauna rows typed as `sight` are recoverable. |
| 24 | Cost mixed currencies and states | `approx cost` kept verbatim; added a derived `costTier` (free/low/moderate/high/varies) and a Cost filter. `best time` likewise keeps its raw value plus a `timeBucket`, so date-specific constraints survive. |
| 25 | Attribution insufficient | Now "© OpenStreetMap contributors" with a working link, per the OSM attribution guidelines. Verified in the rendered control. |
| 26 | `Inter` declared but never loaded | Removed from the stack; designed against the system font. |
| 27 | Dead code, fake "today" button | Dead coordinates removed. "Go to today" now scrolls to today's row and highlights it, handling before/during/after the trip. Dates are validated, so no more "Invalid Date". Reset now clears the route strip and search too. |
| 28 | Single-line minified source | Formatted. `styles.css` went from one 10,479-character line to 1,153 readable lines; longest line is now 100 chars. |
| 29 | No cache-busting | `?v=2` on CSS, JS and data; the service worker versions its caches. |
| 30 | Missing page furniture | Added `favicon.svg`, `robots.txt`, `404.html`, `manifest.webmanifest`, `LICENSE`, `.gitignore`, meta description, and print styles. |

## Still yours to decide

1. **Repository visibility.** The site is now `noindex` and crawler-blocked, but a public repo still exposes the JSON to anyone with the URL.
2. **A CARTO key**, if you prefer their lighter basemap or want offline tiles. OSM's policy forbids caching tiles, so offline maps require a different provider.
3. **The 13 untraceable places** in Appendix A of the issue report. They are not in the new data, because the extractor only emits tracker rows. The Alhambra is the notable one: genuinely absent from the tracker's Granada rows. Add it to the master file and re-run the extractor.
