#! /usr/bin/env python
"""Build src/europe-regions.json — regional outlines for European choropleths.

This is a BUILD-TIME script, not part of the app.  It is run by hand when the
region set changes; the app only ever reads its output.  It needs two packages
the app itself does not (install them into a throwaway venv, not Yearbirder's):

    python3 -m venv /tmp/ybbuild && /tmp/ybbuild/bin/pip install shapely topojson
    /tmp/ybbuild/bin/python build_europe_regions.py

Source data is Natural Earth 10m Admin-1 (public domain), the same source the
ca-provinces / in-states / gb-counties files came from.  Region codes come from
eBird's own subnational1 lists, fetched live so the output cannot drift from what
the app's sighting records actually contain.

Output matches the existing choropleth files exactly: a FeatureCollection whose
features carry a top-level "id" holding the eBird subnational1 code and a
properties.name holding eBird's own name for the region.
"""

import json
import os
import sys
import urllib.request

HERE      = os.path.dirname(os.path.abspath(__file__))
OUT_PATH  = os.path.join(HERE, "src", "europe-regions.json")
CACHE_DIR = os.path.join(HERE, "build", "europe-regions-cache")

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_10m_admin_1_states_provinces.geojson")

# Simplification tolerance in degrees, applied to a shared-arc topology so
# neighbouring regions cannot drift apart into slivers.  ~1.1 km.
SIMPLIFY_TOLERANCE = 0.01
COORD_PRECISION    = 4


# Countries whose eBird subnational1 regions map 1:1 onto a Natural Earth
# admin-1 feature's iso_3166_2.  Nothing to do but keep the features whose code
# eBird actually uses — a rule that also discards Natural Earth's extras
# (Caribbean Netherlands, Svalbard, Bouvet Island), which eBird files under
# separate countries.
SIMPLE_COUNTRIES = ["AT", "CH", "CZ", "DE", "GR", "NL", "NO", "PL", "PT", "RO", "SE"]

# Natural Earth codes that eBird spells differently, applied before the check
# above.  These are plain code-for-code swaps, not a change of level: Natural
# Earth files Attica as GR-A1 where eBird uses GR-I.  Several countries not yet
# supported need only entries here (Latvia's city codes, RU-CHI, KZ-ALM).
CODE_ALIASES = {
    "GR": {"GR-A1": "GR-I"},
    }

# Countries where Natural Earth carries a FINER division than eBird uses, and
# has to be dissolved upwards.  'key' is the Natural Earth attribute holding the
# coarser unit; its value is matched against eBird's region NAME, with 'alias'
# covering the spellings that differ and 'drop' removing units that eBird files
# under a different country entirely.
DISSOLVE_COUNTRIES = {
    "FR": {
        "key": "region",
        # eBird treats these as their own countries (GP, GF, MQ, YT, RE).
        "drop": {"Guadeloupe", "Guyane française", "Martinique", "Mayotte",
                 "Réunion"},
        "alias": {"Provence-Alpes-Côte-d'Azur": "FR-PAC"},
    },
    "IT": {
        "key": "region",
        "drop": set(),
        "alias": {"Apulia": "IT-75", "Sicily": "IT-82"},
    },
    "ES": {
        "key": "region",
        "drop": set(),
        # Natural Earth's iso_3166_2 for Spain holds PROVINCE codes, which are
        # the wrong level, so every Spanish id comes from name matching.
        "alias": {"Asturias": "ES-AS", "Canary Is.": "ES-CN",
                  "Foral de Navarra": "ES-NC", "Islas Baleares": "ES-IB",
                  "Madrid": "ES-MD", "Murcia": "ES-MC",
                  "Valenciana": "ES-VC"},
    },
}

# Natural Earth folds Jan Mayen into Nordland, but eBird files Jan Mayen under
# Svalbard & Jan Mayen (SJ) — a separate country, so a sighting there is never
# NO-18.  Left in, it also drags Norway's map extent 20 degrees west of the
# mainland.  Values are a minimum longitude; parts lying entirely west are cut.
DROP_PARTS_WEST_OF = {"NO-18": 0.0}


COUNTRIES = SIMPLE_COUNTRIES + list(DISSOLVE_COUNTRIES)


# ----------------------------------------------------------------------------
# source data


