# Europa Trip Atlas

This is a static website: it has no login, database, or server-side setup. That makes it easy to publish privately or publicly on any static host and open from a phone, tablet, or computer.

## Publish it

1. Create a new site on a static host such as Netlify, Vercel, or GitHub Pages.
2. Upload the contents of this `site` folder as the published folder.
3. Open the generated link on any device.

## Preview locally

From the project folder, run:

```sh
python3 -m http.server 4173 --directory site
```

Then visit `http://localhost:4173`.

## Refresh from the tracker

The extraction script at `../scripts/extract_trip_data.py` is ready to regenerate `data/trip-data.json` from the original Excel tracker. It expects the workbook at the same Downloads path supplied with this project. Replace the output JSON and republish the `site` folder.
