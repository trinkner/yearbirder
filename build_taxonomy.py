#! /usr/bin/env python
"""Build src/eBird_Taxonomy_<year>.csv — the bundled eBird taxonomy.

This is a BUILD-TIME script, not part of the app.  Run it by hand once a year,
after eBird publishes its taxonomy update (usually late October), then rerun
build_bbl_codes.py, which keys banding codes to this file's names.  It needs
only the standard library:

    python3 build_taxonomy.py

Source is the eBird API taxonomy, which needs no key:
    https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=csv

The API's columns differ from the eBird/Clements download the app was written
against, so they are renamed here, and FAMILY is rebuilt in that file's
"Scientific (Common)" form, e.g. "Struthionidae (Ostriches)".  The output
keeps the UTF-8 BOM of the Cornell download (the app opens it with
utf-8-sig) and is named for the API's latest authority version.

After building, update the file name in both .spec files, remove the old
taxonomy file from src/ (the app loads the newest eBird_Taxonomy*.csv), and
check that the names match a fresh eBird data export.
"""

import csv
import glob
import io
import json
import os
import sys
import urllib.request

HERE         = os.path.dirname(os.path.abspath(__file__))
SRC_DIR      = os.path.join(HERE, "src")
VERSIONS_URL = "https://api.ebird.org/v2/ref/taxonomy/versions"
TAXONOMY_URL = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=csv"

OUT_COLUMNS = ["TAXON_ORDER", "CATEGORY", "SPECIES_CODE", "PRIMARY_COM_NAME",
               "SCI_NAME", "ORDER", "FAMILY", "REPORT_AS"]


def fetch(url):
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8-sig")


def main():
    versions = json.loads(fetch(VERSIONS_URL))
    latest = [v for v in versions if v.get("latest")]
    if not latest:
        sys.exit("The API marks no taxonomy version as latest.")
    year = str(int(latest[0]["authorityVer"]))
    outPath = os.path.join(SRC_DIR, "eBird_Taxonomy_" + year + ".csv")

    rows = list(csv.DictReader(io.StringIO(fetch(TAXONOMY_URL))))
    out = []
    for r in rows:
        taxonOrder = r["TAXON_ORDER"]
        # The API writes "2.0"; the Cornell file writes "2".
        if taxonOrder.endswith(".0"):
            taxonOrder = taxonOrder[:-2]
        family = ""
        if r["FAMILY_SCI_NAME"]:
            family = r["FAMILY_SCI_NAME"] + " (" + r["FAMILY_COM_NAME"] + ")"
        out.append([taxonOrder, r["CATEGORY"], r["SPECIES_CODE"], r["COMMON_NAME"],
                    r["SCIENTIFIC_NAME"], r["ORDER"], family, r["REPORT_AS"]])

    with open(outPath, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(OUT_COLUMNS)
        w.writerows(out)

    counts = {}
    for r in rows:
        counts[r["CATEGORY"]] = counts.get(r["CATEGORY"], 0) + 1
    print("eBird taxonomy", year)
    print(f"Rows: {len(out)}   " + ", ".join(f"{k} {v}" for k, v in
                                                sorted(counts.items(), key=lambda kv: -kv[1])))
    others = [p for p in glob.glob(os.path.join(SRC_DIR, "eBird_Taxonomy*.csv")) if p != outPath]
    if others:
        print("Remove the old file(s):", ", ".join(os.path.basename(p) for p in others))
    print("Wrote", outPath)


if __name__ == "__main__":
    main()