def ebird_api_key():
    """The key the app already stores, or EBIRD_API_KEY from the environment."""
    if os.environ.get("EBIRD_API_KEY"):
        return os.environ["EBIRD_API_KEY"].strip()

    if sys.platform == "darwin":
        prefs_dir = os.path.expanduser("~/Library/Application Support/Yearbirder")
    elif sys.platform == "win32":
        prefs_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                 "Yearbirder")
    else:
        prefs_dir = os.path.expanduser("~/.yearbirder")

    prefs_path = os.path.join(prefs_dir, "yearbirderPreferences.txt")
    if os.path.isfile(prefs_path):
        with open(prefs_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("ebirdApiKey="):
                    return line[len("ebirdApiKey="):].strip()
    return ""


def ebird_regions(country):
    """eBird's subnational1 list for one country, cached on disk after fetching."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"ebird-{country}.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    key = ebird_api_key()
    if not key:
        sys.exit("No eBird API key found.  Set one in Preferences, or export "
                 "EBIRD_API_KEY, so region codes can be fetched.")

    url = f"https://api.ebird.org/v2/ref/region/list/subnational1/{country}"
    req = urllib.request.Request(url, headers={"X-eBirdApiToken": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def natural_earth():
    """The Natural Earth admin-1 FeatureCollection, cached on disk (39 MB)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "ne_10m_admin_1_states_provinces.geojson")
    if not os.path.isfile(path):
        print("  downloading Natural Earth admin-1 (39 MB) ...")
        urllib.request.urlretrieve(NE_URL, path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ne_country(props):
    """Natural Earth's country for a feature.

    iso_a2 is '-99' on some features, so fall back to the iso_3166_2 prefix.
    Without this fallback whole countries silently vanish from the output.
    """
    cc = props.get("iso_a2")
    if cc and cc != "-99":
        return cc
    code = props.get("iso_3166_2") or ""
    return code.split("-")[0] if "-" in code else ""


# ----------------------------------------------------------------------------
# assembly


def build_features(ne, shapely_ops):
    """One feature per eBird region, id = eBird code, name = eBird's name."""
    from shapely.geometry import shape, mapping

    by_country = {}
    for feature in ne["features"]:
        by_country.setdefault(ne_country(feature["properties"]), []).append(feature)

    features, problems = [], []

    for country in sorted(COUNTRIES):
        regions   = ebird_regions(country)
        by_code   = {r["code"]: r["name"] for r in regions}
        by_name   = {r["name"]: r["code"] for r in regions}
        candidates = by_country.get(country, [])
        made       = {}

        if country in DISSOLVE_COUNTRIES:
            spec    = DISSOLVE_COUNTRIES[country]
            groups  = {}
            for feature in candidates:
                value = feature["properties"].get(spec["key"])
                if not value or value in spec["drop"]:
                    continue
                code = spec["alias"].get(value) or by_name.get(value)
                if not code:
                    problems.append(f"{country}: no eBird code for "
                                    f"{spec['key']}={value!r}")
                    continue
                groups.setdefault(code, []).append(shape(feature["geometry"]))

            for code, geoms in groups.items():
                # A plain MultiPolygon merge would leave Leaflet stroking every
                # internal department/province border inside the regional fill,
                # so the parts have to be genuinely unioned.
                made[code] = mapping(shapely_ops.unary_union(geoms))
        else:
            aliases = CODE_ALIASES.get(country, {})
            for feature in candidates:
                code = feature["properties"].get("iso_3166_2")
                code = aliases.get(code, code)
                if code not in by_code:
                    continue          # Natural Earth extra eBird files elsewhere
                if code in made:
                    problems.append(f"{country}: {code} appears more than once")
                    continue
                made[code] = feature["geometry"]

        for code in sorted(made):
            geom = shape(made[code])
            if code in DROP_PARTS_WEST_OF:
                geom = drop_far_parts(code, geom, DROP_PARTS_WEST_OF[code])
            features.append({
                "type": "Feature",
                "id": code,
                "properties": {"name": by_code[code]},
                "geometry": mapping(geom),
            })

        missing = sorted(set(by_code) - set(made))
        if missing:
            problems.append(f"{country}: {len(missing)} eBird region(s) with no "
                            f"outline: {', '.join(missing)}")
        print(f"  {country}: {len(made):3} of {len(by_code)} eBird regions")

    return features, problems


def polygonal(geom):
    """Drop anything that is not a polygon from a possibly mixed geometry.

    make_valid can hand back lines or points alongside the polygons when it
    repairs a self-intersection; only the polygonal parts belong in a choropleth.
    """
    from shapely.geometry import MultiPolygon

    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    if not parts:
        return geom
    merged = []
    for part in parts:
        merged.extend(part.geoms if part.geom_type == "MultiPolygon" else [part])
    return MultiPolygon(merged) if len(merged) > 1 else merged[0]


def repair(code, geom, problems):
    """Make a geometry valid, reporting anything that cannot be repaired.

    Simplification can introduce self-intersections even from valid input, and an
    invalid ring is not something to hand to Leaflet.
    """
    from shapely.validation import make_valid

    if geom.is_valid:
        return geom
    fixed = polygonal(make_valid(geom))
    if not fixed.is_valid or fixed.is_empty:
        problems.append(f"{code}: geometry still invalid after repair")
    return fixed


def drop_far_parts(code, geom, min_lon):
    """Remove polygon parts lying entirely west of min_lon."""
    from shapely.geometry import MultiPolygon

    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    kept = [p for p in parts if p.bounds[2] >= min_lon]
    if not kept:
        return geom
    if len(kept) != len(parts):
        print(f"    {code}: dropped {len(parts) - len(kept)} outlying part(s) "
              f"west of {min_lon}")
    return MultiPolygon(kept) if len(kept) > 1 else kept[0]


def simplify(features):
    """Simplify on a SHARED-ARC topology.

    Simplifying each region independently would pull neighbours apart along the
    borders they share, leaving visible slivers.  Building one topology first
    means a shared border is simplified once and stays shared.
    """
    import topojson

    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature",
                        "properties": {"code": f["id"], "name": f["properties"]["name"]},
                        "geometry": f["geometry"]} for f in features]}

    topo = topojson.Topology(fc, prequantize=False)
    simplified = json.loads(topo.toposimplify(SIMPLIFY_TOLERANCE).to_geojson())

    from shapely.geometry import shape, mapping

    out, problems = [], []
    for feature in simplified["features"]:
        props = feature["properties"]
        geom  = repair(props["code"], shape(feature["geometry"]), problems)
        out.append({"type": "Feature",
                    "id": props["code"],
                    "properties": {"name": props["name"]},
                    "geometry": round_coords(mapping(geom))})
    return out, problems


