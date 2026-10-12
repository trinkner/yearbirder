# -*- coding: utf-8 -*-
"""Shared photo-metadata parsing for the Photo Statistics reports and charts.

Every value in the media catalog is a string written by the EXIF reader in
code_DataBase.AddPhoto: shutter speed as "1/N", focal length as "N mm",
aperture as a plain float, ISO as a plain int.  Those formats come from the
app's own writer, so they hold for every user's catalog — but any field can be
blank (no EXIF, scanned film, stripped exports), so each parse returns None
rather than raising and callers bucket None as "unknown".

Lives in its own module so code_PhotoStats (the tabular reports) and
code_Graphs (the distribution charts) read a photo the same way, without
either importing the other.
"""


def int_or_none(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def iso(photo):
    return int_or_none(photo.get("iso"))


def aperture(photo):
    try:
        return float(str(photo.get("aperture") or "").strip())
    except (TypeError, ValueError):
        return None


def focal(photo):
    """Focal length in mm from the stored "N mm" string."""
    raw = str(photo.get("focalLength") or "").strip()
    if not raw:
        return None
    return int_or_none(raw.split(" mm")[0])


def shutter_denom(photo):
    """Denominator N from the stored "1/N" shutter speed.

    Larger N is a faster shutter, so N orders the same way photographers talk
    about it.  N == 0 is returned as None: the EXIF writer computes
    floor(denominator/numerator), so every exposure longer than one second
    collapses to the string "1/0" — a real catalog value that is not a real
    shutter speed, counted under catalog health rather than charted.
    """
    raw = str(photo.get("shutterSpeed") or "").strip()
    if not raw.startswith("1/"):
        return None
    n = int_or_none(raw[2:])
    if n is None or n <= 0:
        return None
    return n


def is_long_exposure(photo):
    """True for the "1/0" values the EXIF writer produces above one second."""
    return str(photo.get("shutterSpeed") or "").strip() == "1/0"


def rating(photo):
    """Rating 1-5, or 0 when the photo is unrated.  0 means unrated, not bad."""
    r = int_or_none(photo.get("rating"))
    if r is None or r < 0 or r > 5:
        return 0
    return r


def hour(photo, sighting):
    """Hour of day (0-23) the photo was taken, or None.

    Prefers the photo's own EXIF timestamp.  Photos loaded from the catalog
    carry "exifDatetime" ("YYYY:MM:DD HH:MM:SS") but no separate time field —
    that only exists on a freshly ingested photo — so the sighting's checklist
    time is the fallback.
    """
    if not photo.get("exifDateInvalid"):
        stamp = str(photo.get("exifDatetime") or "")
        if len(stamp) >= 13 and stamp[11:13].isdigit():
            return int(stamp[11:13])
    t = str((photo.get("time") or sighting.get("time") or "")).strip()
    if len(t) >= 2 and t[:2].isdigit():
        h = int(t[:2])
        if 0 <= h <= 23:
            return h
    return None


def is_species(name):
    """False for hybrids, spuhs and slashes, matching code_Stats."""
    return " x " not in name and "sp." not in name and "/" not in name


def percentile(sorted_values, fraction):
    """Value at `fraction` through an already-sorted list (nearest-rank)."""
    if not sorted_values:
        return None
    idx = int(round(fraction * (len(sorted_values) - 1)))
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def median(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def fmt_shutter(denom):
    return f"1/{denom}" if denom else "—"
