# Master file corrections, Part 8 `neighbourhood` column

Produced 4 September 2026 from `data/trip-data.json`. Every row below was
matched by city and place name against the committed data, not typed from
memory.

These are **master file edits, not JSON edits.** `data/trip-data.json` is
generated; hand-editing it is undone by the next extractor run. Change the
rows in Part 8 of `Europe_2026_Master_Trip_File.md`, then:

```bash
python3 scripts/extract_trip_data.py \
    --master /path/to/Europe_2026_Master_Trip_File.md \
    --out data/trip-data.json
python3 scripts/validate_trip_data.py data/trip-data.json
git add -A && git commit -m "Canonicalise area names" && git push
```

Nothing in the city view depends on these edits. It works today with the split
names; the areas simply read better once they are merged. Blocks are separate
so any one can be applied or skipped on its own.

---

## Block A: duplicate area names, 22 rows

Rule applied: where the same area is recorded under two names, the simpler
English form wins. In all five cities below, that form is already present in
the data on at least one row, so nothing is being invented.

Luxembourg's three names are one place: the city's own tourism site presents
Ville Haute as Luxembourg's old town, and the UNESCO-inscribed Old City of
Luxembourg lies mainly in Ville Haute
(<https://luxembourg-city.com/en/about-luxembourg-city/districts/ville-haute>,
<https://en.wikipedia.org/wiki/Old_City_of_Luxembourg>). Grund, Clausen,
Pfaffenthal, Gare and Kirchberg are separate quarters and are left alone.

| City | Place | Current | Change to |
|---|---|---|---|
| Tallinn | Old Town | `Vanalinn` | `Old Town` |
| Tallinn | Philly Joe's | `Vanalinn` | `Old Town` |
| Tallinn | III Draakon | `Vanalinn` | `Old Town` |
| Tallinn | KGB Prison Cells | `Vanalinn` | `Old Town` |
| Riga | Folkklubs Ala Pagrabs | `Vecrīga` | `Old Town` |
| Riga | Old Town | `Vecrīga` | `Old Town` |
| Riga | Black Magic Bar | `Vecrīga` | `Old Town` |
| Riga | Pelmeņi XL | `Vecrīga` | `Old Town` |
| Riga | Big Bad Bagels | `Vecrīga` | `Old Town` |
| Vilnius | Old Town | `Senamiestis` | `Old Town` |
| Vilnius | Bix Baras | `Senamiestis` | `Old Town` |
| Vilnius | Bernardine Garden & St Anne's | `Senamiestis` | `Old Town` |
| Prague | Korzo Národní (Velvet Revolution) | `Nové Město` | `New Town` |
| Prague | Original Beer Spa | `Nové Město` | `New Town` |
| Luxembourg City | Bock Casemates | `Ville Haute` | `Old Town` |
| Luxembourg City | Chemin de la Corniche | `Ville Haute` | `Old Town` |
| Luxembourg City | Brasserie du Cercle (Place d'Armes) | `Ville Haute` | `Old Town` |
| Luxembourg City | Place d'Armes vendors | `Ville Haute` | `Old Town` |
| Luxembourg City | Döner counters, Place d'Armes | `Ville Haute` | `Old Town` |
| Luxembourg City | Am Tiirmschen | `Old town` | `Old Town` |
| Luxembourg City | Wenzel Circular Walk | `Old town` | `Old Town` |
| Luxembourg City | Brasserie Um Dierfgen | `City centre` | `Old Town` |

Resulting areas: Tallinn Old Town 5, Riga Old Town 6, Vilnius Old Town 4,
Prague New Town 3, Luxembourg City Old Town 8.

Five cities ending up with an area called "Old Town" is fine. Areas are keyed
on the **(city, area)** pair, so they never collide.

---

## Block B: Cologne, 7 rows. Decide before applying.

This one is not like Block A, which is why it is separated.

`Altstadt` and `Altstadt-Nord` are not two names for the same area.
Altstadt-Nord and Altstadt-Süd are separate official Stadtteile inside the
Innenstadt district; Altstadt-Nord is the northern half of the old town, not
the whole of it (<https://en.wikipedia.org/wiki/Innenstadt,_Cologne>). Merging
them loses that distinction. Applying the same rule as Block A gives:

| City | Place | Current | Change to |
|---|---|---|---|
| Cologne | Heinzels Wintermärchen | `Altstadt` | `Old Town` |
| Cologne | Weihnachtsmarkt am Kölner Dom | `Altstadt` | `Old Town` |
| Cologne | Kölner Dom | `Altstadt` | `Old Town` |
| Cologne | Max Stark | `Altstadt` | `Old Town` |
| Cologne | Römerturm & Praetorium | `Altstadt` | `Old Town` |
| Cologne | Rievkoochebud | `Altstadt` | `Old Town` |
| Cologne | NS-Dokumentationszentrum (EL-DE Haus) | `Altstadt-Nord` | `Old Town` |

Two further rows sit in the same family and are **not** in the table above,
because folding them in is a bigger claim than the handoff made:

- `Altstadt-Süd` (1 place). Merging it too would give a single Old Town of 9.
- `Altstadt/Deutz` (1 place). Deutz is across the Rhine, so this row spans two
  areas and is really the same shape of problem as Madrid below.

Three ways to go, in decreasing tidiness and decreasing fidelity:

1. Apply the table, and also move `Altstadt-Süd` to `Old Town`. One Old Town
   of 9, north/south distinction gone.
2. Apply the table as written. Old Town 7, Altstadt-Süd stays separate at 1,
   which then falls into the collapsed "other areas" group.
3. Skip Block B. Altstadt 6 and Altstadt-Nord 1 stay as two areas.

---

## Block C: the type value leaked into the area column

Split in two after checking each row, which changed the recommendation given
earlier: not all 17 of these should be blanked.

### C1: 15 rows, safe to blank

Every one of these is typed `day trip`, so the city view already pulls it into
the "trips out of" section and the area value is never displayed. Blanking is
tidy-up with no visible effect.

| City | Place | Current |
|---|---|---|
| Cologne | Aachen | `day trip` |
| Cologne | Bonn | `day trip` |
| Cologne | Brühl Augustusburg | `day trip` |
| Copenhagen | Helsingør / Kronborg | `day trip` |
| Copenhagen | Louisiana Museum | `day trip` |
| Copenhagen | Roskilde | `day trip` |
| Riga | Cēsis | `day trip` |
| Riga | Jūrmala | `day trip` |
| Riga | Sigulda | `day trip` |
| Tallinn | Lahemaa National Park | `day trip` |
| Tallinn | Tartu | `day trip` |
| Vilnius | Kaunas | `day trip` |
| Vilnius | Trakai | `day trip` |
| Venice | Padua (Scrovegni) | `mainland` |
| Venice | Verona | `mainland` |

### C2: 2 rows, recommend leaving alone

These two are **not** day trips, so blanking them costs information and gains
nothing. Each forms an area of one, which the city view already collapses into
the "other areas" group.

| City | Place | Current | Type | Note |
|---|---|---|---|---|
| Prague | Lokál | `various` | food | A chain with several branches. `various` is accurate. |
| Riga | Traditional pirts ritual | `forest edge` | sight | Descriptive, and better than a blank. |

---

## Block D: Madrid, one row, not a rename

`Malasaña` and `Lavapiés` are genuinely different barrios, not two names for
one area: Lavapiés sits south of Sol, Malasaña north of Gran Vía
(<https://www.uniplaces.com/es/d/madrid/guides/thecity>). No rename fixes this.

The problem is a single row, **`Plaza Dos de Mayo / C. Argumosa`**, recorded as
`Malasaña/Lavapiés`. It is one saved entry covering two different bar streets:
Plaza del Dos de Mayo is the centre of Malasaña
(<https://en.wikipedia.org/wiki/Plaza_del_Dos_de_Mayo>) and Calle Argumosa is
the terrace street of Lavapiés
(<https://www.timeout.com/madrid/things-to-do/the-best-of-the-barrios-lavapies>).

Two options, both yours to pick since it is your own note:

1. **Split into two rows.** Duplicate the row in Part 8, keep
   `Plaza Dos de Mayo` in `Malasaña` and `C. Argumosa` in `Lavapiés`. This
   raises the place count from 406 to 407, so `meta.places` and the hero figure
   move. Nothing breaks, but the number in the handoff stops being 406.
2. **Pick one.** Lavapiés already has 4 places and Malasaña 1, so filing it
   under `Lavapiés` gives Lavapiés 5 and leaves the total at 406.

Option 2 is the smaller change. Option 1 is the truer one.
