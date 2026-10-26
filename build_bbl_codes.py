#! /usr/bin/env python
"""Build src/eBird_BBLCodes.csv — IBP banding codes keyed to eBird's taxonomy.

This is a BUILD-TIME script, not part of the app.  Run it by hand when IBP
publishes a new alpha code list (each year, after the AOS supplement) and again
whenever the bundled eBird taxonomy file changes.  It needs one package the app
itself does not (install it into a throwaway venv, not Yearbirder's):

    python3 -m venv /tmp/ybbuild && /tmp/ybbuild/bin/pip install pdfplumber
    /tmp/ybbuild/bin/python build_bbl_codes.py

Source is the IBP list, published only as a PDF:
    https://birdpop.org/docs/misc/Alpha_codes_tax.pdf
Each line reads "[+ ]English Name CODE[*] Scientific name SIXLTR[*]"; "+" marks
a non-species taxon and "*" a code that is not first-order.

IBP follows the AOS checklist and eBird follows Clements, so the two disagree on
genera (Dryobates vs Leuconotopicus), spellings, and splits eBird has made that
AOS has not.  The app looks codes up by eBird scientific name, so every IBP row
is resolved to eBird's own names here:

  1. exact scientific name;
  2. exact common name (catches genus changes and IBP misspellings);
  3. slash taxa with their halves in either order.

When step 1 lands on an eBird species with a DIFFERENT common name, eBird has
often split IBP's species and kept the old scientific name for one daughter
(Yellow Warbler -> Mangrove Yellow Warbler, Setophaga petechia).  The code then
also goes to every same-genus eBird species whose name ends with IBP's name
(Northern Yellow Warbler), so each daughter carries the parent's code until IBP
assigns its own.

Output is Code,CommonName,ScientificName with eBird's names, one row per eBird
taxon; a species row wins over a "+" row for the same taxon.  Rows that resolve
to nothing (subspecies groups, morphs, "Unidentified X") are listed on stdout.
"""

import csv
import glob
import os
import re
import sys
import urllib.request

HERE       = os.path.dirname(os.path.abspath(__file__))
SRC_DIR    = os.path.join(HERE, "src")
OUT_PATH   = os.path.join(SRC_DIR, "eBird_BBLCodes.csv")
CACHE_DIR  = os.path.join(HERE, "build", "bbl-codes-cache")
PDF_URL    = "https://birdpop.org/docs/misc/Alpha_codes_tax.pdf"
PDF_PATH   = os.path.join(CACHE_DIR, "Alpha_codes_tax.pdf")

# "Ou" carries a two-letter code, so the code is 2-4 letters.
LINE_RE = re.compile(r'^(\+ )?(.+?) ([A-Z]{2,4})\*? (.+?) ([A-Z]{6})\*?$')


def fetch_pdf():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if "--refresh" in sys.argv or not os.path.isfile(PDF_PATH):
        print("Downloading", PDF_URL)
        urllib.request.urlretrieve(PDF_URL, PDF_PATH)
    return PDF_PATH


def read_ibp(pdfPath):
    import pdfplumber

    rows = []
    title = ""
    with pdfplumber.open(pdfPath) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if not title and "AOS Supplement" in line:
                    title = line.strip()
                m = LINE_RE.match(line.strip())
                if m:
                    rows.append({"nonSpecies": bool(m[1]), "name": m[2].strip(),
                                 "code": m[3], "sci": m[4].strip()})
    return rows, title


def read_taxonomy():
    matches = glob.glob(os.path.join(SRC_DIR, "eBird_Taxonomy*.csv"))
    if not matches:
        sys.exit("No eBird_Taxonomy*.csv in src/")
    path = max(matches)
    # The eBird file starts with a UTF-8 BOM.
    with open(path, encoding="utf-8-sig") as f:
        return path, list(csv.DictReader(f))


def norm_name(name):
    return name.lower().replace("-", " ")


