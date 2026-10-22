# -*- coding: utf-8 -*-
"""Recordings reports — Recordings > Birding / Technical Statistics.

Two report modes, each its own menu entry, and each the recordings
counterpart of a photo report in code_PhotoStats:

    "overview"  Recordings Overview (Birding Statistics) — totals, recording
                days, rating distribution; mirrors Photos Overview
    "gear"      Recording Gear (Technical Statistics) — recorders,
                microphones, formats, lengths; mirrors Camera Gear

The window subclasses PhotoStats, so it shares the report styling, the
fit-to-content sizing, Save as PDF and media-change refresh.

Recorders play the part of camera bodies and microphones the part of lenses.
What has no audio equivalent is left out rather than forced: there is no
exposure envelope to measure, so Typical Settings becomes the recording
format and length, and Practical Limits gives way to a table of formats.

Two differences from photos shape the counting:

* A recording assigned to several species appears once under each of those
  sightings, so every count here is of distinct FILES, while species are
  counted across all the sightings a file belongs to.
* Microphones are never stored in the file; a user assigns one through a rig
  in Add or Manage Recordings.  So a blank microphone means "not assigned",
  not "none used", and the table says so.
"""

import code_MediaRefresh
import code_PhotoMetrics as pm
from code_PhotoStats import (PhotoStats, _elide, _fmt_date,
                             _MIN_BAND_N, _TABLE_CAP)

from PySide6.QtGui import QIcon, QPixmap


_MODE_TITLES = {
    "overview": "Recordings Overview",
    "gear":     "Recording Gear",
}


