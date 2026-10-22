# -*- coding: utf-8 -*-
"""Photo Statistics reports — Photos > Statistics.

Three report modes share this window, each its own menu entry:

    "overview"  totals, rating distribution, catalog health
    "gear"      bodies, lenses, rigs, typical settings, practical limits
    "coverage"  species photographed vs seen, most wanted, single-photo species

All three respect the current Sighting Filter and Media Filter, like every
other Photos-menu report (the main Statistics report is the lone exception —
it deliberately reports on everything).

Two rules shape what these reports show, both learned the hard way:

* A photo's EXIF fields may be blank, and a user's catalog may be nothing like
  the author's — some rate every photo, some rate none; some pair one lens to
  one body for years, some swap both every outing.  So nothing here assumes
  ratings exist (rating sections are conditional, and any rating threshold is a
  percentile of *that* user's own ratings, never an absolute star count), and
  bodies and lenses are always reported separately, with the body+lens "rig"
  table appearing only when a user actually mixes them.
* Counts and distributions are always meaningful; rating-weighted statistics
  are only sometimes meaningful.  Prefer the former.
"""

import form_PhotoStats
import code_Filter
import code_MediaRefresh
import code_PhotoMetrics as pm

import copy
import datetime

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMdiSubWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings


# Report modes and the window-title prefix each one carries.
_MODE_TITLES = {
    "overview": "Photos Overview",
    "gear":     "Camera Gear",
    "coverage": "Photo Coverage of Species",
}

# Rows shown before a table collapses the rest into an "Others" line.
_TABLE_CAP = 15
# Rows shown in the long species lists (Most Wanted, single-photo species).
_LIST_CAP = 25
# A per-band figure drawn from fewer photos than this is reported as unknown:
# one lucky frame should never be allowed to look like a limit.
_MIN_BAND_N = 20


def _fmt_date(d):
    """YYYY-MM-DD as "Apr 4, 2025"."""
    try:
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}, {dt.strftime('%Y')}"
    except (TypeError, ValueError):
        return d or "—"


def _elide(text, limit=30):
    text = str(text or "").strip()
    if not text:
        return "(none recorded)"
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ----------------------------------------------------------------------
# Catalog Health — REMOVED 2026-10-07, kept here because reviving it is cheap.
#
# It counted photos with missing or unreadable EXIF and offered each count as a
# link into Browse Grid.  The counts were real but not actionable: a JPEG that
# never recorded its ISO cannot be given one, and the user has no way to supply
# the value.  Where the gaps actually matter — a distribution chart drawn from
# only part of the catalog — the charts already say so themselves ("13 photos
# without an ISO not shown"), which is the same fact at the point where it
# bites.
#
# Two pieces would be worth reviving separately:
#   * Files Not Found, the one genuinely actionable row — the remedy already
#     exists in Compact Catalog and Cache.
#   * Telling "the file has no EXIF" apart from "the catalog never read it";
#     the second is fixable with Update EXIF Data for All Photos, but needs
#     the files themselves read to tell which is which.
#
# Reviving needs QTimer and QWebEnginePage imported again, the page installed
# on the web view in FillPhotoStats, and the per-photo tallies restored to
# _computeOverview.  The generic photoTest predicate it rode on is still live
# in Photos.FillPhotos and MainWindow.createPhotosGridForFilter.
#
# def _blank(field):
#     """Predicate: this photo records nothing for `field`."""
#     return lambda p, s: not str(p.get(field) or "").strip()
#
#
# _HEALTH_PROBES = {
#     "camera":   (_blank("camera"),       "Photos Missing Camera"),
#     "lens":     (_blank("lens"),         "Photos Missing Lens"),
#     "iso":      (_blank("iso"),          "Photos Missing ISO"),
#     "shutter":  (_blank("shutterSpeed"), "Photos Missing Shutter Speed"),
#     "aperture": (_blank("aperture"),     "Photos Missing Aperture"),
#     "focal":    (_blank("focalLength"),  "Photos Missing Focal Length"),
#     "exifdate": (lambda p, s: bool(p.get("exifDateInvalid")),
#                  "Photos With an Unreadable EXIF Date"),
#     "missing":  (lambda p, s: not os.path.isfile(p.get("fileName") or ""),
#                  "Photos Whose Files Are Missing"),
#     "longexp":  (lambda p, s: pm.is_long_exposure(p),
#                  "Photos Exposed Over 1 Second"),
# }
#
#
# class _HealthLinkPage(QWebEnginePage):
#     """Page that turns a Catalog Health number into an open Browse Grid."""
#
#     def __init__(self, report, parent=None):
#         super().__init__(parent)
#         self._report = report
#
#     def acceptNavigationRequest(self, url, nav_type, is_main_frame):
#         if url.scheme() == "yearbirder" and url.host() == "health":
#             key = url.path().lstrip("/")
#             QTimer.singleShot(0, lambda: self._report._openHealthPhotos(key))
#             return False
#         return super().acceptNavigationRequest(url, nav_type, is_main_frame)
# ----------------------------------------------------------------------


