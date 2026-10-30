#! /usr/bin/env python
"""Build src/RedList_data.csv — IUCN Red List categories keyed to eBird's taxonomy.

This is a BUILD-TIME script, not part of the app.  Run it by hand when BirdLife
publishes a new checklist (each year, with the IUCN Red List update) and again
whenever the bundled eBird taxonomy file changes.  It needs one package the app
itself does not (install it into a throwaway venv, not Yearbirder's):

    python3 -m venv /tmp/ybbuild && /tmp/ybbuild/bin/pip install openpyxl
    /tmp/ybbuild/bin/python build_redlist_data.py species-filter-results.zip \\
        AviList-v2026-...-extended-version.xlsx

Sources:
  * BirdLife DataZone species download (https://datazone.birdlife.org, Species
    search with no filters, Download): the .zip or the .csv inside it.  BirdLife
    is the IUCN Red List authority for birds; its SIS IDs are IUCN's taxon ids,
    so https://www.iucnredlist.org/species/<SISID> opens the Red List page.
    BirdLife granted permission on 2026-10-30 to bundle TWO fields from it,
    scientific name and Red List category, plus the SIS ID for the link.  Write
    nothing else from it, and never commit the download itself: the repo is
    public.
  * AviList EXTENDED checklist (.xlsx, https://www.avilist.org), used only as a
    crosswalk: it pairs each Cornell Lab species code with a BirdLife DataZone
    URL ending in the SIS ID.  Nothing else from AviList reaches the output.

Each eBird species is matched to a BirdLife species by:

  1. AviList's SIS ID for its species code (catches the ~500 species whose
     scientific names differ, Anser cygnoides vs BirdLife's Anser cygnoid);
  2. exact scientific name.

Step 2 fills species AviList leaves blank because its species concept differs
from BirdLife's (American Robin, Red Crossbill).  BirdLife's category then
describes BirdLife's version of the species, so review the non-LC ones the
script prints.  An eBird species neither step matches (mostly splits BirdLife
does not recognize) is left out, and the app shows it as Not Available.

Output is eBirdCode,Status,SISID, one row per matched eBird species.  Status is
the Red List category (LC, NT, VU, EN, CR, EW, EX, DD), with BirdLife's PE and
PEW flags written "CR (PE)" and "CR (PEW)".

After a rebuild, update the BirdLife year in the About credits (code_Web.py)
and the README if the script prints a new one.
"""

import csv
import glob
import io
import os
import re
import sys
import zipfile

HERE     = os.path.dirname(os.path.abspath(__file__))
SRC_DIR  = os.path.join(HERE, "src")
OUT_PATH = os.path.join(SRC_DIR, "RedList_data.csv")

BIRDLIFE_COLUMNS = ["SIS ID", "Scientific name", "RL Category", "PE", "PEW"]
AVILIST_COLUMNS  = {"rank": "RANK",
                    "code": "SPECIES CODE CORNELL LAB",
                    "datazone": "BIRDLIFE DATAZONE URL"}


def readBirdLife(path):
    """(rows, citation year) from the DataZone .zip or its .csv."""
    year = ""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            csvName = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            text = z.read(csvName).decode("utf-8-sig")
            if "readme.txt" in z.namelist():
                m = re.search(r"BirdLife International \((\d{4})\)",
                              z.read("readme.txt").decode("utf-8-sig"))
                year = m.group(1) if m else ""
    else:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    rows = list(csv.DictReader(io.StringIO(text)))
    missing = [c for c in BIRDLIFE_COLUMNS if rows and c not in rows[0]]
    if not rows or missing:
        sys.exit("Not a BirdLife species download; missing columns: " + ", ".join(missing))
    return rows, year


def readAviListCrosswalk(path):
    """Cornell Lab species code -> BirdLife SIS ID, from the AviList extended file."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    rows = wb[wb.sheetnames[0]].iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows)]
    missing = [c for c in AVILIST_COLUMNS.values() if c not in header]
    if missing:
        sys.exit("Not an AviList extended file; missing columns: " + ", ".join(missing))
    idx = {k: header.index(c) for k, c in AVILIST_COLUMNS.items()}

    def cell(row, key):
        i = idx[key]
        return str(row[i]).strip() if i < len(row) and row[i] is not None else ""

    crosswalk = {}
    for row in rows:
        if cell(row, "rank") != "species":
            continue
        idMatch = re.search(r"/(\d+)/?$", cell(row, "datazone"))
        code = cell(row, "code")
        if code and idMatch:
            crosswalk.setdefault(code, idMatch.group(1))
    return crosswalk


def statusOf(row):
    status = row["RL Category"].strip()
    if row["PEW"] == "True":
        return status + " (PEW)"
    if row["PE"] == "True":
        return status + " (PE)"
    return status


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: build_redlist_data.py <BirdLife .zip or .csv> <AviList extended .xlsx>")

    birdLifeRows, year = readBirdLife(sys.argv[1])
    bySIS = {r["SIS ID"].strip(): r for r in birdLifeRows}
    bySciName = {r["Scientific name"].strip(): r for r in birdLifeRows}
    crosswalk = readAviListCrosswalk(sys.argv[2])

    # The app picks the newest taxonomy file by name, so match against the same one.
    taxonomyFile = max(glob.glob(os.path.join(SRC_DIR, "eBird_Taxonomy*.csv")))
    with open(taxonomyFile, encoding="utf-8-sig") as f:
        species = [r for r in csv.DictReader(f) if r["CATEGORY"] == "species"]

    out = []
    viaCrosswalk = viaSciName = 0
    review = []
    unmatched = []
    for t in species:
        code, sciName = t["SPECIES_CODE"], t["SCI_NAME"]
        row = bySIS.get(crosswalk.get(code, ""))
        if row:
            viaCrosswalk += 1
        else:
            row = bySciName.get(sciName)
            if not row:
                unmatched.append(t)
                continue
            viaSciName += 1
            if row["RL Category"] != "LC":
                review.append((t["PRIMARY_COM_NAME"], sciName, statusOf(row)))
        out.append((code, statusOf(row), row["SIS ID"].strip()))

    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["eBirdCode", "Status", "SISID"])
        w.writerows(out)

    statuses = {}
    for _, s, _ in out:
        statuses[s] = statuses.get(s, 0) + 1
    print("Taxonomy:", os.path.basename(taxonomyFile))
    print(f"eBird species: {len(species)}   matched via AviList SIS ID: {viaCrosswalk}"
          f"   via scientific name: {viaSciName}   Not Available: {len(unmatched)}")
    print("Status counts:", ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())))
    print(f"\nScientific-name matches that are not LC ({len(review)}); BirdLife's"
          " species concept may differ from eBird's:")
    for name, sci, status in sorted(review, key=lambda r: r[2]):
        print(f"  {status:9} {name} ({sci})")
    if year:
        print(f"\nBirdLife citation year: {year}; check the About credits and README.")
    print("Wrote", OUT_PATH)


if __name__ == "__main__":
    main()
