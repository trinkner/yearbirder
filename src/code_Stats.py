import form_Stats
import code_Filter

from math import floor
import os
import sys
import datetime

try:
    import piexif as _piexif
    _PIEXIF_AVAILABLE = True
except ImportError:
    _PIEXIF_AVAILABLE = False

from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QMdiSubWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile


def _get_latest_exif_ts(filenames):
    """Return the latest EXIF DateTimeOriginal string ('YYYY:MM:DD HH:MM:SS') found
    across filenames, or None if none could be read."""
    if not _PIEXIF_AVAILABLE:
        return None
    latest = None
    for fname in filenames:
        if not fname or not os.path.isfile(fname):
            continue
        try:
            exif = _piexif.load(fname)
            raw = exif.get("Exif", {}).get(_piexif.ExifIFD.DateTimeOriginal, b"")
            if isinstance(raw, bytes):
                raw = raw.decode("ascii", errors="ignore").strip()
            if raw and len(raw) == 19:
                if latest is None or raw > latest:
                    latest = raw
        except Exception:
            pass
    return latest


def _tiebreak_species(tied_names, date, species_date_photos, want_latest):
    """Break a checklist-date tie among tied_names using each species' latest EXIF
    timestamp on that date.  want_latest=True picks the most-recently-shot species;
    False picks the earliest-shot.  Falls back to alphabetical when EXIF is unavailable."""
    exif_map = {}
    for name in tied_names:
        ts = _get_latest_exif_ts(species_date_photos.get((name, date), []))
        if ts is not None:
            exif_map[name] = ts
    if exif_map:
        fn = max if want_latest else min
        return fn(exif_map.items(), key=lambda x: x[1])[0]
    return sorted(tied_names)[0]