def _seconds(duration):
    """Catalog "m:ss" as whole seconds, or None."""
    parts = str(duration or "").split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def _fmt_seconds(sec):
    """Seconds as "m:ss", or "h:mm:ss" from an hour up."""
    if sec is None:
        return "—"
    h, rest = divmod(int(sec), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _rate_label(rate):
    """Catalog "48000 Hz" as "48 kHz" (or "44.1 kHz")."""
    t = str(rate or "").strip()
    if t.lower().endswith("hz") and not t.lower().endswith("khz"):
        try:
            khz = float(t[:-2].strip()) / 1000.0
            return f"{khz:g} kHz"
        except ValueError:
            pass
    return t


class RecordingStats(PhotoStats):

    def __init__(self):
        super().__init__()
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_microphone_white.png"),
                       QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)
        self.mode = "gear"

    def _designWidth(self):
        return 760 if self.mode == "overview" else 920

    @code_MediaRefresh.media_report(is_content=True)   # always about media
    def FillRecordingStats(self, filter, mode="gear"):
        self.filter = filter
        self.mode = mode if mode in _MODE_TITLES else "gear"

        recordings = self._collectRecordings(filter)
        if not recordings:
            return False

        if self.mode == "overview":
            self._stats = self._computeRecordingOverview(recordings)
        else:
            self._stats = self._computeRecordingGear(recordings)
        self._render(filter.buildWindowTitle(_MODE_TITLES[self.mode],
                                             self.mdiParent.db))
        return True

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _collectRecordings(self, filter):
        """{fileName: (audio dict, [sightings])} for every matching recording.

        GetSightingsWithRecordings keeps a sighting when ANY of its recordings
        matches the Media Filter, so each file gets the individual test too,
        as the photo reports do.
        """
        db = self.mdiParent.db
        files = {}
        for s in db.GetSightingsWithRecordings(filter):
            for a in s.get("audio", []):
                if not db.TestIndividualRecording(a, filter):
                    continue
                entry = files.setdefault(a["fileName"], (a, []))
                entry[1].append(s)
        return files

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _computeRecordingOverview(self, recordings):
        """Totals and rhythm, counted per distinct file (see module notes)."""
        species, families, locations, checklists = set(), set(), set(), set()
        files_by_date = {}
        secs = []
        for fn, (a, sightings) in recordings.items():
            for s in sightings:
                if pm.is_species(s["commonName"]):
                    species.add(s["commonName"])
                if s.get("family"):
                    families.add(s["family"])
                locations.add(s["location"])
                checklists.add(s["checklistID"])
                files_by_date.setdefault(s["date"], set()).add(fn)
            sec = _seconds(a.get("duration"))
            if sec is not None:
                secs.append(sec)

        by_date = {d: len(fns) for d, fns in files_by_date.items()}
        busiest_date, busiest_n = ("", 0)
        for d, n in by_date.items():
            if n > busiest_n or (n == busiest_n and d > busiest_date):
                busiest_date, busiest_n = d, n

        total = len(recordings)
        dates = sorted(by_date)
        # PhotoStats._ratingSpread reads (sighting, item) pairs and only the
        # item's rating, so one pair per file gives a per-file distribution.
        pairs = [(sightings[0], a) for a, sightings in recordings.values()]
        return {
            "recording_n":  total,
            "species_n":    len(species),
            "families_n":   len(families),
            "locations_n":  len(locations),
            "checklists_n": len(checklists),
            "days_n":       len(by_date),
            "total_sec":    sum(secs) if secs else None,
            "first_date":   dates[0] if dates else "",
            "last_date":    dates[-1] if dates else "",
            "per_day":      (total / len(by_date)) if by_date else 0.0,
            "busiest_date": busiest_date,
            "busiest_n":    busiest_n,
            "rating":       self._ratingSpread(pairs),
        }

    @staticmethod
    def _gearRowsFor(recordings, key, blank_label):
        """Per-recorder or per-microphone rows: recordings, share, species,
        date span."""
        agg = {}
        for a, sightings in recordings.values():
            label = str(a.get(key) or "").strip()
            rec = agg.setdefault(label, {"n": 0, "species": set(),
                                         "first": "", "last": ""})
            rec["n"] += 1
            for s in sightings:
                if pm.is_species(s["commonName"]):
                    rec["species"].add(s["commonName"])
                d = s["date"]
                if not rec["first"] or d < rec["first"]:
                    rec["first"] = d
                if not rec["last"] or d > rec["last"]:
                    rec["last"] = d
        total = len(recordings)
        rows = [{
            "label":   label or blank_label,
            "n":       rec["n"],
            "pct":     (100.0 * rec["n"] / total) if total else 0.0,
            "species": len(rec["species"]),
            "first":   rec["first"],
            "last":    rec["last"],
            "blank":   not label,
        } for label, rec in agg.items()]
        rows.sort(key=lambda r: (-r["n"], r["label"]))
        return rows

    def _computeRecordingGear(self, recordings):
        recorders = self._gearRowsFor(recordings, "device", "(none recorded)")
        mics = self._gearRowsFor(recordings, "microphone", "(not assigned)")
        unassigned_mic_n = sum(r["n"] for r in mics if r["blank"])

        # Rigs earn a table only when a recorder's recordings are genuinely
        # split across microphones — the same rule, and for the same reason,
        # as Camera Gear's body-and-lens table.  Recordings with no microphone
        # assigned do not count as a microphone here: "not assigned yet" is
        # not a second mic.
        rig_agg = {}
        per_recorder = {}
        for a, _sightings in recordings.values():
            dev = str(a.get("device") or "").strip()
            mic = str(a.get("microphone") or "").strip()
            rig_agg[(dev, mic)] = rig_agg.get((dev, mic), 0) + 1
            if mic:
                per = per_recorder.setdefault(dev, {})
                per[mic] = per.get(mic, 0) + 1
        total = len(recordings)
        rigs = [{"label": f"{_elide(d or '(none recorded)', 22)} + "
                          f"{_elide(m or '(not assigned)', 26)}",
                 "n": n,
                 "pct": (100.0 * n / total) if total else 0.0}
                for (d, m), n in rig_agg.items()]
        rigs.sort(key=lambda r: (-r["n"], r["label"]))

        show_rigs = False
        for dev, mic_counts in per_recorder.items():
            dev_n = sum(mic_counts.values())
            if dev_n < _MIN_BAND_N or len(mic_counts) < 2:
                continue
            runner_up = sorted(mic_counts.values(), reverse=True)[1]
            if runner_up >= 0.15 * dev_n:
                show_rigs = True
                break

        # Formats: sample rate and bit depth together, since that pair is
        # what a recorder's settings menu actually offers.
        fmt_agg = {}
        rates, depths, chans, secs = {}, {}, {}, []
        for a, _sightings in recordings.values():
            rate = _rate_label(a.get("sampleRate"))
            depth = str(a.get("bitDepth") or "").strip()
            ch = str(a.get("channels") or "").strip()
            if rate and depth:
                key = f"{rate} · {depth}"
            else:
                key = rate or depth or "(unknown)"
            fmt_agg[key] = fmt_agg.get(key, 0) + 1
            if rate:
                rates[rate] = rates.get(rate, 0) + 1
            if depth:
                depths[depth] = depths.get(depth, 0) + 1
            if ch:
                chans[ch] = chans.get(ch, 0) + 1
            sec = _seconds(a.get("duration"))
            if sec is not None:
                secs.append(sec)
        formats = [{"label": k, "n": n,
                    "pct": (100.0 * n / total) if total else 0.0}
                   for k, n in fmt_agg.items()]
        formats.sort(key=lambda r: (-r["n"], r["label"]))

        def _modal(counts):
            if not counts:
                return None
            return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]

        return {
            "recording_n": total,
            "recorders": recorders,
            "mics":      mics,
            "unassigned_mic_n": unassigned_mic_n,
            "rigs":      rigs,
            "show_rigs": show_rigs,
            "formats":   formats,
            "typical": {
                "rate_modal":  _modal(rates),
                "depth_modal": _modal(depths),
                "mono_n":      chans.get("Mono", 0),
                "stereo_n":    chans.get("Stereo", 0),
                "median_sec":  pm.median(secs),
                "max_sec":     max(secs) if secs else None,
                "total_sec":   sum(secs) if secs else None,
            },
        }

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _reportColumns(self, st, dark):
        if self.mode == "overview":
            return self._recordingOverviewHtml(st, dark)
        return self._recordingGearHtml(st, dark)

    def _recordingOverviewHtml(self, st, dark):
        def fi(n):  return f"{int(round(n)):,}"
        def ff1(n): return f"{n:,.1f}"

        totals = self._section("Your Recordings", [
            ("Recordings",           fi(st["recording_n"])),
            ("Species Recorded",     fi(st["species_n"])),
            ("Families",             fi(st["families_n"])),
            ("Locations",            fi(st["locations_n"])),
            ("Checklists",           fi(st["checklists_n"])),
            ("Days with Recordings", fi(st["days_n"])),
            ("Total Recorded Time",  _fmt_seconds(st["total_sec"])),
        ], dark)

        rhythm = self._section("Recording Days", [
            ("First Recording",     _fmt_date(st["first_date"])),
            ("Latest Recording",    _fmt_date(st["last_date"])),
            ("Recordings per Day",  ff1(st["per_day"])),
            ("Busiest Day",         _fmt_date(st["busiest_date"])),
            ("Recordings That Day", fi(st["busiest_n"])),
        ], dark)

        # As on Photos Overview, ratings get a full section only when this
        # catalog uses them.
        r = st["rating"]
        if r["uses_ratings"]:
            rows = [(f'{star} ★', fi(r["counts"][star]))
                    for star in range(5, 0, -1)]
            rows.append(("Average Rating", ff1(r["avg"])))
            if r["unrated_n"]:
                rows.append(("Unrated", fi(r["unrated_n"])))
            note = None
            if r["top_decile"] is not None:
                note = (f'Your best 10% of recordings are rated '
                        f'{r["top_decile"]}★ and above.')
            rating_sec = self._section("Rating Distribution", rows, dark, note)
        else:
            rating_sec = self._section("Rating Distribution", [
                ("Rated Recordings", "0"),
                ("Unrated",          fi(r["unrated_n"])),
            ], dark, "No recordings in this selection carry a rating.")

        return ([totals + rhythm, rating_sec], "1fr 1fr")

    def _recordingGearHtml(self, st, dark):
        def fi(n):  return f"{int(round(n)):,}"

        def gear_table(title, rows, label, note=None):
            shown = rows[:_TABLE_CAP]
            table_rows = [(
                _elide(r["label"]),
                fi(r["n"]),
                f'{r["pct"]:.1f}%',
                fi(r["species"]),
                _fmt_date(r["first"]),
                _fmt_date(r["last"]),
            ) for r in shown]
            if len(rows) > _TABLE_CAP:
                rest = rows[_TABLE_CAP:]
                table_rows.append((
                    f'Others ({len(rest)})',
                    fi(sum(r["n"] for r in rest)),
                    f'{sum(r["pct"] for r in rest):.1f}%',
                    "—", "—", "—",
                ))
            return self._table(
                title, [label, "Recordings", "Share", "Species", "First", "Last"],
                table_rows, dark, note)

        recorders = gear_table("Recorders", st["recorders"], "Recorder")

        mic_note = None
        if st["unassigned_mic_n"]:
            mic_note = ("Recording files do not store the microphone, so it is "
                        "known only once you assign a rig in Add Recordings or "
                        "Manage Recordings. Recordings without one are listed "
                        "as not assigned.")
        mics = gear_table("Microphones", st["mics"], "Microphone", mic_note)

        rigs = ""
        if st["show_rigs"]:
            rig_rows = [(_elide(r["label"], 48), fi(r["n"]), f'{r["pct"]:.1f}%')
                        for r in st["rigs"][:_TABLE_CAP]]
            rigs = self._table("Recorder and Microphone Together",
                               ["Rig", "Recordings", "Share"], rig_rows, dark,
                               "Shown because this selection uses more than "
                               "one microphone on a recorder; with one "
                               "microphone per recorder it would only repeat "
                               "the tables above.")

        t = st["typical"]
        if t["mono_n"] or t["stereo_n"]:
            channels = f'{fi(t["mono_n"])} mono · {fi(t["stereo_n"])} stereo'
        else:
            channels = "—"
        typical = self._section("Typical Settings", [
            ("Most-Used Sample Rate", t["rate_modal"] or "—"),
            ("Most-Used Bit Depth",   t["depth_modal"] or "—"),
            ("Channels",              channels),
            ("Median Length",         _fmt_seconds(t["median_sec"])),
            ("Longest Recording",     _fmt_seconds(t["max_sec"])),
            ("Total Recorded Time",   _fmt_seconds(t["total_sec"])),
        ], dark)

        fmt_rows = [(_elide(r["label"], 40), fi(r["n"]), f'{r["pct"]:.1f}%')
                    for r in st["formats"][:_TABLE_CAP]]
        formats = self._table("Formats", ["Sample Rate · Bit Depth",
                                          "Recordings", "Share"],
                              fmt_rows, dark)

        return ([recorders + mics, rigs + typical + formats], "1fr 1fr")