class PhotoStats(QMdiSubWindow, form_PhotoStats.Ui_frmPhotoStats):

    resized = Signal()
    contentReady = Signal()   # report loaded and window sized to fit it

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)
        self.mdiParent = ""
        self.filter = code_Filter.Filter()
        self.mode = "overview"
        self._stats = {}
        self.webView = None   # created lazily, so opening the app never starts
                              # a QtWebEngineProcess for a report nobody opened
        self._fitAttempts = 0
        self.resized.connect(self.resizeMe)


    def resizeEvent(self, event):
        self.resized.emit()
        return super().resizeEvent(event)


    def resizeMe(self):
        windowWidth  = self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        if self.webView is not None:
            self.webView.setGeometry(5, 27, windowWidth - 10, windowHeight - 35)


    def _designWidth(self):
        """Unscaled page width for this mode.

        The gear and coverage reports carry multi-column tables and need the
        room; the overview is two columns of label/value pairs.
        """
        return 760 if self.mode == "overview" else 920


    def scaleMe(self):
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth = int(self._designWidth() * scaleFactor)
        # Start taller than the content is likely to need: _fitToContent can
        # then only shrink the window, and the pre-fit layout never contains a
        # scrollbar.  (Chromium's last hidden frame is what appears at reveal,
        # so a scrollbar in it would flash on screen before the renderer
        # catches up.)
        windowHeight = int(820 * scaleFactor)
        self.resize(windowWidth, windowHeight)


    @code_MediaRefresh.media_report(is_content=True)   # always about media
    def FillPhotoStats(self, filter, mode="overview"):
        self.filter = filter
        self.mode = mode if mode in _MODE_TITLES else "overview"

        db = self.mdiParent.db
        photos = self._collectPhotos(filter)
        if not photos:
            return False

        if self.mode == "gear":
            self._stats = self._computeGear(photos)
        elif self.mode == "coverage":
            self._stats = self._computeCoverage(photos, filter)
        else:
            self._stats = self._computeOverview(photos)

        self._render(filter.buildWindowTitle(_MODE_TITLES[self.mode], db))
        return True


    def _render(self, title):
        """Show self._stats as the report, creating the web view on first use.

        Shared with code_RecordingStats, which subclasses this window.
        """
        if self.webView is None:
            # Size the window BEFORE creating the view: Chromium lays the page
            # out at the view's creation size, and resizes made while the
            # window is hidden may never reach the renderer — a view created at
            # the small Designer default gets a narrow, extra-tall layout that
            # poisons the _fitToContent measurement.
            self.scaleMe()
            self.webView = QWebEngineView(self)
            self.webView.setObjectName("webView")
            self.webView.page().setBackgroundColor(QColor("#1e1f26"))
            QWebEngineProfile.defaultProfile().settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            windowWidth  = self.frameGeometry().width()
            windowHeight = self.frameGeometry().height()
            self.webView.setGeometry(5, 27, windowWidth - 10, windowHeight - 35)
            self.webView.loadFinished.connect(self._fitToContent)

        self.setWindowTitle(title)
        self.webView.setHtml(self._generateHtml(self._stats, dark=True))


    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _collectPhotos(self, filter):
        """Every photo matching the filter, paired with its sighting.

        GetSightingsWithPhotos keeps a sighting when *any* of its photos
        matches the media filter, so each photo needs the individual test too
        — the same two-stage pass the Photos browser, Slideshow and Species
        Gallery make.  Skipping it would quietly inflate every number here
        under a camera, lens, ISO or rating filter.
        """
        db = self.mdiParent.db
        pairs = []
        for s in db.GetSightingsWithPhotos(filter):
            for p in s.get("photos", []):
                if db.TestIndividualPhoto(p, filter):
                    pairs.append((s, p))
        return pairs


    @staticmethod
    def _ratingSpread(photos):
        """Rating counts plus whether this catalog uses ratings at all."""
        counts = {r: 0 for r in range(6)}
        for _s, p in photos:
            counts[pm.rating(p)] += 1
        rated = [r for r in range(1, 6) for _ in range(counts[r])]
        return {
            "counts":    counts,
            "rated_n":   len(rated),
            "unrated_n": counts[0],
            "uses_ratings": len(rated) > 0,
            "avg":       (sum(rated) / len(rated)) if rated else 0.0,
            # Threshold for "your best", expressed as a percentile of this
            # user's own ratings rather than an absolute star count: a catalog
            # rated 1-3 throughout still gets a meaningful top slice.
            "top_decile": pm.percentile(sorted(rated), 0.90) if rated else None,
        }


    def _computeOverview(self, photos):
        species, families, locations, checklists = set(), set(), set(), set()
        by_date = {}
        for s, p in photos:
            name = s["commonName"]
            if pm.is_species(name):
                species.add(name)
            if s.get("family"):
                families.add(s["family"])
            locations.add(s["location"])
            checklists.add(s["checklistID"])
            by_date[s["date"]] = by_date.get(s["date"], 0) + 1

        busiest_date, busiest_n = ("", 0)
        for d, n in by_date.items():
            if n > busiest_n or (n == busiest_n and d > busiest_date):
                busiest_date, busiest_n = d, n

        dates = sorted(by_date)
        return {
            "photo_n":      len(photos),
            "species_n":    len(species),
            "families_n":   len(families),
            "locations_n":  len(locations),
            "checklists_n": len(checklists),
            "days_n":       len(by_date),
            "first_date":   dates[0] if dates else "",
            "last_date":    dates[-1] if dates else "",
            "per_day":      (len(photos) / len(by_date)) if by_date else 0.0,
            "busiest_date": busiest_date,
            "busiest_n":    busiest_n,
            "rating":       self._ratingSpread(photos),
        }


    @staticmethod
    def _gearRows(photos, key):
        """Per-body or per-lens rows: photos, share, species, date span."""
        agg = {}
        for s, p in photos:
            label = str(p.get(key) or "").strip()
            rec = agg.setdefault(label, {"n": 0, "species": set(),
                                         "first": "", "last": ""})
            rec["n"] += 1
            if pm.is_species(s["commonName"]):
                rec["species"].add(s["commonName"])
            d = s["date"]
            if not rec["first"] or d < rec["first"]:
                rec["first"] = d
            if not rec["last"] or d > rec["last"]:
                rec["last"] = d
        total = len(photos)
        rows = [{
            "label":   label or "(none recorded)",
            "n":       rec["n"],
            "pct":     (100.0 * rec["n"] / total) if total else 0.0,
            "species": len(rec["species"]),
            "first":   rec["first"],
            "last":    rec["last"],
        } for label, rec in agg.items()]
        rows.sort(key=lambda r: (-r["n"], r["label"]))
        return rows


    def _computeGear(self, photos):
        bodies = self._gearRows(photos, "camera")
        lenses = self._gearRows(photos, "lens")

        # Rigs earn a table only when this user actually mixes bodies and
        # lenses.  For a photographer who keeps one lens on one body, the rig
        # table just repeats the two above it; for one who swaps, it is the
        # only place the pairing shows.
        rig_agg = {}
        per_body_lenses = {}
        for s, p in photos:
            cam = str(p.get("camera") or "").strip()
            lens = str(p.get("lens") or "").strip()
            rig_agg[(cam, lens)] = rig_agg.get((cam, lens), 0) + 1
            per_body = per_body_lenses.setdefault(cam, {})
            per_body[lens] = per_body.get(lens, 0) + 1
        total = len(photos)
        rigs = [{"label": f"{_elide(c, 22)} + {_elide(l, 26)}",
                 "n": n,
                 "pct": (100.0 * n / total) if total else 0.0}
                for (c, l), n in rig_agg.items()]
        rigs.sort(key=lambda r: (-r["n"], r["label"]))

        # "Mixing" means a body whose photos are genuinely split across lenses,
        # not merely a body that has seen a second lens: a handful of photos
        # carrying mismatched EXIF (a compact's body name against an SLR lens,
        # say) must not be enough to turn the table on.  So a body counts as
        # mixed only when its second-most-used lens holds a real share of its
        # own photos.
        show_rigs = False
        for cam, lens_counts in per_body_lenses.items():
            body_n = sum(lens_counts.values())
            if body_n < _MIN_BAND_N or len(lens_counts) < 2:
                continue
            runner_up = sorted(lens_counts.values(), reverse=True)[1]
            if runner_up >= 0.15 * body_n:
                show_rigs = True
                break

        isos     = [v for v in (pm.iso(p) for _s, p in photos) if v is not None]
        apertures = [v for v in (pm.aperture(p) for _s, p in photos) if v is not None]
        shutters = [v for v in (pm.shutter_denom(p) for _s, p in photos) if v is not None]
        focals   = [v for v in (pm.focal(p) for _s, p in photos) if v is not None]

        def _modal(values):
            if not values:
                return None
            counts = {}
            for v in values:
                counts[v] = counts.get(v, 0) + 1
            return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]

        # Practical limits, computed without reference to ratings so they mean
        # the same thing in a catalog nobody has rated.  Every photo here is
        # one the user kept, so the slow-shutter edge of each focal band is a
        # setting that has produced a photo worth keeping.  The edge is taken
        # at the 5th percentile, not the minimum: a single lucky frame should
        # not get to look like a limit.
        bands = {}
        for _s, p in photos:
            f = pm.focal(p)
            d = pm.shutter_denom(p)
            i = pm.iso(p)
            if f is None:
                continue
            band = (f // 100) * 100
            rec = bands.setdefault(band, {"shutters": [], "isos": []})
            if d is not None:
                rec["shutters"].append(d)
            if i is not None:
                rec["isos"].append(i)

        limit_rows = []
        for band in sorted(bands):
            rec = bands[band]
            n = len(rec["shutters"])
            slow = pm.percentile(sorted(rec["shutters"]), 0.05) if n >= _MIN_BAND_N else None
            hi_iso = pm.percentile(sorted(rec["isos"]), 0.95) if len(rec["isos"]) >= _MIN_BAND_N else None
            limit_rows.append({
                "band":   f"{band}–{band + 99} mm",
                "n":      n,
                "slow":   pm.fmt_shutter(slow),
                "hi_iso": f"{hi_iso:,}" if hi_iso else "—",
            })

        return {
            "photo_n": len(photos),
            "bodies":  bodies,
            "lenses":  lenses,
            "rigs":    rigs,
            "show_rigs": show_rigs,
            "typical": {
                "iso_median":    pm.median(isos),
                "iso_ceiling":   pm.percentile(sorted(isos), 0.95) if isos else None,
                "iso_max":       max(isos) if isos else None,
                "shutter_median": pm.median(shutters),
                "aperture_modal": _modal(apertures),
                "focal_modal":   _modal(focals),
                "focal_max":     max(focals) if focals else None,
                "iso_n":         len(isos),
                "shutter_n":     len(shutters),
                "focal_n":       len(focals),
            },
            "limits":  limit_rows,
        }


    def _computeCoverage(self, photos, filter):
        photo_species = {}
        photo_families = set()
        for s, p in photos:
            name = s["commonName"]
            photo_species[name] = photo_species.get(name, 0) + 1
            if s.get("family"):
                photo_families.add(s["family"])

        # The "seen" population must ignore the media filter, or the comparison
        # becomes photographed-vs-photographed: a photo constraint would reject
        # every sighting that has no matching photo, which is exactly the set
        # this report is looking for.  The sighting-side filter (dates, region,
        # taxonomy) still applies.
        seen_filter = copy.deepcopy(filter)
        seen_filter.clearPhotoFilter()
        seen_counts = {}
        seen_families = set()
        for s in self.mdiParent.db.GetSightings(seen_filter):
            name = s["commonName"]
            seen_counts[name] = seen_counts.get(name, 0) + 1
            if s.get("family"):
                seen_families.add(s["family"])

        photo_species_only = {n for n in photo_species if pm.is_species(n)}
        seen_species_only = {n for n in seen_counts if pm.is_species(n)}

        most_wanted = sorted(
            ((n, c) for n, c in seen_counts.items()
             if n not in photo_species and pm.is_species(n)),
            key=lambda nc: (-nc[1], nc[0]))

        single = sorted(n for n, c in photo_species.items() if c == 1)
        most_photographed = sorted(photo_species.items(),
                                   key=lambda nc: (-nc[1], nc[0]))

        return {
            "photo_n":        len(photos),
            "photo_species":  len(photo_species_only),
            "seen_species":   len(seen_species_only),
            "photo_taxa":     len(photo_species),
            "photo_families": len(photo_families),
            "seen_families":  len(seen_families),
            "pct_species":    (100.0 * len(photo_species_only) / len(seen_species_only))
                              if seen_species_only else 0.0,
            "pct_families":   (100.0 * len(photo_families) / len(seen_families))
                              if seen_families else 0.0,
            "most_wanted":    most_wanted,
            "single":         single,
            "most_photographed": most_photographed,
            "photo_filter_active": filter.hasPhotoFilter(),
        }


    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    @staticmethod
    def _palette(dark):
        if dark:
            return {"sec_bg": "#252730", "hdr": "#4f8ef7", "sub": "#c8cad8",
                    "val": "#e2e4ec", "border": "#3a3d4e", "muted": "#9a9cad"}
        return {"sec_bg": "#f5f6f8", "hdr": "#333333", "sub": "#555555",
                "val": "#000000", "border": "#cccccc", "muted": "#666666"}

    def _shell(self, title, body, dark, note=None):
        c = self._palette(dark)
        note_html = (f'<div style="font-size:8.5pt;color:{c["muted"]};'
                     f'margin-top:10px;line-height:1.4;">{note}</div>'
                     if note else "")
        return (
            f'<div style="background:{c["sec_bg"]};border-radius:6px;padding:14px;'
            f'margin-bottom:16px;">'
            f'<div style="font-size:12pt;font-weight:bold;color:{c["hdr"]};'
            f'border-bottom:1px solid {c["border"]};padding-bottom:6px;'
            f'margin-bottom:10px;">{title}</div>'
            f'{body}{note_html}'
            f'</div>'
        )

    def _section(self, title, rows, dark, note=None):
        """Label/value section, styled to match the main Statistics report."""
        c = self._palette(dark)
        rows_html = "".join(
            f'<tr>'
            f'<td style="padding:4px 8px;color:{c["sub"]};font-size:9pt;">{lbl}</td>'
            f'<td style="padding:4px 8px;color:{c["val"]};font-size:9pt;'
            f'text-align:right;font-weight:bold;">{val}</td>'
            f'</tr>'
            for lbl, val in rows
        )
        body = (f'<table style="width:100%;border-collapse:collapse;">'
                f'{rows_html}</table>')
        return self._shell(title, body, dark, note)

    def _table(self, title, headers, rows, dark, note=None):
        """Multi-column table section.  headers/rows align left-first, rest right."""
        c = self._palette(dark)

        def cell(text, i, header=False):
            tag = "th" if header else "td"
            align = "left" if i == 0 else "right"
            color = c["sub"] if (header or i > 0) else c["val"]
            weight = "bold" if (header or i == 0) else "normal"
            rule = f'border-bottom:1px solid {c["border"]};' if header else ""
            return (f'<{tag} style="padding:4px 8px;color:{color};'
                    f'font-size:9pt;text-align:{align};font-weight:{weight};'
                    f'{rule}">{text}</{tag}>')

        head = "<tr>" + "".join(cell(h, i, header=True)
                                for i, h in enumerate(headers)) + "</tr>"
        body_rows = "".join(
            "<tr>" + "".join(cell(v, i) for i, v in enumerate(r)) + "</tr>"
            for r in rows
        )
        body = (f'<table style="width:100%;border-collapse:collapse;">'
                f'{head}{body_rows}</table>')
        return self._shell(title, body, dark, note)

    def _names_section(self, title, names, dark, cap=_LIST_CAP, note=None):
        """Comma-run of species names, capped with a "+N more" tail."""
        c = self._palette(dark)
        shown = names[:cap]
        tail = (f' <span style="color:{c["muted"]};">+{len(names) - cap:,} more'
                f'</span>' if len(names) > cap else "")
        body = (f'<div style="color:{c["val"]};font-size:9pt;line-height:1.6;">'
                f'{", ".join(shown) if shown else "(none)"}{tail}</div>')
        return self._shell(title, body, dark, note)

    def _reportColumns(self, st, dark):
        """(column HTML list, CSS grid-template-columns) for this mode."""
        if self.mode == "gear":
            return self._gearHtml(st, dark)
        if self.mode == "coverage":
            return self._coverageHtml(st, dark)
        return self._overviewHtml(st, dark)

    def _generateHtml(self, st, dark=True):
        cols, grid = self._reportColumns(st, dark)

        bg   = "#1e1f26" if dark else "#ffffff"
        text = "#e2e4ec" if dark else "#111111"

        # A fixed pixel width for the on-screen report.  While the window is
        # hidden Chromium lays the page out with an unreliable viewport, so a
        # fluid layout can be measured in a squeezed, extra-tall state; a fixed
        # width makes the layout — and the height _fitToContent measures —
        # viewport-independent.  The light PDF variant stays fluid for the
        # print engine.
        body_width_css = ""
        if dark:
            try:
                sf = float(self.mdiParent.scaleFactor)
            except (AttributeError, TypeError, ValueError):
                sf = 1.0
            view_w = int(self._designWidth() * sf) - 10
            body_width_css = f"width: {view_w - 40}px;"

        col_html = "".join(f'<div class="col">{c}</div>' for c in cols)
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{
    background: {bg};
    color: {text};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 20px;
    {body_width_css}
  }}
  .grid {{
    display: grid;
    grid-template-columns: {grid};
    gap: 16px;
  }}
  .col {{ display: flex; flex-direction: column; }}