class Stats(QMdiSubWindow, form_Stats.Ui_frmStats):

    resized = Signal()
    contentReady = Signal()   # report loaded and window sized to fit it

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_statistics_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)
        self.mdiParent = ""
        self.filter = code_Filter.Filter()
        self._stats = {}
        self.webView = None   # created lazily in FillStats to avoid starting
                              # the QtWebEngineProcess at app startup
        self.resized.connect(self.resizeMe)


    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)


    def resizeMe(self):
        windowWidth  = self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth - 10, windowHeight - 35)
        if self.webView is not None:
            self.webView.setGeometry(5, 27, windowWidth - 10, windowHeight - 35)


    def scaleMe(self):
        scaleFactor  = self.mdiParent.scaleFactor
        has_photos   = getattr(self, "_has_photos", False)
        windowWidth  = int((1000 if has_photos else 640) * scaleFactor)
        # Windows renders the report taller (Segoe UI metrics), so the window
        # is fitted to the measured content height after the page loads
        # (_fitToContent).  Start ABOVE the real need on purpose: the fit can
        # only shrink the window then, and the pre-fit layout never contains a
        # scrollbar — Chromium's last hidden frame is what shows at reveal, so
        # a scrollbar in it would briefly flash on screen before the renderer
        # catches up.
        windowHeight = int((830 if sys.platform == "win32" else 760) * scaleFactor)
        self.resize(windowWidth, windowHeight)


    def FillStats(self, filter):
        self.filter = filter
        sightings = self.mdiParent.db.GetSightings(filter)
        if not sightings:
            return False

        has_photos = self.mdiParent.db.photoDataFileOpenFlag
        self._stats = self._computeStats(sightings, has_photos)
        self._has_photos = has_photos

        # Lazy-create the QWebEngineView the first time it's needed.
        # This defers the expensive QtWebEngineProcess startup until the
        # Stats window is actually populated, keeping app launch fast.
        if self.webView is None:
            # Size the window to its final dimensions BEFORE creating the view:
            # Chromium lays the page out at the view's creation size, and while
            # the window is hidden later resizes may never reach the renderer —
            # a view created at the small Designer default gets a narrow,
            # extra-tall layout that poisons _fitToContent's measurement.
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

        self.setWindowTitle(filter.buildWindowTitle("Statistics", self.mdiParent.db))
        self.webView.setHtml(self._generateHtml(self._stats, self._has_photos, dark=True))
        return True


    def _fitToContent(self, ok=True):
        """Resize the window so the whole report fits without a scrollbar.

        The report's rendered height varies with platform font metrics — the
        Windows Segoe UI layout runs taller than the macOS one the 760px
        design height was tuned for, and a fixed bump wasn't reliable either.
        So on Windows, measure the report's actual height in the page and
        size the window to it, capped to the MDI area.  Emits contentReady
        when finished so a caller can reveal a hidden window only once it has
        its final size (no visible resize jerk).

        Two measurement subtleties: documentElement.scrollHeight is useless
        here (it never reports less than the viewport, so the window could
        only ever ratchet taller — measure the .grid element instead), and at
        loadFinished the renderer may still be laid out at a stale window
        size (scaleMe's resize propagates to Chromium asynchronously), so
        measure → resize → re-measure until the height converges.
        """
        if not ok or sys.platform != "win32" or self.webView is None:
            self.contentReady.emit()
            return
        self._fitAttempts = 0
        self._measureContent()


    def _measureContent(self):
        js = ("(function(){"
              "var g = document.querySelector('.grid');"
              "if (!g) return 0;"
              "return Math.ceil(g.getBoundingClientRect().bottom"
              "                 + window.scrollY);"
              "})()")
        self.webView.page().runJavaScript(js, self._applyFit)


    def _applyFit(self, gridBottom):
        try:
            gridBottom = int(gridBottom)
        except (TypeError, ValueError):
            gridBottom = 0
        if gridBottom <= 0:
            self.contentReady.emit()
            return

        # grid bottom + 20px body margin below it, then the webView chrome:
        # view occupies (5, 27, w-10, h-35), i.e. 27px above it, 8px below.
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
        # keep the window vertically centered in the MDI area
        self.move(self.x(), max(0, (mdiHeight - target) // 2))
        # the layout we measured may have been for a stale window size —
        # measure again and correct until stable
        self._measureContent()


    def handlePhotoDeletion(self, filename):
        self.FillStats(self.filter)


    # ------------------------------------------------------------------
    # Statistics computation
    # ------------------------------------------------------------------

    def _computeStats(self, sightings, has_photos=False):

        species_set  = set()
        family_set   = set()
        country_set  = set()
        state_set    = set()
        county_set   = set()
        location_set = set()
        date_set     = set()
        checklist_dict = {}   # checklistID -> dict

        for s in sightings:
            name = s["commonName"]
            is_species = (" x " not in name and
                          "sp."  not in name and
                          "/"    not in name)
            if is_species:
                species_set.add(name)
            if s.get("family"):
                family_set.add(s["family"])
            if s.get("country"):
                country_set.add(s["country"])
            if s.get("state"):
                state_set.add(s["state"])
            if s.get("county"):
                county_set.add(s["county"])
            location_set.add(s["location"])
            date_set.add(s["date"])

            cid = s["checklistID"]
            if cid not in checklist_dict:
                checklist_dict[cid] = {
                    "protocol": (s.get("protocol") or "").strip(),
                    "duration": s.get("duration") or "",
                    "distance": s.get("distance") or "",
                    "species":  set(),
                    "ind_count": 0,
                }
            if is_species:
                checklist_dict[cid]["species"].add(name)
            cnt = s.get("count") or ""
            if cnt and cnt != "X":
                try:
                    checklist_dict[cid]["ind_count"] += int(cnt)
                except (ValueError, TypeError):
                    pass

        total_minutes = 0.0
        total_km      = 0.0
        proto_counts  = {"Traveling": 0, "Stationary": 0,
                         "Casual": 0, "Historical": 0, "Other": 0}
        traveling  = []
        stationary = []
        incidental = []

        for c in checklist_dict.values():
            if c["duration"]:
                try:
                    total_minutes += float(c["duration"])
                except (ValueError, TypeError):
                    pass
            if c["distance"]:
                try:
                    total_km += float(c["distance"])
                except (ValueError, TypeError):
                    pass
            proto = c["protocol"]
            if "Traveling" in proto:
                proto_counts["Traveling"] += 1
                traveling.append(c)
            elif "Stationary" in proto:
                proto_counts["Stationary"] += 1
                stationary.append(c)
            elif "Casual" in proto:
                proto_counts["Casual"] += 1
                incidental.append(c)
            elif "Historical" in proto:
                proto_counts["Historical"] += 1
            else:
                proto_counts["Other"] += 1

        def _avg(lst):
            return sum(lst) / len(lst) if lst else 0.0

        def _floats(lst, key):
            return [float(c[key]) for c in lst if c.get(key)]

        total_checklists   = len(checklist_dict)
        total_individuals  = sum(c["ind_count"] for c in checklist_dict.values())

        photo_stats = {}
        if has_photos:
            photo_count        = 0
            photo_species_set  = set()
            photo_location_set = set()
            photo_checklist_set= set()
            ratings            = []
            species_photo_count= {}   # commonName -> count
            species_first_date = {}   # commonName -> earliest photo date (YYYY-MM-DD)
            species_date_photos= {}   # (commonName, date) -> [fileName, ...]

            for s in sightings:
                photos = s.get("photos") or []
                if not photos:
                    continue
                name = s["commonName"]
                is_species = (" x " not in name and
                              "sp."  not in name and
                              "/"    not in name)
                date = s.get("date") or ""
                for p in photos:
                    photo_count += 1
                    if is_species:
                        photo_species_set.add(name)
                        species_photo_count[name] = species_photo_count.get(name, 0) + 1
                        if date:
                            prev_first = species_first_date.get(name)
                            if prev_first is None or date < prev_first:
                                species_first_date[name] = date
                            fname = p.get("fileName", "")
                            if fname:
                                key = (name, date)
                                if key not in species_date_photos:
                                    species_date_photos[key] = []
                                species_date_photos[key].append(fname)
                    photo_location_set.add(s["location"])
                    photo_checklist_set.add(s["checklistID"])
                    try:
                        r = int(p.get("rating") or 0)
                        if r > 0:
                            ratings.append(r)
                    except (ValueError, TypeError):
                        pass

            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
            top_species = sorted(species_photo_count.items(),
                                 key=lambda x: x[1], reverse=True)

            most_recent_new_species = ""
            most_recent_new_date    = ""
            if species_first_date:
                most_recent_new_date = max(species_first_date.values())
                tied_mn = [n for n, d in species_first_date.items() if d == most_recent_new_date]
                most_recent_new_species = (
                    tied_mn[0] if len(tied_mn) == 1 else
                    _tiebreak_species(tied_mn, most_recent_new_date, species_date_photos, want_latest=True)
                )

            photo_stats = {
                "photo_count":              photo_count,
                "photo_species":            len(photo_species_set),
                "photo_locations":          len(photo_location_set),
                "photo_checklists":         len(photo_checklist_set),
                "photo_avg_rating":         avg_rating,
                "photo_rated_count":        len(ratings),
                "photo_unrated_count":      photo_count - len(ratings),
                "photo_top_species":        top_species[:1],
                "photo_most_recent_new_species": most_recent_new_species,
                "photo_most_recent_new_date":    most_recent_new_date,
            }

        rec_stats = {}
        if has_photos:
            rec_count         = 0
            rec_species_set   = set()
            rec_location_set  = set()
            rec_checklist_set = set()
            rec_ratings       = []
            rec_sp_count      = {}   # commonName -> recording count
            rec_sp_first_date = {}   # commonName -> earliest recording date

            for s in sightings:
                recs = s.get("audio") or []
                if not recs:
                    continue
                name = s["commonName"]
                is_species = (" x " not in name and
                              "sp."  not in name and
                              "/"    not in name)
                date = s.get("date") or ""
                for r in recs:
                    rec_count += 1
                    if is_species:
                        rec_species_set.add(name)
                        rec_sp_count[name] = rec_sp_count.get(name, 0) + 1
                        if date:
                            prev = rec_sp_first_date.get(name)
                            if prev is None or date < prev:
                                rec_sp_first_date[name] = date
                    rec_location_set.add(s["location"])
                    rec_checklist_set.add(s["checklistID"])
                    try:
                        rv = int(r.get("rating") or 0)
                        if rv > 0:
                            rec_ratings.append(rv)
                    except (ValueError, TypeError):
                        pass

            if rec_count > 0:
                top_rec_sp     = sorted(rec_sp_count.items(), key=lambda x: x[1], reverse=True)
                rec_avg_rating = sum(rec_ratings) / len(rec_ratings) if rec_ratings else 0.0

                rec_new_sp   = ""
                rec_new_date = ""
                if rec_sp_first_date:
                    rec_new_date = max(rec_sp_first_date.values())
                    tied = [n for n, d in rec_sp_first_date.items() if d == rec_new_date]
                    rec_new_sp = sorted(tied)[0]

                rec_stats = {
                    "rec_count":         rec_count,
                    "rec_species":       len(rec_species_set),
                    "rec_locations":     len(rec_location_set),
                    "rec_checklists":    len(rec_checklist_set),
                    "rec_avg_rating":    rec_avg_rating,
                    "rec_rated_count":   len(rec_ratings),
                    "rec_unrated_count": rec_count - len(rec_ratings),
                    "rec_top_species":   top_rec_sp[:1],
                    "rec_new_species":   rec_new_sp,
                    "rec_new_date":      rec_new_date,
                }

        return {
            "total_species":            len(species_set),
            "total_families":           len(family_set),
            "total_countries":          len(country_set),
            "total_states":             len(state_set),
            "total_counties":           len(county_set),
            "total_locations":          len(location_set),
            "total_days":               len(date_set),
            "total_checklists":         total_checklists,
            "total_species_records":    len(sightings),
            "total_individuals":        total_individuals,
            "avg_species_per_checklist": _avg([len(c["species"]) for c in checklist_dict.values()]),
            "total_minutes":            total_minutes,
            "total_hours":              total_minutes / 60.0,
            "total_days_time":          total_minutes / 1440.0,
            "total_km":                 total_km,
            "total_miles":              total_km * 0.621371,
            "proto_traveling":          proto_counts["Traveling"],
            "proto_stationary":         proto_counts["Stationary"],
            "proto_casual":             proto_counts["Casual"],
            "proto_historical":         proto_counts["Historical"],
            "proto_other":              proto_counts["Other"],
            "avg_trav_species":         _avg([len(c["species"]) for c in traveling]),
            "avg_trav_duration":        _avg(_floats(traveling,  "duration")),
            "avg_trav_distance":        _avg(_floats(traveling,  "distance")),
            "avg_stat_species":         _avg([len(c["species"]) for c in stationary]),
            "avg_stat_duration":        _avg(_floats(stationary, "duration")),
            "avg_incidental_species":   _avg([len(c["species"]) for c in incidental]),
            **photo_stats,
            **rec_stats,
        }


    # ------------------------------------------------------------------
    # HTML generation  (dark=True for on-screen; dark=False for PDF)
    # ------------------------------------------------------------------

    def _section(self, title, rows, dark):
        if dark:
            sec_bg    = "#252730"
            hdr_color = "#4f8ef7"
            sub_text  = "#c8cad8"
            val_color = "#e2e4ec"
            border    = "#3a3d4e"
        else:
            sec_bg    = "#f5f6f8"
            hdr_color = "#333333"
            sub_text  = "#555555"
            val_color = "#000000"
            border    = "#cccccc"

        rows_html = "".join(
            f'<tr>'
            f'<td style="padding:4px 8px;color:{sub_text};font-size:9pt;">{lbl}</td>'
            f'<td style="padding:4px 8px;color:{val_color};font-size:9pt;'
            f'text-align:right;font-weight:bold;">{val}</td>'
            f'</tr>'
            for lbl, val in rows
        )
        return (
            f'<div style="background:{sec_bg};border-radius:6px;padding:14px;margin-bottom:16px;">'
            f'<div style="font-size:12pt;font-weight:bold;color:{hdr_color};'
            f'border-bottom:1px solid {border};padding-bottom:6px;margin-bottom:10px;">'
            f'{title}</div>'
            f'<table style="width:100%;border-collapse:collapse;">{rows_html}</table>'
            f'</div>'
        )

    def _generateHtml(self, st, has_photos=False, dark=True):
        def fi(n):  return f"{int(round(n)):,}"
        def ff1(n): return f"{n:,.1f}"
        def ff2(n): return f"{n:,.2f}"
        def fdate(d):
            # Format YYYY-MM-DD as "Mon D, YYYY" (e.g. "Apr 4, 2025")
            try:
                import datetime
                dt = datetime.datetime.strptime(d, "%Y-%m-%d")
                return f"{dt.strftime('%b')} {dt.day}, {dt.strftime('%Y')}"
            except Exception:
                return d

        bg   = "#1e1f26" if dark else "#ffffff"
        text = "#e2e4ec" if dark else "#111111"

        s1 = self._section("Your Totals", [
            ("Species",                   fi(st["total_species"])),
            ("Families",                  fi(st["total_families"])),
            ("Checklists",                fi(st["total_checklists"])),
            ("Dates",                     fi(st["total_days"])),
            ("Sightings",                 fi(st["total_species_records"])),
            ("Individuals",               fi(st["total_individuals"])),
        ], dark)

        s2 = self._section("Traveling Checklists", [
            ("Checklists",                fi(st["proto_traveling"])),
            ("Avg Species",               ff1(st["avg_trav_species"])),
            ("Avg Duration",              ff1(st["avg_trav_duration"]) + " min"),
            ("Avg Distance",              ff1(st["avg_trav_distance"]) + " km"),
            ("Avg Distance",              ff2(st["avg_trav_distance"] * 0.621371) + " miles"),
        ], dark)

        s_regions = self._section("Regions", [
            ("Countries",                 fi(st["total_countries"])),
            ("States / Provinces",        fi(st["total_states"])),
            ("Counties",                  fi(st["total_counties"])),
            ("Locations",                 fi(st["total_locations"])),
        ], dark)

        s3 = self._section("Time in the Field", [
            ("Minutes",                   fi(st["total_minutes"])),
            ("Hours",                     ff1(st["total_hours"])),
            ("Days",                      ff2(st["total_days_time"])),
        ], dark)

        breakdown_rows = [
            ("Traveling",                 fi(st["proto_traveling"])),
            ("Stationary",                fi(st["proto_stationary"])),
            ("Incidental",                fi(st["proto_casual"])),
            ("Historical",                fi(st["proto_historical"])),
        ]
        if st["proto_other"] > 0:
            breakdown_rows.append(("Other Protocols", fi(st["proto_other"])))
        breakdown_rows.append(("Avg Species / Checklist", ff1(st["avg_species_per_checklist"])))
        s4 = self._section("Checklist Breakdown", breakdown_rows, dark)

        s5 = self._section("Stationary Checklists", [
            ("Checklists",                fi(st["proto_stationary"])),
            ("Avg Species",               ff1(st["avg_stat_species"])),
            ("Avg Duration",              ff1(st["avg_stat_duration"]) + " min"),
        ], dark)

        s_incidental = self._section("Incidental Checklists", [
            ("Checklists",                fi(st["proto_casual"])),
            ("Avg Species",               ff1(st["avg_incidental_species"])),
        ], dark)

        s6 = self._section("Distance Covered", [
            ("Kilometers",                ff2(st["total_km"])),
            ("Miles",                     ff2(st["total_miles"])),
        ], dark)

        if has_photos:
            def _sp(name):
                return name if len(name) <= 28 else name[:26] + "\u2026"

            top = st.get("photo_top_species", [])
            top_rows = []
            if top:
                top_rows = [("Most Photographed", "")]
                for sp_name, cnt in top:
                    top_rows.append((f"\u00a0\u00a0- {_sp(sp_name)}", fi(cnt)))

            mn_name = st.get("photo_most_recent_new_species", "")
            mn_date = st.get("photo_most_recent_new_date", "")
            mn_rows = []
            if mn_name:
                mn_rows = [
                    ("Most Recent New Species", ""),
                    (f"\u00a0\u00a0- {_sp(mn_name)}", fdate(mn_date)),
                ]

            s7 = self._section("Your Photos", [
                ("Total Photos",              fi(st["photo_count"])),
                ("Species Photographed",      fi(st["photo_species"])),
                ("Locations with Photos",     fi(st["photo_locations"])),
                ("Checklists with Photos",    fi(st["photo_checklists"])),
                ("Avg Rating (rated photos)", ff1(st["photo_avg_rating"])),
                ("Rated Photos",              fi(st["photo_rated_count"])),
                ("Unrated Photos",            fi(st["photo_unrated_count"])),
            ] + top_rows + mn_rows, dark)

            rec_count = st.get("rec_count", 0)
            if rec_count > 0:
                rec_top = st.get("rec_top_species", [])
                rec_top_rows = []
                if rec_top:
                    rec_top_rows = [("Most Recorded", "")]
                    for sp_name, cnt in rec_top:
                        rec_top_rows.append((f"\u00a0\u00a0- {_sp(sp_name)}", fi(cnt)))

                rec_mn_name = st.get("rec_new_species", "")
                rec_mn_date = st.get("rec_new_date", "")
                rec_mn_rows = []
                if rec_mn_name:
                    rec_mn_rows = [
                        ("Most Recent New Species", ""),
                        (f"\u00a0\u00a0- {_sp(rec_mn_name)}", fdate(rec_mn_date)),
                    ]

                s8 = self._section("Your Recordings", [
                    ("Total Recordings",            fi(st["rec_count"])),
                    ("Species Recorded",            fi(st["rec_species"])),
                    ("Locations with Recordings",   fi(st["rec_locations"])),
                    ("Checklists with Recordings",  fi(st["rec_checklists"])),
                    ("Avg Rating (rated)",          ff1(st["rec_avg_rating"])),
                    ("Rated Recordings",            fi(st["rec_rated_count"])),
                    ("Unrated Recordings",          fi(st["rec_unrated_count"])),
                ] + rec_top_rows + rec_mn_rows, dark)
            else:
                s8 = ""

            col3 = f'<div class="col">{s7}{s8}{{photo_catalog_note}}</div>'
            grid_cols = "1fr 1fr 1.3fr"
        else:
            col3 = ""
            grid_cols = "1fr 1fr"

        note_style = f'font-size:9pt;color:{text};margin-top:auto;margin-bottom:0;text-align:left;'

        taxonomy_year = getattr(self.mdiParent, "taxonomyYear", "")
        taxonomy_note = (
            f'<p style="{note_style}">'
            f'{taxonomy_year} eBird taxonomy. '
            f'If checklists include exotic species, totals may not match eBird totals.</p>'
            if taxonomy_year else ""
        )

        # eBird file info — bottom of col 2
        db = self.mdiParent.db
        def _fmt_dt(dt):
            h = dt.hour % 12 or 12
            period = "AM" if dt.hour < 12 else "PM"
            return dt.strftime(f"%b %d, %Y {h}:%M {period}")

        file_stamp = ""
        try:
            stat = os.stat(db.eBirdFilePath)
            ts = getattr(stat, "st_birthtime", stat.st_mtime)
            file_stamp = _fmt_dt(datetime.datetime.fromtimestamp(ts))
        except OSError:
            pass

        most_recent_date = max(db.dateDict.keys()) if db.dateDict else ""
        sighting_stamp = ""
        if most_recent_date:
            times = [s["time"] for s in db.dateDict[most_recent_date] if s.get("time")]
            latest_hhmm = max(times) if times else ""
            try:
                rdt = datetime.datetime.strptime(most_recent_date, "%Y-%m-%d")
                if latest_hhmm:
                    t = datetime.datetime.strptime(latest_hhmm, "%H:%M")
                    rdt = rdt.replace(hour=t.hour, minute=t.minute)
                sighting_stamp = _fmt_dt(rdt)
            except ValueError:
                sighting_stamp = most_recent_date

        ebird_lines = []
        if file_stamp:
            ebird_lines.append(f"eBird file: {file_stamp}")
        if sighting_stamp:
            ebird_lines.append(f"Latest sighting: {sighting_stamp}")
        ebird_note = (f'<p style="{note_style}">{"<br>".join(ebird_lines)}</p>'
                      if ebird_lines else "")

        # Media catalog last-write date — bottom of col 3
        photo_catalog_note = ""
        if has_photos and db.photoDataFile:
            try:
                pdt = datetime.datetime.fromtimestamp(os.stat(db.photoDataFile).st_mtime)
                catalog_stamp = _fmt_dt(pdt)
                photo_catalog_note = (
                    f'<p style="{note_style}">Media catalog last updated:<br>{catalog_stamp}</p>'
                )
            except OSError:
                pass

        if col3:
            col3 = col3.format(photo_catalog_note=photo_catalog_note)

        # Fixed pixel width for the on-screen (dark) report.  While the Stats
        # window is hidden, Chromium lays the page out with an unreliable
        # viewport (widget sizes/resizes don't reach the renderer), so a fluid
        # layout can be measured in a squeezed, extra-tall state.  With a fixed
        # width matching the webView's final size, the layout — and therefore
        # the height _fitToContent measures — is viewport-independent.  The
        # light (PDF) variant keeps a fluid width for the print engine.
        body_width_css = ""
        if dark:
            try:
                sf = float(self.mdiParent.scaleFactor)
            except (AttributeError, TypeError, ValueError):
                sf = 1.0
            view_w = int((1000 if has_photos else 640) * sf) - 10
            body_width_css = f"width: {view_w - 40}px;"

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
    grid-template-columns: {grid_cols};
    gap: 16px;
  }}
  .col {{ display: flex; flex-direction: column; }}
</style>
</head>
<body>
<div class="grid">
  <div class="col">{s1}{s_regions}{s3}{s6}{taxonomy_note}</div>
  <div class="col">{s4}{s2}{s5}{s_incidental}{ebird_note}</div>
  {col3}
</div>
</body></html>"""


    def html(self):
        """Generate light-theme HTML for PDF output."""
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
            'font-size: 13pt; font-weight: normal; margin-top: 0; margin-bottom: 16px; }\n'
        )

        stats_html = self._generateHtml(self._stats, getattr(self, "_has_photos", False), dark=False)
        stats_html = stats_html.replace("</style>", heading_styles + "</style>", 1)
        stats_html = stats_html.replace("<body>", "<body>" + heading, 1)
        return stats_html
