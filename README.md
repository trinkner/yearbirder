<table><tr>
<td><img src="icons/Yearbird_Icon_1024.png" alt="Yearbird" height="120"></td>
<td><img src="icons/Yearbird_Screenshot.jpg" alt="Yearbird screenshot" height="120"></td>
</tr></table>

# Yearbird

A desktop application for exploring and analysing your personal [eBird](https://ebird.org) data and your personal photos of birds.

Yearbird lets you filter, browse, and visualise your personal eBird sightings in ways the eBird website does not — across every location, species, date, and season in your personal history. If you are a bird photogrpaher, Yearbird also lets you sort, filter and view your photos in the same way.

---

## Features

- **Species, Locations, and Checklists lists** — sortable, filterable tables of your sightings
- **Families window** — browse your sightings grouped by taxonomic family
- **Date Totals** — species counts by year, month, and individual date
- **Location Totals** — species counts by region, country, state, county, and named location
- **Big Report** — comprehensive multi-tab report combining species, dates, locations, and checklists
- **Compare Lists** — compare any two species lists side by side
- **Interactive Map** — all your sighting locations plotted on a zoomable map
- **Choropleth Maps** — US states, US counties, Canada provinces, India states, Great Britain counties, and world countries shaded by species count
- **Photos** — associate your JPEG bird photos with your sightings; browse, filter, and rate them by camera, lens, aperture, shutter speed, focal length, and ISO
- **Individual Species window** — full sighting history, location and year breakdowns, monthly patterns, and photo thumbnails for any species
- **Print and PDF export** — export any window to the printer or a PDF file
- **Powerful filter panel** — filter everything simultaneously by region, country, state, county, location, taxonomic order, family, species, date range, and seasonal range

---

## Download

A pre-built, signed, and notarized macOS app is available on the [Releases page](https://github.com/trinkner/yearbird/releases/latest).

Download `Yearbird.dmg`, open it, and drag Yearbird to your Applications folder.

---

## Requirements

- Python 3.10 or later
- [PySide6](https://pypi.org/project/PySide6/) — Qt 6 bindings (LGPL)
- [folium](https://pypi.org/project/folium/)
- [natsort](https://pypi.org/project/natsort/)
- [piexif](https://pypi.org/project/piexif/)

Install all dependencies with:

```
pip install pyside6 folium natsort piexif
```

---

## Running Yearbird

```
python3 yearbird.py
```

---

## Getting Your eBird Data

1. Go to [https://ebird.org/downloadMyData](https://ebird.org/downloadMyData)
2. Click **Request My Observations**
3. eBird will email you a link to download a `.csv` file containing your complete sightings history
4. In Yearbird, click **File → Open** and select that file

---

## Building a Standalone App (macOS)

Yearbird uses [PyInstaller](https://pyinstaller.org) to create a distributable `.app` bundle. From the project root directory:

```
pyinstaller Yearbird.spec
```

The finished app will be in `dist/Yearbird.app`.

---

## License

Yearbird is free, open-source software licensed under the [GNU General Public License v3](https://www.gnu.org/licenses/gpl-3.0.html).

Created by Richard Trinkner.
