import form_Stats
import code_Filter

from math import floor

from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QMdiSubWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile


class Stats(QMdiSubWindow, form_Stats.Ui_frmStats):

    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
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
        windowHeight = int(760 * scaleFactor)
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
            self.webView = QWebEngineView(self)
            self.webView.setObjectName("webView")
            self.webView.page().setBackgroundColor(QColor("#1e1f26"))
            QWebEngineProfile.defaultProfile().settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            windowWidth  = self.frameGeometry().width()
            windowHeight = self.frameGeometry().height()
            self.webView.setGeometry(5, 27, windowWidth - 10, windowHeight - 35)

        self.setWindowTitle(filter.buildWindowTitle("Statistics", self.mdiParent.db))
        self.webView.setHtml(self._generateHtml(self._stats, self._has_photos, dark=True))
        return True


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
            photo_family_set   = set()
            photo_order_set    = set()
            photo_checklist_set= set()
            ratings            = []
            camera_count       = {}   # camera -> count
            lens_count         = {}   # lens -> count
            species_photo_count= {}   # commonName -> count
            species_last_date  = {}   # commonName -> most recent photo date (YYYY-MM-DD)

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
                            prev = species_last_date.get(name)
                            if prev is None or date > prev:
                                species_last_date[name] = date
                    photo_location_set.add(s["location"])
                    if s.get("family"):
                        photo_family_set.add(s["family"])
                    if s.get("order"):
                        photo_order_set.add(s["order"])
                    photo_checklist_set.add(s["checklistID"])
                    cam = (p.get("camera") or "").strip()
                    if cam:
                        camera_count[cam] = camera_count.get(cam, 0) + 1
                    lens = (p.get("lens") or "").strip()
                    if lens:
                        lens_count[lens] = lens_count.get(lens, 0) + 1
                    try:
                        r = int(p.get("rating") or 0)
                        if r > 0:
                            ratings.append(r)
                    except (ValueError, TypeError):
                        pass

            avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
            top_species = sorted(species_photo_count.items(),
                                 key=lambda x: x[1], reverse=True)
            top_camera = max(camera_count.items(), key=lambda x: x[1]) if camera_count else ("", 0)
            top_lens   = max(lens_count.items(),   key=lambda x: x[1]) if lens_count   else ("", 0)

            # Most recently photographed: species with the latest last-photo date
            # Longest since photographed: species with the earliest last-photo date
            most_recent_species = ""
            most_recent_date    = ""
            longest_since_species = ""
            longest_since_date    = ""
            if species_last_date:
                mr = max(species_last_date.items(), key=lambda x: x[1])
                most_recent_species, most_recent_date = mr[0], mr[1]
                ls = min(species_last_date.items(), key=lambda x: x[1])
                longest_since_species, longest_since_date = ls[0], ls[1]

            photo_stats = {
                "photo_count":              photo_count,
                "photo_species":            len(photo_species_set),
                "photo_locations":          len(photo_location_set),
                "photo_families":           len(photo_family_set),
                "photo_orders":             len(photo_order_set),
                "photo_checklists":         len(photo_checklist_set),
                "photo_avg_rating":         avg_rating,
                "photo_rated_count":        len(ratings),
                "photo_unrated_count":      photo_count - len(ratings),
                "photo_top_species":        top_species[:3],
                "photo_most_recent_species": most_recent_species,
                "photo_most_recent_date":    most_recent_date,
                "photo_longest_since_species": longest_since_species,
                "photo_longest_since_date":    longest_since_date,
                "photo_top_camera":            top_camera[0],
                "photo_top_camera_count":      top_camera[1],
                "photo_top_lens":              top_lens[0],
                "photo_top_lens_count":        top_lens[1],
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
                return datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%b %-d, %Y")
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
            top = st.get("photo_top_species", [])
            top_rows = [("Most Photographed", "")]
            for sp_name, cnt in top:
                display = sp_name if len(sp_name) <= 28 else sp_name[:26] + "\u2026"
                top_rows.append((f"\u00a0\u00a0- {display}", fi(cnt)))
            def _sp(name):
                return name if len(name) <= 28 else name[:26] + "\u2026"

            mr_name = st.get("photo_most_recent_species", "")
            mr_date = st.get("photo_most_recent_date", "")
            ls_name = st.get("photo_longest_since_species", "")
            ls_date = st.get("photo_longest_since_date", "")

            recency_rows = []
            if mr_name:
                recency_rows += [
                    ("Most Recently Photographed", ""),
                    (f"\u00a0\u00a0- {_sp(mr_name)}", mr_date),
                ]
            if ls_name:
                recency_rows += [
                    ("Longest Since Photographed", ""),
                    (f"\u00a0\u00a0- {_sp(ls_name)}", ls_date),
                ]

            def _trunc(s, n=28):
                return s if len(s) <= n else s[:n - 1] + "\u2026"

            camera_rows = []
            if st.get("photo_top_camera"):
                camera_rows = [
                    ("Most Used Camera", ""),
                    (f"\u00a0\u00a0- {_trunc(st['photo_top_camera'])}", fi(st["photo_top_camera_count"])),
                ]
            lens_rows = []
            if st.get("photo_top_lens"):
                lens_rows = [
                    ("Most Used Lens", ""),
                    (f"\u00a0\u00a0- {_trunc(st['photo_top_lens'])}", fi(st["photo_top_lens_count"])),
                ]

            s7 = self._section("Your Photos", [
                ("Total Photos",              fi(st["photo_count"])),
                ("Species Photographed",      fi(st["photo_species"])),
                ("Families Photographed",     fi(st["photo_families"])),
                ("Orders Photographed",       fi(st["photo_orders"])),
                ("Locations with Photos",     fi(st["photo_locations"])),
                ("Checklists with Photos",    fi(st["photo_checklists"])),
                ("Avg Rating (rated photos)", ff1(st["photo_avg_rating"])),
                ("Rated Photos",              fi(st["photo_rated_count"])),
                ("Unrated Photos",            fi(st["photo_unrated_count"])),
            ] + top_rows + recency_rows + camera_rows + lens_rows, dark)
            col3 = f'<div class="col">{s7}</div>'
            grid_cols = "1fr 1fr 1.3fr"
        else:
            col3 = ""
            grid_cols = "1fr 1fr"

        taxonomy_year = getattr(self.mdiParent, "taxonomyYear", "")
        taxonomy_note = (
            f'<p style="font-size:9pt;color:{text};margin-top:0;margin-bottom:0;text-align:left;">'
            f'{taxonomy_year} eBird taxonomy. '
            f'If checklists include exotic species, totals may not match eBird totals.</p>'
            if taxonomy_year else ""
        )

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{
    background: {bg};
    color: {text};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 20px;
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
  <div class="col">{s4}{s2}{s5}{s_incidental}</div>
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