def round_coords(node):
    # shapely's mapping() yields tuples rather than lists, so both must be walked
    # or the coordinates slip through unrounded.
    if isinstance(node, (list, tuple)):
        return [round_coords(n) for n in node]
    if isinstance(node, float):
        return round(node, COORD_PRECISION)
    if isinstance(node, dict):
        return {k: round_coords(v) for k, v in node.items()}
    return node


def vertex_count(features):
    def count(node):
        if isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (int, float)):
                return 1
            return sum(count(n) for n in node)
        return 0
    return sum(count(f["geometry"]["coordinates"]) for f in features)


def main():
    from shapely import ops as shapely_ops
    from shapely.geometry import shape

    print("Building europe-regions.json")
    ne = natural_earth()
    print(f"  Natural Earth: {len(ne['features'])} admin-1 features worldwide")

    features, problems = build_features(ne, shapely_ops)
    before = vertex_count(features)

    print(f"  simplifying {len(features)} regions on a shared topology "
          f"({SIMPLIFY_TOLERANCE}° ≈ {SIMPLIFY_TOLERANCE * 111:.1f} km) ...")
    features, simplify_problems = simplify(features)
    problems.extend(simplify_problems)

    # Every region the app can ask for must exist exactly once, with geometry.
    seen = {}
    for f in features:
        seen[f["id"]] = seen.get(f["id"], 0) + 1
        if not f["geometry"] or not f["geometry"].get("coordinates"):
            problems.append(f"{f['id']}: empty geometry after simplification")
        elif not shape(f["geometry"]).is_valid:
            problems.append(f"{f['id']}: invalid geometry in the output")
    for code, n in sorted(seen.items()):
        if n != 1:
            problems.append(f"{code}: {n} features in the output, expected 1")

    if problems:
        print("\nFAILED — output not written:")
        for p in problems:
            print(f"  - {p}")
        return 1

    fc = {"type": "FeatureCollection", "features": features}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(OUT_PATH)
    after = vertex_count(features)
    print(f"\n  vertices {before:,} -> {after:,} ({100 * after / before:.0f}%)")
    print(f"  wrote {OUT_PATH}")
    print(f"  {len(features)} regions, {size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
