<table><tr>
<td><img src="icons/Yearbirder_Icon_1024.png" alt="Yearbirder" height="120"></td>
<td><img src="src/readme_photos/demo_Lists.png" alt="Lists" height="120"></td>
<td><img src="src/readme_photos/demo_Reports1.png" alt="Reports" height="120"></td>
<td><img src="src/readme_photos/demo_Graphs1.png" alt="Graphs" height="120"></td>
<td><img src="src/readme_photos/demo_Maps1.png" alt="Maps" height="120"></td>
<td><img src="src/readme_photos/demo_Photos1.png" alt="Photos" height="120"></td>
</tr></table>

# Yearbirder

A desktop application for exploring and analysing your personal [eBird](https://ebird.org) data and your personal photos of birds.

Yearbirder lets you filter, browse, and visualise your personal eBird sightings in ways the eBird website does not — across every location, species, date, and season in your personal history. If you are a bird photogrpaher, Yearbirder also lets you sort, filter and view your photos in the same way.

---

## Features

- **Species, Locations, and Checklists lists** — sortable, filterable tables of your sightings
- **Individual Species window** — full sighting history, location and year breakdowns, monthly patterns, and photo thumbnails for any species
- **Location window** — complete sighting history for a single location, with species list, yearly and monthly breakdowns, and a map showing the site
- **Date Totals** — species counts by year, month, and individual date
- **Location Totals** — species counts by region, country, state, county, and named location
- **Powerful filter panel** — filter everything simultaneously by region, country, state, county, location, taxonomic order, family, species, date range, and seasonal range; the Date Options picker includes a **Select Year** mode that reveals a second dropdown listing every year in your data, so you can filter to any specific calendar year in one step
- **Big Report** — comprehensive multi-tab report combining species, dates, locations, and checklists
- **Compare Lists** — compare any two species lists side by side
- **Graphs** — fourteen chart types:
  - *Total Species Bar Graph* — species count per year
  - *Cumulative Species Curve* — cumulative species seen over time
  - *Species Heatmap* — species count by month and year
  - *Species Accumulation* — new species added each year vs. repeats
  - *Top Locations* — top 20 locations by species count
  - *Checklist Scatter* — duration vs. species count per checklist, coloured by season
  - *Locations by Species & Checklists* — locations plotted by species count vs. checklist count
  - *Species by Locations & Count* — species plotted by distinct location count vs. individual count
  - *Phenology Chart* — sighting dates by day-of-year across years
  - *First of Year Chart* — first sighting of each species per year, plotted by month
  - *Last of Year Chart* — last sighting of each species per year, plotted by month
  - *Pie Chart by Species* — species count by taxonomic family or order
  - *Pie Chart by Individual Tallies* — individual bird count by taxonomic family or order
  - *Locations by Checklists* — checklist count by location as a pie chart
  - *YTD Reports* — horizontal bar charts comparing year-to-date species, locations, checklists, and photographs across all years in your data
- **Maps** — eight interactive map types:
  - *Locations Map* — all your sighting locations plotted on a zoomable map
  - *Animated Lifer Map* — watch your life list build up chronologically, dot by dot
  - *Effort Map by Time* — bubble map sized by cumulative birding time per location
  - *Effort Map by Checklists* — bubble map sized by checklist count per location
  - *Species Total Map* — bubble map sized by species total per location
  - *Individuals Total Map* — bubble map sized by individual bird count per location
  - *Choropleth by Species* — US states, US counties, Canada, India, Great Britain, and world countries shaded by species count
  - *Choropleth by Checklists* — same regions shaded by checklist count
- **Photos** — associate your JPEG bird photos with your sightings; browse, filter, and rate them by camera, lens, aperture, shutter speed, focal length, and ISO; **File → Open Photo Settings File** defaults to the photo settings directory stored in Preferences
  - *Photos by Filter* — thumbnail gallery of every photo matching the current filter, sortable by taxonomy, date, rating, or name
  - *Species Gallery* — one best-rated photo per species, arranged in taxonomic order; click any tile to see all photos of that species
  - *Geolocated Photos* — geotagged photos plotted on a clustered interactive map; hover for a thumbnail preview, click to open the full enlargement
- **Print and PDF export** — export any window to the printer or a PDF file

---

## Download

A pre-built, signed, and notarized macOS app is available on the [Releases page](https://github.com/trinkner/yearbird/releases/latest).

Download `Yearbirder.dmg`, open it, and drag Yearbirder to your Applications folder.

---

## Requirements

- Python 3.10 or later (download from [python.org](https://www.python.org/downloads/))
- [PySide6](https://pypi.org/project/PySide6/) — Qt 6 bindings (LGPL)
- [folium](https://pypi.org/project/folium/)
- [matplotlib](https://pypi.org/project/matplotlib/)
- [numpy](https://pypi.org/project/numpy/)
- [natsort](https://pypi.org/project/natsort/)
- [piexif](https://pypi.org/project/piexif/)

After installing Python, install all other dependencies with:

```
pip install pyside6 folium matplotlib numpy natsort piexif
```

---

## Running Yearbirder

```
python3 yearbirder.py
```

---

## Getting Your eBird Data

1. Go to [https://ebird.org/downloadMyData](https://ebird.org/downloadMyData)
2. Click **Request My Observations**
3. eBird will email you a link to download a `.csv` file containing your complete sightings history
4. In Yearbirder, click **File → Open** and select that file — if you have set a default eBird data folder in Preferences, the dialog will open there automatically

---

## Building a Standalone App (macOS)

Yearbirder uses [PyInstaller](https://pyinstaller.org) to create a distributable `.app` bundle. From the project root directory:

```
pyinstaller Yearbirder.spec
```

The finished app will be in `dist/Yearbirder.app`.

---

## License

Yearbirder is free, open-source software licensed under the [GNU General Public License v3](https://www.gnu.org/licenses/gpl-3.0.html).

Created by Richard Trinkner.