def slash_key(sci):
    """'Vireo swainsoni/gilvus' and 'Vireo gilvus/swainsoni' share a key."""
    if "/" not in sci or " " not in sci:
        return None
    genus, rest = sci.split(" ", 1)
    return genus + " " + "/".join(sorted(rest.split("/")))


def main():
    ibpRows, title = read_ibp(fetch_pdf())
    taxPath, taxonomy = read_taxonomy()

    bySci   = {t["SCI_NAME"]: t for t in taxonomy}
    byName  = {t["PRIMARY_COM_NAME"]: t for t in taxonomy}
    bySlash = {slash_key(t["SCI_NAME"]): t for t in taxonomy
               if t["CATEGORY"] == "slash" and slash_key(t["SCI_NAME"])}
    species = [t for t in taxonomy if t["CATEGORY"] == "species"]

    # Species rows claim their taxa before "+" rows do, so Alaska Marbled
    # Murrelet (same scientific name) cannot overwrite MAMU.
    ibpRows.sort(key=lambda r: r["nonSpecies"])

    codeFor   = {}          # eBird SCI_NAME -> (code, eBird row)
    renamed   = []          # matched by scientific name, names differ
    daughters = []          # split daughters given the parent's code
    byCommon  = []          # matched only by common name
    unmatched = []

    def assign(t, code):
        if t["SCI_NAME"] not in codeFor:
            codeFor[t["SCI_NAME"]] = (code, t)

    for r in ibpRows:
        t = bySci.get(r["sci"])
        if t:
            assign(t, r["code"])
            if t["PRIMARY_COM_NAME"] != r["name"]:
                renamed.append((r, t))
                if t["CATEGORY"] == "species" and not r["nonSpecies"]:
                    genus = t["SCI_NAME"].split(" ")[0]
                    for s in species:
                        if (s is not t
                                and s["SCI_NAME"].split(" ")[0] == genus
                                and s["PRIMARY_COM_NAME"] != r["name"]
                                and norm_name(s["PRIMARY_COM_NAME"]).endswith(
                                    " " + norm_name(r["name"]))):
                            assign(s, r["code"])
                            daughters.append((r, s))
            continue
        t = byName.get(r["name"]) or bySlash.get(slash_key(r["sci"]))
        if t:
            assign(t, r["code"])
            byCommon.append((r, t))
            continue
        unmatched.append(r)

    order = {t["SCI_NAME"]: i for i, t in enumerate(taxonomy)}
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Code", "CommonName", "ScientificName"])
        for sci in sorted(codeFor, key=order.get):
            code, t = codeFor[sci]
            w.writerow([code, t["PRIMARY_COM_NAME"], sci])

    print(title)
    print("eBird taxonomy:", os.path.basename(taxPath))
    print(f"IBP rows: {len(ibpRows)}   written: {len(codeFor)}   "
          f"unmatched: {len(unmatched)}")

    print("\nMatched by common name or slash order (genus/spelling differs):")
    for r, t in byCommon:
        print(f"  {r['code']:5} {r['name']}: {r['sci']} -> {t['SCI_NAME']}")

    print("\nSplit daughters given the parent's code (review these):")
    for r, s in daughters:
        print(f"  {r['code']:5} {r['name']} -> {s['PRIMARY_COM_NAME']}")

    print("\nSpecies matched by scientific name under a different eBird name:")
    for r, t in renamed:
        if t["CATEGORY"] == "species" and not r["nonSpecies"]:
            print(f"  {r['code']:5} {r['name']} -> {t['PRIMARY_COM_NAME']}")

    print("\nUnmatched (no eBird taxon; expected for subspecies and morphs):")
    for r in unmatched:
        flag = "+" if r["nonSpecies"] else "SPECIES"
        print(f"  {flag:7} {r['code']:5} {r['name']} [{r['sci']}]")

    print("\nWrote", OUT_PATH)


if __name__ == "__main__":
    main()