</style>
</head>
<body>
<div class="grid">{col_html}</div>
</body></html>"""


    def _overviewHtml(self, st, dark):
        def fi(n):  return f"{int(round(n)):,}"
        def ff1(n): return f"{n:,.1f}"

        totals = self._section("Your Photos", [
            ("Photos",               fi(st["photo_n"])),
            ("Species Photographed", fi(st["species_n"])),
            ("Families",             fi(st["families_n"])),
            ("Locations",            fi(st["locations_n"])),
            ("Checklists",           fi(st["checklists_n"])),
            ("Days with Photos",     fi(st["days_n"])),
        ], dark)

        rhythm = self._section("Shooting Days", [
            ("First Photo",            _fmt_date(st["first_date"])),
            ("Latest Photo",           _fmt_date(st["last_date"])),
            ("Photos per Day",         ff1(st["per_day"])),
            ("Busiest Day",            _fmt_date(st["busiest_date"])),
            ("Photos That Day",        fi(st["busiest_n"])),
        ], dark)

        # Ratings get a section only when this catalog uses them.  A column of
        # zeros tells a non-rating user nothing except that something may be
        # broken.
        r = st["rating"]
        if r["uses_ratings"]:
            rows = [(f'{star} ★', fi(r["counts"][star]))
                    for star in range(5, 0, -1)]
            rows.append(("Average Rating", ff1(r["avg"])))
            if r["unrated_n"]:
                rows.append(("Unrated", fi(r["unrated_n"])))
            note = None
            if r["top_decile"] is not None:
                note = (f'Your best 10% of photos are rated '
                        f'{r["top_decile"]}★ and above.')
            rating_sec = self._section("Rating Distribution", rows, dark, note)
        else:
            rating_sec = self._section("Rating Distribution", [
                ("Rated Photos", "0"),
                ("Unrated",      fi(r["unrated_n"])),
            ], dark, "No photos in this selection carry a rating, so the "
                     "rating-based figures elsewhere are left out.")

        return ([totals + rhythm, rating_sec], "1fr 1fr")


    def _gearHtml(self, st, dark):
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
                title, [label, "Photos", "Share", "Species", "First", "Last"],
                table_rows, dark, note)

        bodies = gear_table("Camera Bodies", st["bodies"], "Body")
        lenses = gear_table("Lenses", st["lenses"], "Lens")

        rigs = ""
        if st["show_rigs"]:
            rig_rows = [(_elide(r["label"], 48), fi(r["n"]), f'{r["pct"]:.1f}%')
                        for r in st["rigs"][:_TABLE_CAP]]
            rigs = self._table("Body and Lens Together",
                               ["Rig", "Photos", "Share"], rig_rows, dark,
                               "Shown because this selection mixes bodies and "
                               "lenses; with one lens per body it would only "
                               "repeat the tables above.")

        t = st["typical"]
        median_shutter = ("—" if t["shutter_median"] is None
                          else pm.fmt_shutter(int(round(t["shutter_median"]))))
        typical = self._section("Typical Settings", [
            ("Median Shutter",    median_shutter),
            ("Most-Used Aperture", f'f/{t["aperture_modal"]}' if t["aperture_modal"] else "—"),
            ("Most-Used Focal Length", f'{t["focal_modal"]} mm' if t["focal_modal"] else "—"),
            ("Longest Focal Length", f'{t["focal_max"]} mm' if t["focal_max"] else "—"),
        ], dark)

        if st["limits"]:
            limits = self._table(
                "Practical Limits",
                ["Focal Length", "Photos", "Slow Edge", "ISO Ceiling"],
                [(r["band"], f'{r["n"]:,}', r["slow"], r["hi_iso"])
                 for r in st["limits"]],
                dark,
                "Slow Edge is the shutter speed 95% or more of your photos at "
                "that focal length beat; ISO Ceiling is the one 95% stayed "
                "under. Neither is your slowest or highest ever — those are "
                "single frames. Every photo in your catalog is one you chose "
                "to keep, so read these as an envelope you have demonstrated, "
                f"not a rule. Bands under {_MIN_BAND_N} photos are left blank, "
                "so one lucky frame cannot look like a limit.")
        else:
            limits = self._section(
                "Practical Limits", [("Focal Length Recorded", "0")], dark,
                "No photo in this selection records a focal length, so there "
                "is nothing to measure an envelope against.")

        ceiling = self._section("ISO Reach", [
            ("Median ISO",            f'{t["iso_median"]:,.0f}' if t["iso_median"] else "—"),
            ("Practical Ceiling",     f'{t["iso_ceiling"]:,}' if t["iso_ceiling"] else "—"),
            ("Highest ISO",           f'{t["iso_max"]:,}' if t["iso_max"] else "—"),
        ], dark, "Practical ceiling is the 95th percentile: the ISO you reach "
                 "for regularly, rather than the once-ever maximum.")

        return ([bodies + lenses, rigs + typical + limits + ceiling], "1fr 1fr")


    def _coverageHtml(self, st, dark):
        def fi(n):  return f"{int(round(n)):,}"
        def ff1(n): return f"{n:,.1f}"

        note = None
        if st["photo_filter_active"]:
            note = ("The species-seen totals ignore the Media Filter on "
                    "purpose: a camera, lens or rating constraint would hide "
                    "every sighting without a matching photo, which is exactly "
                    "what this report is looking for.")
        coverage = self._section("Coverage", [
            ("Species Photographed",  fi(st["photo_species"])),
            ("Species Seen",          fi(st["seen_species"])),
            ("Species Coverage",      ff1(st["pct_species"]) + "%"),
            ("Families Photographed", fi(st["photo_families"])),
            ("Families Seen",         fi(st["seen_families"])),
            ("Family Coverage",       ff1(st["pct_families"]) + "%"),
        ], dark, note)

        top_rows = [(_elide(n, 34), fi(c))
                    for n, c in st["most_photographed"][:_TABLE_CAP]]
        most = self._table("Most Photographed", ["Species", "Photos"],
                           top_rows, dark)

        wanted_rows = [(_elide(n, 34), fi(c))
                       for n, c in st["most_wanted"][:_LIST_CAP]]
        wanted_note = (f'{len(st["most_wanted"]):,} species in this selection '
                       f'have no photo.')
        wanted = self._table("Most Wanted", ["Species", "Times Seen"],
                             wanted_rows, dark, wanted_note)

        single = self._names_section(
            f'Single-Photo Species ({len(st["single"]):,})',
            [_elide(n, 34) for n in st["single"]], dark,
            note="One frame each — the species a single deletion would "
                 "drop from your photographed list.")

        return ([coverage + most, wanted + single], "1fr 1fr")


    # ------------------------------------------------------------------
    # Fit the window to the report
    # ------------------------------------------------------------------

    def _fitToContent(self, ok=True):
        """Resize the window so the whole report fits without a scrollbar.

        Unlike the main Statistics report, which measures only on Windows and
        otherwise trusts a tuned design height, these reports measure on every
        platform: their height swings with the data (a user with two lenses and
        one with twelve get very different tables), so no fixed height can be
        right for both.
        """
        if not ok or self.webView is None:
            self.contentReady.emit()
            return
        self._fitAttempts = 0
        self._measureContent()


    def _measureContent(self):
        # documentElement.scrollHeight is useless here — it never reports less
        # than the viewport, so the window could only ratchet taller.  Measure
        # the grid itself.
        js = ("(function(){"
              "var g = document.querySelector('.grid');"
              "if (!g) return 0;"
              "return Math.ceil(g.getBoundingClientRect().bottom"
              "                 + window.scrollY);"
              "})()")
        self.webView.page().runJavaScript(js, self._applyFit)


    def _applyFit(self, gridBottom):
        # Same hazard as the photo browsers: resizing a maximized subwindow
        # shrinks it while Qt still reports it as maximized.  A maximized
        # report already fills the MDI area, so there is nothing to fit.
        if self.isMaximized():
            self.contentReady.emit()
            return
        try:
            gridBottom = int(gridBottom)
        except (TypeError, ValueError):
            gridBottom = 0
        if gridBottom <= 0:
            self.contentReady.emit()
            return

        # grid bottom + the 20px body margin below it, then the webView chrome:
        # the view occupies (5, 27, w-10, h-35) — 27px above, 8px below.
        target = gridBottom + 20 + 35 + 2
        try:
            mdiHeight = self.mdiParent.mdiArea.height()
        except Exception:
            self.contentReady.emit()
            return
        target = max(400, min(target, mdiHeight - 10))

        if abs(target - self.height()) <= 4 or self._fitAttempts >= 3:
            self.contentReady.emit()
            return

        self._fitAttempts += 1
        self.resize(self.width(), target)
        self.move(self.x(), max(0, (mdiHeight - target) // 2))
        # The layout just measured may have been for a stale window size, so
        # measure again and correct until it stops moving.
        self._measureContent()


    def html(self):
        """Light-theme HTML for PDF output."""
        if not self._stats:
            return ""

        title = self.windowTitle()
        if ': ' in title:
            type_part, filter_part = title.split(': ', 1)
            heading = '<h1>' + type_part + '</h1><h2>' + filter_part + '</h2>'
        else:
            heading = '<h1>' + title + '</h1>'

        heading_styles = (
            'h1 { font-family: "Times New Roman", Times, serif; '
            'font-size: 18pt; margin-bottom: 4px; }\n'
            'h2 { font-family: "Times New Roman", Times, serif; '
            'font-size: 13pt; font-weight: normal; margin-top: 0; '
            'margin-bottom: 16px; }\n'
        )

        report_html = self._generateHtml(self._stats, dark=False)
        report_html = report_html.replace("</style>", heading_styles + "</style>", 1)
        report_html = report_html.replace("<body>", "<body>" + heading, 1)
        return report_html
