# import basic Python libraries
import os
import re
import csv
import json
import zipfile
import io
import sys
from copy import deepcopy
from collections import defaultdict, Counter
import datetime
import code_Filter
import json
import piexif
from math import floor
import wave
from natsort import natsorted

# libsndfile (via soundfile) reads audio-format metadata for ALL formats the app
# supports — 24-bit, 32-bit float (Zoom F3), FLAC, AIFF — where the stdlib `wave`
# module fails.  Guarded so the data layer degrades gracefully if it's missing.
try:
    import soundfile as _sf
except Exception:
    _sf = None

# libsndfile subtype -> friendly bit-depth label shown in the Media Filter.
_BIT_DEPTH_LABELS = {
    "PCM_S8": "8-bit", "PCM_U8": "8-bit",
    "PCM_16": "16-bit", "PCM_24": "24-bit", "PCM_32": "32-bit",
    "FLOAT": "32-bit float", "DOUBLE": "64-bit float",
}
# Display order for the bit-depth multi-select (low fidelity -> high).
_BIT_DEPTH_ORDER = ["8-bit", "16-bit", "24-bit", "32-bit", "32-bit float", "64-bit float"]


def _bit_depth_label(subtype):
    """Friendly bit-depth label for a libsndfile subtype, or '' if unknown."""
    return _BIT_DEPTH_LABELS.get(subtype, "")


def _hz_from_rate_str(s):
    """Parse a sample-rate string ('48000 Hz', '48 kHz', '44.1 kHz') to an int
    number of Hz, or None.  Accepts either the catalog ('… Hz') or combo
    ('… kHz') format so the same matcher handles both."""
    if not s:
        return None
    t = str(s).strip().lower()
    try:
        if "khz" in t:
            return int(round(float(t.replace("khz", "").strip()) * 1000))
        if "hz" in t:
            return int(round(float(t.replace("hz", "").strip())))
        return int(round(float(t)))
    except Exception:
        return None


def _khz_label(hz):
    """Format an Hz int as a kHz combo label ('48 kHz', '44.1 kHz')."""
    return f"{hz / 1000:g} kHz"


def _glean_audio_format(fileName):
    """Return (sampleRate_str, bitDepth_str, channels_str) for an audio file via
    libsndfile.  Handles every format the app supports; empty strings on any
    failure or if soundfile is unavailable."""
    if _sf is None:
        return "", "", ""
    try:
        info = _sf.info(fileName)
        return (f"{info.samplerate} Hz",
                _bit_depth_label(info.subtype),
                "Stereo" if info.channels == 2 else "Mono")
    except Exception:
        return "", "", ""


def _exif_datetime_from_dict(exif_dict):
    """(datetime_str 'YYYY:MM:DD HH:MM:SS' | None, subsec_str | None, bad_flag).

    Mirrors code_RenameMedia._readExifDatetime but operates on an already-loaded
    piexif dict, so a caller that has read EXIF (e.g. getPhotoData) can capture
    the photo's exact shooting time without a second file read.  bad_flag is True
    when EXIF was present but the date was invalid or undecodable.
    """
    try:
        dt_raw = exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
    except Exception:
        return None, None, False
    if dt_raw is None:
        return None, None, False
    try:
        dt_str = dt_raw.decode("utf-8")
    except Exception:
        return None, None, True
    try:
        if len(dt_str) < 19:
            raise ValueError
        year = int(dt_str[0:4]); month = int(dt_str[5:7]); day = int(dt_str[8:10])
        hour = int(dt_str[11:13]); minute = int(dt_str[14:16])
        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23
                and 0 <= minute <= 59 and year > 0):
            raise ValueError
    except (ValueError, IndexError):
        return None, None, True
    sub_raw = exif_dict.get("Exif", {}).get(piexif.ExifIFD.SubSecTimeOriginal)
    sub_str = None
    if sub_raw is not None:
        try:
            sub_str = sub_raw.decode("utf-8").strip("\x00").strip()
        except Exception:
            pass
    return dt_str, sub_str, False


def _photo_exif_fields(p):
    """Optional catalog fields carrying a photo's cached EXIF capture time.

    Emitted only when the value is known (the ``exifDatetime`` key is present),
    so legacy records that were never gleaned stay un-cached and are read on
    demand the first time Rename Media needs them."""
    if "exifDatetime" not in p:
        return {}
    return {
        "ExifDateTime":    p.get("exifDatetime") or "",
        "ExifSubSec":      p.get("exifSubsec") or "",
        "ExifDateInvalid": bool(p.get("exifDateInvalid")),
    }


def _recording_meta_fields(a):
    """Optional catalog fields carrying a recording's cached embedded date/time."""
    if "metaDate" not in a:
        return {}
    return {
        "MetaDate": a.get("metaDate") or "",
        "MetaTime": a.get("metaTime") or "",
    }


from PySide6.QtWidgets import (
    QApplication,
    QMessageBox
    )


# Module-level constants shared across methods
_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def _hhmm_to_minutes(t):
    """Parse an 'HH:MM' time string to minutes since midnight, or None when the
    value is blank or malformed (e.g. a checklist with no recorded start time)."""
    try:
        return 60 * int(t[0:2]) + int(t[3:5])
    except (ValueError, IndexError, TypeError):
        return None


def _checklist_distance(c, photo_minutes):
    """Return minutes between photo_minutes and the nearest edge of checklist c.

    Returns 0 if the photo was taken during the checklist (i.e. within the
    window [start, start+duration]).  c is a GetChecklists() row where
    c[5] = start time "HH:MM" and c[7] = duration (str, int, or empty/None).
    Checklists without a usable start time sort last.
    """
    start = _hhmm_to_minutes(c[5])
    if start is None:
        return float('inf')
    dur   = int(c[7]) if c[7] else 0
    end   = start + dur
    if start <= photo_minutes <= end:
        return 0
    return min(abs(photo_minutes - start), abs(photo_minutes - end))


def _longest_substr_in(needle, haystack, min_len=4):
    """Return the length of the longest substring of needle found in haystack.

    For each start position i, tries the longest possible remaining substring
    first and breaks as soon as a match is found — O(n²) in the worst case but
    fast in practice because species names are short and early exits are common.
    Returns 0 when no substring of length >= min_len exists in haystack.
    """
    n = len(needle)
    best = 0
    for i in range(n):
        if n - i <= best:       # remaining tail can't beat current best
            break
        for j in range(n, i + min_len - 1, -1):
            length = j - i
            if length <= best:  # this slice can't improve score; move to next i
                break
            if needle[i:j] in haystack:
                best = length
                break           # found longest match starting at i
    return best


#routine to open helper files (json, csv, etc.) in fashion compatible with PyInstaller for when code is bundled into an app.
def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return filename


def _safe_rating(val, default=0):
    """Return val as an int in 0-5, or default if val is missing/invalid."""
    try:
        r = int(val)
        return r if 0 <= r <= 5 else default
    except (TypeError, ValueError):
        return default


def _read_wav_metadata_datetime(filepath):
    """Extract recording date/time from WAV file metadata.

    Walks the RIFF structure manually to read all relevant chunk types, then
    falls back to a prepended-ID3 scan for files written by tools like mutagen.

    Priority: BWF bext > embedded id3 chunk > RIFF INFO TITL > ICMT > ICRD > prepended ID3

    Returns (date_str 'YYYY-MM-DD', time_str 'HH:MM') or ('', '').
    """
    import struct as _struct

    def _parse_date(s):
        # Accept -, ., / or : as separators (BWF OriginationDate is usually
        # YYYY-MM-DD but some recorders write YYYY:MM:DD).
        m = re.match(r'(20\d\d)[-./:](0[1-9]|1[0-2])[-./:](0[1-9]|[12]\d|3[01])',
                     (s or '').strip())
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else ''

    def _parse_time(s):
        m = re.match(r'([01]\d|2[0-3])[:.h]([0-5]\d)', (s or '').strip())
        return f'{m.group(1)}:{m.group(2)}' if m else ''

    def _id3_datetime(tags):
        """Pull date/time from a mutagen ID3Tags-like object."""
        try:
            frame = tags.get('TDRC')
            if frame:
                ts = str(frame.text[0]) if hasattr(frame, 'text') else str(frame)
                d = _parse_date(ts[:10])
                if d:
                    return d, (_parse_time(ts[11:16]) if len(ts) >= 16 else '')
        except Exception:
            pass
        try:
            frame = tags.get('TIT2')
            if frame:
                title = str(frame.text[0]) if hasattr(frame, 'text') else str(frame)
                m2 = re.match(r'(20\d\d-\d\d-\d\d)[ T](\d\d[.:]\d\d)', title.strip())
                if m2:
                    d = _parse_date(m2.group(1))
                    if d:
                        return d, _parse_time(m2.group(2))
        except Exception:
            pass
        try:
            for key in list(tags.keys()):
                if key.startswith('COMM'):
                    frame = tags[key]
                    text = str(frame.text[0]) if hasattr(frame, 'text') else str(frame)
                    dm = re.search(r'Date[:\s]+(\d{4}-\d{2}-\d{2})', text)
                    tm_m = re.search(r'Time[:\s]+(\d{2})[:\.](\d{2})', text)
                    if dm:
                        d = _parse_date(dm.group(1))
                        if d:
                            return d, (f'{tm_m.group(1)}:{tm_m.group(2)}' if tm_m else '')
        except Exception:
            pass
        return None

    try:
        with open(filepath, 'rb') as fh:
            header = fh.read(12)
            if len(header) < 12:
                return '', ''

            # ── Files with a prepended ID3 header (not standard, but mutagen can write these)
            if header[:3] == b'ID3':
                try:
                    from mutagen.id3 import ID3
                    r = _id3_datetime(ID3(filepath))
                    return r if r else ('', '')
                except Exception:
                    return '', ''

            if header[:4] != b'RIFF' or header[8:12] != b'WAVE':
                return '', ''

            bext_result = id3_result = titl_result = icmt_result = icrd_result = None

            pos = 12
            while True:
                fh.seek(pos)
                chunk_hdr = fh.read(8)
                if len(chunk_hdr) < 8:
                    break
                cid = chunk_hdr[:4]
                csz = _struct.unpack_from('<I', chunk_hdr, 4)[0]
                data_pos = pos + 8

                # ── BWF bext ─────────────────────────────────────────────────
                # Per EBU Tech 3285, the 'bext' chunk layout is:
                #   Description 0-255, Originator 256-287, OriginatorReference
                #   288-319, OriginationDate 320-329 (10 bytes, YYYY-MM-DD),
                #   OriginationTime 330-337 (8 bytes, HH:MM:SS).
                if cid == b'bext' and csz >= 338 and not bext_result:
                    fh.seek(data_pos)
                    data = fh.read(min(csz, 512))
                    orig_date = data[320:330].split(b'\x00')[0].decode('ascii', 'replace').strip()
                    orig_time = data[330:338].split(b'\x00')[0].decode('ascii', 'replace').strip()
                    d = _parse_date(orig_date)
                    if d:
                        bext_result = (d, _parse_time(orig_time[:5]))

                # ── Embedded ID3 chunk ('id3 ' or 'ID3 ') ────────────────────
                # Standard location for ID3 inside RIFF/WAVE (RFC 2361 / BWF extension).
                elif cid in (b'id3 ', b'ID3 ') and not id3_result:
                    try:
                        import io as _io
                        from mutagen.id3 import ID3
                        fh.seek(data_pos)
                        r = _id3_datetime(ID3(fileobj=_io.BytesIO(fh.read(csz))))
                        if r:
                            id3_result = r
                    except Exception:
                        pass

                # ── RIFF INFO LIST chunk ──────────────────────────────────────
                # Consumer apps (including Shure MOTIV) write INFO sub-chunks:
                # TITL "YYYY-MM-DD HH.MM.SS", ICMT/CMNT with Date:/Time: fields,
                # ICRD with a date string.
                elif cid == b'LIST':
                    fh.seek(data_pos)
                    list_type = fh.read(4)
                    if list_type == b'INFO':
                        sub_pos = data_pos + 4
                        sub_end = data_pos + csz
                        while sub_pos + 8 <= sub_end:
                            fh.seek(sub_pos)
                            sh = fh.read(8)
                            if len(sh) < 8:
                                break
                            sid = sh[:4]
                            ssz = _struct.unpack_from('<I', sh, 4)[0]
                            fh.seek(sub_pos + 8)
                            val = fh.read(ssz).split(b'\x00')[0].decode('latin-1', 'replace').strip()
                            if sid in (b'TITL', b'INAM') and not titl_result:
                                m2 = re.match(r'(20\d\d-\d\d-\d\d)[ T](\d\d[.:]\d\d)', val)
                                if m2:
                                    d = _parse_date(m2.group(1))
                                    if d:
                                        titl_result = (d, _parse_time(m2.group(2)))
                            elif sid in (b'ICMT', b'CMNT') and not icmt_result:
                                dm = re.search(r'Date[:\s]+(\d{4}-\d{2}-\d{2})', val)
                                tm_m = re.search(r'Time[:\s]+(\d{2})[:\.](\d{2})', val)
                                if dm:
                                    d = _parse_date(dm.group(1))
                                    if d:
                                        icmt_result = (d, f'{tm_m.group(1)}:{tm_m.group(2)}' if tm_m else '')
                            elif sid == b'ICRD' and not icrd_result:
                                d = _parse_date(val)
                                if d:
                                    icrd_result = (d, _parse_time(val[11:16]) if len(val) >= 16 else '')
                            sub_pos += 8 + ssz + (ssz % 2)

                pos += 8 + csz + (csz % 2)  # RIFF chunks are word-aligned

    except Exception:
        return '', ''

    result = bext_result or id3_result or titl_result or icmt_result or icrd_result
    return result if result else ('', '')


def _read_wav_device(filepath):
    """Return the recording device/model from WAV metadata, or ''.

    Priority: BWF 'bext' Originator (field recorders, e.g. 'ZOOM F3') > a
    'Recorded with <device>' phrase in a RIFF INFO comment (e.g. the Shure MOTIV
    app writes 'Recorded with Shure MV88.').  Files with no metadata return ''.
    """
    import struct as _struct
    try:
        with open(filepath, 'rb') as fh:
            header = fh.read(12)
            if len(header) < 12 or header[:4] != b'RIFF' or header[8:12] != b'WAVE':
                return ''
            originator = ''
            comment = ''
            pos = 12
            while True:
                fh.seek(pos)
                chunk_hdr = fh.read(8)
                if len(chunk_hdr) < 8:
                    break
                cid = chunk_hdr[:4]
                csz = _struct.unpack_from('<I', chunk_hdr, 4)[0]
                data_pos = pos + 8
                if cid == b'bext' and csz >= 288 and not originator:
                    fh.seek(data_pos)
                    data = fh.read(min(csz, 288))
                    originator = data[256:288].split(b'\x00')[0].decode('latin-1', 'replace').strip()
                elif cid == b'LIST':
                    fh.seek(data_pos)
                    if fh.read(4) == b'INFO' and not comment:
                        sub_pos = data_pos + 4
                        sub_end = data_pos + csz
                        while sub_pos + 8 <= sub_end:
                            fh.seek(sub_pos)
                            sh = fh.read(8)
                            if len(sh) < 8:
                                break
                            sid = sh[:4]
                            ssz = _struct.unpack_from('<I', sh, 4)[0]
                            if sid in (b'ICMT', b'CMNT', b'COMM'):
                                fh.seek(sub_pos + 8)
                                comment = fh.read(ssz).split(b'\x00')[0].decode('latin-1', 'replace')
                                break
                            sub_pos += 8 + ssz + (ssz % 2)
                pos += 8 + csz + (csz % 2)
            if originator:
                return originator
            if comment:
                m = re.search(r'[Rr]ecorded with\s+(.+?)\s*[.\n]', comment)
                if m:
                    return m.group(1).strip()
    except Exception:
        return ''
    return ''


class DataBase():

    # this is the class that will store all our data and the data-seeking logic 
    
    def __init__(self):
        self.allSpeciesList = []
        self.familyList = []
        self.orderList = []
        self.masterFamilyOrderList = []
        self.masterLocationList = []
        self.regionList = []
        self.countryList = []
        self.stateList = []
        self.countyList = []
        self.locationList = []
        self.validPhotoSpecies = []
        self.cameraList = []
        self.lensList = []
        self.shutterSpeedList = []
        self.apertureList = []
        self.focalLengthList=[]
        self.isoList = []
        self.durationList = []
        self.sampleRateList = []
        self.bitDepthList = []
        self.deviceList = []
        self.sightingList = []
        self.eBirdFileOpenFlag = False
        self.eBirdFilePath = ""
        self.photoDataFileOpenFlag = False
        self.photosNeedSaving = False
        self.countryStateCodeFileFound = False
        self.speciesDict = {}
        self.yearDict = {}
        self.monthDict = {}
        self.dateDict = {}
        self.countryDict = {}
        self.stateDict = {}
        self.countyDict = {}
        self.locationDict = {}
        self.locationIDDict = {}  # location name -> eBird location ID (e.g. "L2222695")
        self.checklistDict = {}
        self.orderDict = {}
        self.familyDict = {}
        self.familySpeciesDict = {}
        self.orderSpeciesDict = {}
        self.bblCodeDict = {}
        self.eBirdCodeDict = {}       # sciName -> eBird species code, populated by ReadTaxonomyDataFile
        self.taxonOrderBySciName = {} # sciName -> float taxon order, populated by ReadTaxonomyDataFile
        self._regionCache = {}
        self._seenLocations = set()
        self.photoDataFile = ""
        self.photoDataFileDefault = ""
        self.jsonlSkippedLines = 0
        self.csvSkippedRows = 0
        self.photoRecordsInCatalog = 0
        self.startupFolder = ""
        self.ebirdApiKey = ""
        self.myCounty = ""
        self.myPatch = ""
        # hex(QAudioDevice.id()) -> {"ms": int, "name": str} — calibrated
        # output-latency compensation per playback device (Preferences tab)
        self.audioLatencyByDevice = {}
        self._countryLookup = {}   # shortCode -> longName, built by ReadCountryStateCodeFile
        self._stateLookup = {}     # shortCode -> longName, built by ReadCountryStateCodeFile
        self.monthNameDict = ({
            "01":"Jan",
            "02":"Feb",
            "03":"Mar",
            "04":"Apr",
            "05":"May",
            "06":"Jun",
            "07":"Jul",
            "08":"Aug",
            "09":"Sep",
            "10":"Oct",
            "11":"Nov",
            "12":"Dec"
            })
        self.monthNumberDict = ({
            "Jan":"01",
            "Feb":"02",
            "Mar":"03",
            "Apr":"04",
            "May":"05",
            "Jun":"06",
            "Jul":"07",
            "Aug":"08",
            "Sep":"09",
            "Oct":"10",
            "Nov":"11",
            "Dec":"12"
            })            
        self.regionNameDict = ({
            "ABA":"ABA Area",
            "AOU":"AOU Area",
            "NAM":"North America",
            "SAM":"South America",
            "AFR":"Africa",
            "EUR":"Europe",
            "ASI":"Asia",
            "SPO":"South Polar",
            "WHE":"Western Hemisphere",
            "EHE":"Eastern Hemisphere",
            "WIN":"West Indies",
            "CAM":"Central America",
            "USL":"USA Lower 48",
            "AUA":"Australasia (ABA)",
            "AUE":"Australasia (eBird)",
            "AUS":"Australia and Territories"
            }) 
        self.regionCodeDict = ({
            "ABA Area":"ABA",
            "AOU Area":"AOU",
            "North America":"NAM",
            "South America":"SAM",
            "Africa":"AFR",
            "Europe":"EUR",
            "Asia":"ASI",
            "South Polar":"SPO",
            "Western Hemisphere":"WHE",
            "Eastern Hemisphere":"EHE",
            "West Indies":"WIN",
            "Central America":"CAM",
            "USA Lower 48":"USL",
            "Australasia (ABA)":"AUA",
            "Australasia (eBird)":"AUE",
            "Australia and Territories":"AUS"
            }) 

        # Use resource_path helper routine (in module, below) to open files in way safe for PyInstaller app bundle
        # Load JSON files using resource_path
        stateJsonFile   = resource_path("us-states.json")
        countyJsonFile  = resource_path("us-counties-lower48.json")
        countryJsonFile = resource_path("world-countries.json")
        caProvJsonFile  = resource_path("ca-provinces.json")
        inStatesJsonFile = resource_path("in-states.json")
        gbCountiesJsonFile = resource_path("gb-counties.json")
        
        # load us-states json shape file for later use with choropleths
        with open(stateJsonFile, encoding='utf-8') as f:
            self.state_geo = json.loads(f.read())

        # load us-counties-lower48 json shape file for later use with choropleths
        with open(countyJsonFile, encoding='utf-8') as f:
            self.county_geo = json.loads(f.read())
        
        # save county code data for easy lookup when processing eBird data file
        self.countyCodeDict = {}
        self.countyCodeList = set()
        self._countyFipsLookup = {}  # (countyName, stateAbbr) -> FIPS code
        for c in self.county_geo["features"]:

            # save master list of all US county codes for use with choropleths
            self.countyCodeList.add(c["id"])

            name = c["properties"]["name"]
            fips = c["id"]
            state_abbr = c["properties"]["state"]
            if name not in self.countyCodeDict:
                self.countyCodeDict[name] = [[fips, state_abbr]]
            else:
                self.countyCodeDict[name].append([fips, state_abbr])
            self._countyFipsLookup[(name, state_abbr)] = fips
        
        # load world-countries json shape file for later use with choropleths
        with open(countryJsonFile, encoding='utf-8') as f:
            self.country_geo = json.loads(f.read())

        # load ca-provinces json shape file for later use with choropleths
        with open(caProvJsonFile, encoding='utf-8') as f:
            self.ca_province_geo = json.loads(f.read())

        # load in-states json shape file for later use with choropleths
        with open(inStatesJsonFile, encoding='utf-8') as f:
            self.in_state_geo = json.loads(f.read())

        # load gb-counties json shape file for later use with choropleths
        with open(gbCountiesJsonFile, encoding='utf-8') as f:
            self.gb_county_geo = json.loads(f.read())
        

    def matchPhoto(self, file, exif_dict=None):

        # method to suggest a commonName, date, time, and location for a photo

        # get just the filename portion from the full-path filename
        fileName = os.path.basename(file)

        # use provided exif_dict (pre-loaded by caller) or load from file
        if exif_dict is None:
            try:
                photoExif = piexif.load(file)
            except:
                photoExif = {}
        else:
            photoExif = exif_dict
        
        # get photo date from EXIF
        try:
            photoDateTime = photoExif["Exif"][piexif.ExifIFD.DateTimeOriginal].decode("utf-8")

            # parse EXIF data for date/time components
            photoDate = photoDateTime[0:4] + "-" + photoDateTime[5:7] + "-" + photoDateTime[8:10]
            photoTime = photoDateTime[11:13] + ":" + photoDateTime[14:16]
        except:
            photoDate = ""
            photoTime = ""

        # preserve the raw EXIF time before any resolution; used by the AM/PM fallback below
        exifPhotoTime = photoTime

        # check whether the EXIF date/time match any checklist (for UI warnings)
        dateMatchFound = False
        timeMatchFound = False
        if photoDate != "":
            _df = code_Filter.Filter()
            _df.setStartDate(photoDate)
            _df.setEndDate(photoDate)
            dateMatchFound = len(self.GetLocations(_df, "OnlyLocations")) > 0
            if dateMatchFound and photoTime != "":
                _tf = code_Filter.Filter()
                _tf.setStartDate(photoDate)
                _tf.setEndDate(photoDate)
                _tf.setTime(photoTime)
                timeMatchFound = len(self.GetLocations(_tf, "OnlyLocations")) > 0
            elif dateMatchFound:
                timeMatchFound = True

        # use date and time to select a sighting location from db
        filter = code_Filter.Filter()
        filter.setStartDate(photoDate)
        filter.setEndDate(photoDate)
        filter.setTime(photoTime)
        locations = self.GetLocations(filter, "OnlyLocations")
        
        # if we find only one location, return it
        if len(locations) == 1:
            photoLocation = locations[0]
            # Resolve photoTime from the EXIF time to the actual checklist start time.
            # The EXIF time may fall within a checklist's active window without matching its
            # start time exactly, which would cause the time combo box to default to the
            # first (wrong) checklist.  Find the start time closest to the photo's EXIF time
            # among all checklists that were active at the photo time.
            if photoTime != "":
                filterWithLocation = code_Filter.Filter()
                filterWithLocation.setStartDate(photoDate)
                filterWithLocation.setEndDate(photoDate)
                filterWithLocation.setLocationName(photoLocation)
                filterWithLocation.setLocationType("Location")
                filterWithLocation.setTime(photoTime)
                startTimes = self.GetStartTimes(filterWithLocation)
                if startTimes:
                    photoMinutes = 60 * int(photoTime[0:2]) + int(photoTime[3:5])
                    _valid = [t for t in startTimes if _hhmm_to_minutes(t) is not None]
                    if _valid:
                        photoTime = min(_valid, key=lambda t: abs(_hhmm_to_minutes(t) - photoMinutes))

        else:
            photoLocation = ""

        # if no single location matched the photo, but we have a date, find which checklist is closest to the photo datetime
        if photoLocation == "" and photoDate != "":
            # try finding a checklist with the right date
            filter = code_Filter.Filter()
            filter.setStartDate(photoDate)
            filter.setEndDate(photoDate)
            locations = self.GetLocations(filter, "OnlyLocations")

            if len(locations) == 1:
                photoLocation = locations[0]
                if photoTime != "":
                    # Pick the checklist whose window [start, start+duration] is closest
                    # to the photo time; distance = 0 when the photo falls inside the window.
                    checklists = self.GetChecklists(filter)
                    if checklists:
                        photoMinutes = 60 * int(photoTime[0:2]) + int(photoTime[3:5])
                        photoTime = min(checklists,
                                        key=lambda c: _checklist_distance(c, photoMinutes))[5]
                else:
                    possibleStartTimes = self.GetStartTimes(filter)
                    if possibleStartTimes:
                        photoTime = possibleStartTimes[0]
            
            # if more than one location was found, find which was visited closest to the photo time
            elif len(locations) > 1 and photoTime != "":
                filter = code_Filter.Filter()
                filter.setStartDate(photoDate)
                filter.setEndDate(photoDate)
                checklists = self.GetChecklists(filter)
                if checklists:
                    photoMinutesSinceMidnight = 60 * int(photoTime[0:2]) + int(photoTime[3:5])
                    best = min(checklists,
                               key=lambda c: _checklist_distance(c, photoMinutesSinceMidnight))
                    photoLocation = best[3]
                    photoTime     = best[5]

        # AM/PM fallback: if a date matched but no checklist window covers the photo's EXIF
        # time, the camera clock may be 12 hours off — retry with the time toggled by 12 hours
        if dateMatchFound and not timeMatchFound and exifPhotoTime != "":
            toggledHour = (int(exifPhotoTime[0:2]) + 12) % 24
            toggledTime = f"{toggledHour:02d}:{exifPhotoTime[3:5]}"

            filter = code_Filter.Filter()
            filter.setStartDate(photoDate)
            filter.setEndDate(photoDate)
            filter.setTime(toggledTime)
            toggledLocations = self.GetLocations(filter, "OnlyLocations")

            if len(toggledLocations) == 1:
                photoLocation = toggledLocations[0]
                photoTime = toggledTime
                filterWithLocation = code_Filter.Filter()
                filterWithLocation.setStartDate(photoDate)
                filterWithLocation.setEndDate(photoDate)
                filterWithLocation.setLocationName(photoLocation)
                filterWithLocation.setLocationType("Location")
                filterWithLocation.setTime(toggledTime)
                startTimes = self.GetStartTimes(filterWithLocation)
                if startTimes:
                    toggledMinutes = 60 * toggledHour + int(toggledTime[3:5])
                    _valid = [t for t in startTimes if _hhmm_to_minutes(t) is not None]
                    if _valid:
                        photoTime = min(_valid, key=lambda t: abs(_hhmm_to_minutes(t) - toggledMinutes))
            elif len(toggledLocations) > 1:
                filter = code_Filter.Filter()
                filter.setStartDate(photoDate)
                filter.setEndDate(photoDate)
                checklists = self.GetChecklists(filter)
                if checklists:
                    toggledMinutes = 60 * toggledHour + int(toggledTime[3:5])
                    best = min(checklists, key=lambda c: _checklist_distance(c, toggledMinutes))
                    photoLocation = best[3]
                    photoTime = best[5]

        # try to use file name to match commonName using date, time, and location found already
        if photoLocation != "" and photoDate != "" and photoTime != "":
            filter = code_Filter.Filter()
            filter.setLocationType("Location")
            filter.setLocationName(photoLocation)
            filter.setStartDate(photoDate)
            filter.setEndDate(photoDate)
            filter.setTime(photoTime)
            possibleCommonNames = self.GetSpecies(filter)

            fileNameLower = os.path.splitext(str(fileName))[0].lower()
            # Alpha-only string for common/scientific name substring matching.
            filename_alpha = re.sub(r'[^a-z]', '', fileNameLower)
            # Alphanumeric string for eBird/BBL code matching (codes can contain digits).
            filename_alnum = re.sub(r'[^a-z0-9]', '', fileNameLower)

            # Score each candidate species against the filename.  For each species
            # we check four name forms and keep the longest match found across all:
            #   • eBird species code  (e.g. "gretit1") — exact substring in alnum filename
            #   • BBL banding code    (e.g. "grti")    — exact substring in alnum filename
            #   • Common name (alpha) (e.g. "greattit") — longest substr in alpha filename
            #   • Scientific name (alpha)               — longest substr in alpha filename
            # The species with the highest score (longest match, min 4 chars) wins.
            photoCommonName = ""
            best_score = 0

            for pcn in possibleCommonNames:
                score = 0

                ebird = self.GeteBirdCode(pcn).lower()
                if ebird and ebird in filename_alnum:
                    score = max(score, len(ebird))

                bbl = self.GetBBLCode(pcn).lower()
                if bbl and bbl in filename_alnum:
                    score = max(score, len(bbl))

                common_clean = re.sub(r'[^a-z]', '', pcn.lower())
                if common_clean:
                    score = max(score, _longest_substr_in(common_clean, filename_alpha))

                sci = self.GetScientificName(pcn)
                if sci:
                    sci_clean = re.sub(r'[^a-z]', '', sci.lower())
                    if sci_clean:
                        score = max(score, _longest_substr_in(sci_clean, filename_alpha))

                if score > best_score:
                    best_score = score
                    photoCommonName = pcn

            if best_score < 4:
                photoCommonName = ""

        else:
            photoCommonName = ""
        
        photoMatchData = {}
        photoMatchData["photoLocation"] = photoLocation
        photoMatchData["photoDate"] = photoDate
        photoMatchData["photoTime"] = photoTime
        photoMatchData["photoCommonName"] = photoCommonName
        photoMatchData["dateMatchFound"] = dateMatchFound
        photoMatchData["timeMatchFound"] = timeMatchFound

        return(photoMatchData)


    def removeUnfoundPhotos(self):

        count = 0
        
        # method to remove photos from database
        # create filter with no settings to retrieve every photo in db
        filter = code_Filter.Filter()
        
        # get all sightings with photos
        sightings = self.GetSightingsWithPhotos(filter)

        for s in sightings:
            for p in s["photos"]:
                if not os.path.isfile(p):
                    s["photos"].remove(p)
                    count += 1

        # return the number of removed files
        return(count)
    

    def removePhotoFromDatabase(self, location, date, time, commonName, photoFileName):

        # method to remove photos from database
        filter = code_Filter.Filter()
        filter.setLocationType("Location")
        filter.setLocationName(location)
        if date != "":
            filter.setStartDate(date)
            filter.setEndDate(date)
        if time != "":
            filter.setTime(time)
        filter.setSpeciesName(commonName)
        
        # get sightings that match the filter. Should only be a single sighting.
        sightings = self.GetSightingsWithPhotos(filter)

        for s in sightings:
            if "photos" in s:
                for p in s["photos"]:
                    if os.path.normcase(p["fileName"]) == os.path.normcase(photoFileName):
                        s["photos"].remove(p)

            # if we've removed all the photos for this sighting, we need to remove the "photos" entry in the dict
            if len(s["photos"]) == 0:
                s.pop("photos", None)
                

    def getPhotoData(self, fileName, exif_dict=None):

        photoData = {}

        # use provided exif_dict (pre-loaded by caller) or load from file
        if exif_dict is None:
            try:
                exif_dict = piexif.load(fileName)
            except:
                exif_dict = {}
             
        try:
            photoCamera = exif_dict["0th"][piexif.ImageIFD.Model].decode("utf-8")
        except:
            photoCamera = ""
        try:
            photoLens = exif_dict["Exif"][piexif.ExifIFD.LensModel].decode("utf-8")
        except:
            photoLens = ""
        try:        
            shutterSpeedFraction = exif_dict["Exif"][piexif.ExifIFD.ExposureTime]
            photoShutterSpeed = floor(shutterSpeedFraction[1]/shutterSpeedFraction[0])
            photoShutterSpeed = "1/" + str(photoShutterSpeed)
        except:
            photoShutterSpeed = ""
        try:
            photoAperture = exif_dict["Exif"][piexif.ExifIFD.FNumber]
            photoAperture = round(photoAperture[0] / photoAperture[1], 1)
        except:
            photoAperture = ""                    
        try:
            photoISO = exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings]
        except:
            photoISO = ""                
        try:
            photoFocalLength = exif_dict["Exif"][piexif.ExifIFD.FocalLength]
            photoFocalLength = floor(photoFocalLength[0] / photoFocalLength[1])
            photoFocalLength = str(photoFocalLength) + " mm"                    
        except:
            photoFocalLength = ""  
        
        # get photo date from EXIF
        try:
            photoDateTime = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode("utf-8")
            
            #parse EXIF data for date/time components
            photoExifDate = photoDateTime[0:4] + "-" + photoDateTime[5:7] + "-" + photoDateTime[8:10]
            photoExifTime = photoDateTime[11:13] + ":" + photoDateTime[14:16]
        except:
            photoExifDate = "Date unknown"
            photoExifTime = "Time unknown"
        
        # Exact shooting time for Rename Media — extracted from the EXIF already
        # loaded above, so it is cached in the catalog and never re-read per file.
        exif_dt, exif_sub, exif_bad = _exif_datetime_from_dict(exif_dict)

        photoData["fileName"] = fileName
        photoData["camera"] = photoCamera
        photoData["lens"] = photoLens
        photoData["shutterSpeed"] = str(photoShutterSpeed)
        photoData["aperture"] = str(photoAperture)
        photoData["iso"] = str(photoISO)
        photoData["focalLength"] = str(photoFocalLength)
        photoData["time"] = photoExifTime
        photoData["date"] = photoExifDate
        photoData["rating"] = "0"
        photoData["exifDatetime"] = exif_dt
        photoData["exifSubsec"] = exif_sub
        photoData["exifDateInvalid"] = exif_bad

        return(photoData)


    def getComboDataForPhoto(self, photoMatchData, allDates=None):
        """Pre-compute all combo box data for a photo so worker threads can do
        this work in parallel rather than blocking the main thread.

        allDates (the unfiltered date list for the date combo) is identical for
        every photo and scans the whole database to build — callers processing
        many photos should compute it once and pass it in."""

        photoDate = photoMatchData["photoDate"]
        photoLocation = photoMatchData["photoLocation"]
        photoTime = photoMatchData["photoTime"]

        # all dates in db (for the date combo box)
        if allDates is None:
            allDates = self.GetDates(code_Filter.Filter())

        # locations visited on the matched date
        locationsByDate = []
        if photoDate:
            f = code_Filter.Filter()
            f.setStartDate(photoDate)
            f.setEndDate(photoDate)
            locationsByDate = self.GetLocations(f)

        # start times for the matched date + location
        timesByDateAndLocation = []
        if photoDate and photoLocation:
            f = code_Filter.Filter()
            f.setStartDate(photoDate)
            f.setEndDate(photoDate)
            f.setLocationName(photoLocation)
            f.setLocationType("Location")
            timesByDateAndLocation = self.GetStartTimes(f)

        # species on the matched checklist
        speciesByChecklist = []
        if photoDate and photoLocation and photoTime:
            f = code_Filter.Filter()
            f.setLocationType("Location")
            f.setLocationName(photoLocation)
            f.setStartDate(photoDate)
            f.setEndDate(photoDate)
            f.setTime(photoTime)
            speciesByChecklist = self.GetSpecies(f)

        return {
            "allDates": allDates,
            "locationsByDate": locationsByDate,
            "timesByDateAndLocation": timesByDateAndLocation,
            "speciesByChecklist": speciesByChecklist,
        }


    # ------------------------------------------------------------------
    # Audio: filename date parsing, metadata, checklist matching, combo data
    # ------------------------------------------------------------------

    def _parseDateTimeFromFilename(self, filepath):
        """Try to parse a recording date/time from the filename.
        Returns (date_str 'YYYY-MM-DD', time_str 'HH:MM') or ('', '')."""
        name = os.path.splitext(os.path.basename(filepath))[0]
        S = r'[^0-9]?'
        year_p = r'(20\d\d)'
        mon_p  = r'(0[1-9]|1[0-2])'
        day_p  = r'(0[1-9]|[12]\d|3[01])'
        hr_p   = r'([01]\d|2[0-3])'
        min_p  = r'([0-5]\d)'

        # YYYY[sep]MM[sep]DD optionally followed by [sep]HH[sep]MM
        m = re.search(
            year_p + S + mon_p + S + day_p +
            r'(?:' + S + hr_p + S + min_p + r')?',
            name,
        )
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            h, mi = m.group(4), m.group(5)
            return f"{y}-{mo}-{d}", (f"{h}:{mi}" if h and mi else "")

        # MM[sep]DD[sep]YYYY optionally followed by [sep]HH[sep]MM
        m = re.search(
            mon_p + S + day_p + S + year_p +
            r'(?:' + S + hr_p + S + min_p + r')?',
            name,
        )
        if m:
            mo, d, y = m.group(1), m.group(2), m.group(3)
            h, mi = m.group(4), m.group(5)
            return f"{y}-{mo}-{d}", (f"{h}:{mi}" if h and mi else "")

        # Fall back to a 2-digit year: YY[sep]MM[sep]DD optionally followed by
        # [sep]HH[sep]MM — e.g. the Zoom F3's 260702_007 → 2026-07-02.  Only
        # reached when no 4-digit-year date matched, so YYYYMMDD is preferred.
        # The lookbehind stops YY from being grabbed out of the middle of a
        # longer digit run; a 2-digit year is assumed to be 20YY.
        yy_p = r'(\d\d)'
        m = re.search(
            r'(?<!\d)' + yy_p + S + mon_p + S + day_p +
            r'(?:' + S + hr_p + S + min_p + r')?',
            name,
        )
        if m:
            yy, mo, d = m.group(1), m.group(2), m.group(3)
            h, mi = m.group(4), m.group(5)
            return f"20{yy}-{mo}-{d}", (f"{h}:{mi}" if h and mi else "")

        return "", ""

    def getRecordingData(self, fileName):
        """Return a dict of file-level audio metadata."""
        recordingData = {"fileName": fileName, "rating": "0"}

        meta_date, meta_time = _read_wav_metadata_datetime(fileName)
        fn_date, fn_time = self._parseDateTimeFromFilename(fileName)
        # Embedded file metadata date/time, kept separately from the assigned
        # date/time so the UI can show the user what the file itself records.
        recordingData["metaDate"] = meta_date or ""
        recordingData["metaTime"] = meta_time or ""
        if meta_date:
            recordingData["date"] = meta_date
            recordingData["time"] = meta_time
            recordingData["dateSource"] = "metadata"
        else:
            recordingData["date"] = fn_date if fn_date else "Date unknown"
            recordingData["time"] = fn_time if fn_time else "Time unknown"
            recordingData["dateSource"] = "filename"

        try:
            mtime = os.path.getmtime(fileName)
            recordingData["mtime"] = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            recordingData["mtime"] = ""

        # Audio format metadata via libsndfile (all formats incl. 24-bit, 32-bit
        # float, FLAC); the stdlib wave module can't read those.
        try:
            info = _sf.info(fileName) if _sf is not None else None
            if info is None:
                raise ValueError
            dur = info.frames / info.samplerate if info.samplerate else 0
            m_part, s_part = divmod(int(dur), 60)
            recordingData["duration"] = f"{m_part}:{s_part:02d}"
            recordingData["sampleRate"] = f"{info.samplerate} Hz"
            recordingData["bitDepth"] = _bit_depth_label(info.subtype)
            recordingData["channels"] = "Stereo" if info.channels == 2 else "Mono"
        except Exception:
            recordingData["duration"] = ""
            recordingData["sampleRate"] = ""
            recordingData["bitDepth"] = ""
            recordingData["channels"] = ""

        recordingData["device"] = _read_wav_device(fileName)

        return recordingData

    def getRecordingMetaDatetime(self, filepath):
        """Return a recording's embedded (date 'YYYY-MM-DD', time 'HH:MM'), or
        ('', ''). Lightweight header read used by Rename Media to backfill the
        cached metaDate/metaTime for catalogs that predate that field."""
        return _read_wav_metadata_datetime(filepath)

    def readWavMetadateDatetime(self, filepath):
        """Return WAV metadata datetime as an EXIF-format string, or None.

        Returns 'YYYY:MM:DD HH:MM:00' when both date and time are found,
        'YYYY:MM:DD' when only a date is found, or None when no metadata
        datetime exists.  The EXIF format makes the result usable directly
        in the exifDatetime slot in Rename Media rows.
        """
        d, t = _read_wav_metadata_datetime(filepath)
        if not d:
            return None
        exif_date = d.replace('-', ':')
        if t and len(t) >= 5:
            return f'{exif_date} {t[0:2]}:{t[3:5]}:00'
        return exif_date

    def matchRecording(self, file):
        """Suggest a checklist match for a WAV file, preferring embedded metadata
        over filename-based date/time parsing when metadata is available."""
        meta_date, meta_time = _read_wav_metadata_datetime(file)
        fn_date, fn_time = self._parseDateTimeFromFilename(file)
        recordingDate = meta_date or fn_date
        recordingTime = meta_time or fn_time
        rawRecordingTime = recordingTime

        dateMatchFound = False
        timeMatchFound = False
        if recordingDate:
            _df = code_Filter.Filter()
            _df.setStartDate(recordingDate)
            _df.setEndDate(recordingDate)
            dateMatchFound = len(self.GetLocations(_df, "OnlyLocations")) > 0
            if dateMatchFound and recordingTime:
                _tf = code_Filter.Filter()
                _tf.setStartDate(recordingDate)
                _tf.setEndDate(recordingDate)
                _tf.setTime(recordingTime)
                timeMatchFound = len(self.GetLocations(_tf, "OnlyLocations")) > 0
            elif dateMatchFound:
                timeMatchFound = True

        recordingLocation = ""
        f = code_Filter.Filter()
        f.setStartDate(recordingDate)
        f.setEndDate(recordingDate)
        f.setTime(recordingTime)
        locations = self.GetLocations(f, "OnlyLocations")

        if len(locations) == 1:
            recordingLocation = locations[0]
            if recordingTime:
                fwl = code_Filter.Filter()
                fwl.setStartDate(recordingDate)
                fwl.setEndDate(recordingDate)
                fwl.setLocationName(recordingLocation)
                fwl.setLocationType("Location")
                fwl.setTime(recordingTime)
                startTimes = self.GetStartTimes(fwl)
                if startTimes:
                    am = 60 * int(recordingTime[0:2]) + int(recordingTime[3:5])
                    _valid = [t for t in startTimes if _hhmm_to_minutes(t) is not None]
                    if _valid:
                        recordingTime = min(_valid, key=lambda t: abs(_hhmm_to_minutes(t) - am))
        else:
            recordingLocation = ""

        if recordingLocation == "" and recordingDate:
            f2 = code_Filter.Filter()
            f2.setStartDate(recordingDate)
            f2.setEndDate(recordingDate)
            locs2 = self.GetLocations(f2, "OnlyLocations")
            if len(locs2) == 1:
                recordingLocation = locs2[0]
                if recordingTime:
                    checklists = self.GetChecklists(f2)
                    if checklists:
                        am = 60 * int(recordingTime[0:2]) + int(recordingTime[3:5])
                        recordingTime = min(checklists, key=lambda c: _checklist_distance(c, am))[5]
                else:
                    pts = self.GetStartTimes(f2)
                    if pts:
                        recordingTime = pts[0]
            elif len(locs2) > 1 and recordingTime:
                checklists = self.GetChecklists(f2)
                if checklists:
                    am = 60 * int(recordingTime[0:2]) + int(recordingTime[3:5])
                    best = min(checklists, key=lambda c: _checklist_distance(c, am))
                    recordingLocation = best[3]
                    recordingTime = best[5]

        # Species name matching from filename (same algorithm as matchPhoto)
        recordingCommonName = ""
        if recordingLocation and recordingDate and recordingTime:
            f3 = code_Filter.Filter()
            f3.setLocationType("Location")
            f3.setLocationName(recordingLocation)
            f3.setStartDate(recordingDate)
            f3.setEndDate(recordingDate)
            f3.setTime(recordingTime)
            possibleNames = self.GetSpecies(f3)

            fn_lower = os.path.splitext(os.path.basename(file))[0].lower()
            fn_alpha = re.sub(r'[^a-z]', '', fn_lower)
            fn_alnum = re.sub(r'[^a-z0-9]', '', fn_lower)

            best_score = 0
            for pcn in possibleNames:
                score = 0
                ebird = self.GeteBirdCode(pcn).lower()
                if ebird and ebird in fn_alnum:
                    score = max(score, len(ebird))
                bbl = self.GetBBLCode(pcn).lower()
                if bbl and bbl in fn_alnum:
                    score = max(score, len(bbl))
                common_clean = re.sub(r'[^a-z]', '', pcn.lower())
                if common_clean:
                    score = max(score, _longest_substr_in(common_clean, fn_alpha))
                sci = self.GetScientificName(pcn)
                if sci:
                    sci_clean = re.sub(r'[^a-z]', '', sci.lower())
                    if sci_clean:
                        score = max(score, _longest_substr_in(sci_clean, fn_alpha))
                if score > best_score:
                    best_score = score
                    recordingCommonName = pcn
            if best_score < 4:
                recordingCommonName = ""

        return {
            "recordingLocation": recordingLocation,
            "recordingDate": recordingDate,
            "recordingTime": recordingTime,
            "recordingCommonName": recordingCommonName,
            "dateMatchFound": dateMatchFound,
            "timeMatchFound": timeMatchFound,
        }

    def getComboDataForAudio(self, audioMatchData, allDates=None):
        """Pre-compute combo box data for a new recording file (date-first cascade).

        allDates (the unfiltered date list) is identical for every recording
        and scans the whole database to build — callers processing many files
        should compute it once and pass it in."""
        recordingDate = audioMatchData.get("recordingDate", "")
        recordingLocation = audioMatchData.get("recordingLocation", "")
        recordingTime = audioMatchData.get("recordingTime", "")

        if allDates is None:
            allDates = self.GetDates(code_Filter.Filter())

        locationsByDate = []
        if recordingDate:
            f = code_Filter.Filter()
            f.setStartDate(recordingDate)
            f.setEndDate(recordingDate)
            locationsByDate = self.GetLocations(f)

        timesByDateAndLocation = []
        if recordingDate and recordingLocation:
            f = code_Filter.Filter()
            f.setStartDate(recordingDate)
            f.setEndDate(recordingDate)
            f.setLocationName(recordingLocation)
            f.setLocationType("Location")
            timesByDateAndLocation = self.GetStartTimes(f)

        speciesByChecklist = []
        if recordingDate and recordingLocation and recordingTime:
            f = code_Filter.Filter()
            f.setLocationType("Location")
            f.setLocationName(recordingLocation)
            f.setStartDate(recordingDate)
            f.setEndDate(recordingDate)
            f.setTime(recordingTime)
            speciesByChecklist = self.GetSpecies(f)

        return {
            "allDates": allDates,
            "locationsByDate": locationsByDate,
            "timesByDateAndLocation": timesByDateAndLocation,
            "speciesByChecklist": speciesByChecklist,
        }

    def getComboDataForAudioExisting(self, sighting):
        """Pre-compute combo box data for an audio recording already in the catalog."""
        allLocations = list(self.locationList)

        f = code_Filter.Filter()
        f.setLocationName(sighting["location"])
        f.setLocationType("Location")
        datesByLocation = self.GetDates(f)

        f2 = code_Filter.Filter()
        f2.setLocationName(sighting["location"])
        f2.setLocationType("Location")
        f2.setStartDate(sighting["date"])
        f2.setEndDate(sighting["date"])
        timesByLocationAndDate = self.GetStartTimes(f2)

        f3 = code_Filter.Filter()
        f3.setChecklistID(sighting.get("checklistID", ""))
        speciesByChecklist = self.GetSpecies(f3)

        return {
            "allLocations": allLocations,
            "datesByLocation": datesByLocation,
            "timesByLocationAndDate": timesByLocationAndDate,
            "speciesByChecklist": speciesByChecklist,
        }

    def addPhotoToDatabase(self, filter, photoData, skip_file_check=False):

        if not skip_file_check and not os.path.isfile(photoData["fileName"]):
            return None

        # Fast path: if filter has checklistID + speciesName, scan directly
        # instead of running the full GetSightings filter machinery.
        checklistID = filter.getChecklistID()
        speciesName = filter.getSpeciesName()
        if checklistID and speciesName and checklistID in self.checklistDict:
            candidates = self.checklistDict[checklistID]
            s = next((c for c in candidates
                      if c["commonName"] == speciesName
                      or c.get("subspeciesName") == speciesName), None)
        else:
            sightings = self.GetSightings(filter)
            s = sightings[0] if sightings else None

        if s is not None:
            if "photos" not in s:
                s["photos"] = [photoData]
            elif photoData not in s["photos"]:
                s["photos"].append(photoData)
            self.addPhotoDataToDb(photoData)
            return s

        return None

    def writePhotoDataToFile(self, fileName):

        filter = code_Filter.Filter()
        photoSightings = self.GetSightingsWithPhotos(filter)
        recordingSightings = self.GetSightingsWithRecordings(filter)

        try:
            with open(fileName, mode='w', encoding='utf-8') as f:
                # Wave 1: photos
                for s in photoSightings:
                    for p in s["photos"]:
                        record = {
                            "type":        "photo",
                            "ChecklistID": s["checklistID"],
                            "CommonName":  s["commonName"],
                            "FileName":    p["fileName"],
                            "Camera":      p["camera"],
                            "Lens":        p["lens"],
                            "ShutterSpeed": p["shutterSpeed"],
                            "Aperture":    p["aperture"],
                            "ISO":         p["iso"],
                            "FocalLength": p["focalLength"],
                            "Rating":      p["rating"],
                        }
                        record.update(_photo_exif_fields(p))
                        f.write(json.dumps(record) + '\n')
                # Wave 2: audio
                for s in recordingSightings:
                    for a in s["audio"]:
                        record = {
                            "type":        "audio",
                            "ChecklistID": s["checklistID"],
                            "CommonName":  s["commonName"],
                            "FileName":    a["fileName"],
                            "Duration":    a.get("duration", ""),
                            "SampleRate":  a.get("sampleRate", ""),
                            "BitDepth":    a.get("bitDepth", ""),
                            "Channels":    a.get("channels", ""),
                            "Device":      a.get("device", ""),
                            "Rating":      a.get("rating", "0"),
                        }
                        record.update(_recording_meta_fields(a))
                        f.write(json.dumps(record) + '\n')
        except IOError as err:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("Error occurred while saving the media catalog to disk.\n" + str(err))
            msg.setWindowTitle("Save Error")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()


    def appendPhotoToJsonl(self, sighting, photoData):
        if not self.photoDataFile or not self.photoDataFile.lower().endswith(".jsonl"):
            return
        record = {
            "type":        "photo",
            "ChecklistID": sighting["checklistID"],
            "CommonName":  sighting["commonName"],
            "FileName":    photoData["fileName"],
            "Camera":      photoData["camera"],
            "Lens":        photoData["lens"],
            "ShutterSpeed": photoData["shutterSpeed"],
            "Aperture":    photoData["aperture"],
            "ISO":         photoData["iso"],
            "FocalLength": photoData["focalLength"],
            "Rating":      photoData["rating"],
        }
        record.update(_photo_exif_fields(photoData))
        with open(self.photoDataFile, mode='a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')


    def appendPhotoDeletionToJsonl(self, fileName):
        if not self.photoDataFile or not self.photoDataFile.lower().endswith(".jsonl"):
            return
        with open(self.photoDataFile, mode='a', encoding='utf-8') as f:
            f.write(json.dumps({"FileName": fileName, "deleted": True}) + '\n')

    def addRecordingToDatabase(self, filter, recordingData, skip_file_check=False):
        if not skip_file_check and not os.path.isfile(recordingData["fileName"]):
            return None

        checklistID = filter.getChecklistID()
        speciesName = filter.getSpeciesName()
        if checklistID and speciesName and checklistID in self.checklistDict:
            candidates = self.checklistDict[checklistID]
            s = next((c for c in candidates
                      if c["commonName"] == speciesName
                      or c.get("subspeciesName") == speciesName), None)
        else:
            sightings = self.GetSightings(filter)
            s = sightings[0] if sightings else None

        if s is not None:
            if "audio" not in s:
                s["audio"] = [recordingData]
            elif recordingData not in s["audio"]:
                s["audio"].append(recordingData)
            return s

        return None

    def removeRecordingFromDatabase(self, location, date, time, commonName, audioFileName):
        f = code_Filter.Filter()
        f.setLocationName(location)
        f.setLocationType("Location")
        f.setStartDate(date)
        f.setEndDate(date)
        f.setTime(time)
        f.setSpeciesName(commonName)
        sightings = self.GetSightingsWithRecordings(f)
        for s in sightings:
            if "audio" in s:
                s["audio"] = [a for a in s["audio"] if a["fileName"] != audioFileName]
                if not s["audio"]:
                    del s["audio"]

    def removeRecordingFileFromDatabase(self, audioFileName):
        for s in self.sightingList:
            if "audio" in s:
                s["audio"] = [a for a in s["audio"] if a["fileName"] != audioFileName]
                if not s["audio"]:
                    del s["audio"]

    def appendRecordingToJsonl(self, sighting, recordingData):
        if not self.photoDataFile or not self.photoDataFile.lower().endswith(".jsonl"):
            return
        record = {
            "type": "audio",
            "ChecklistID": sighting["checklistID"],
            "CommonName":  sighting["commonName"],
            "FileName":    recordingData["fileName"],
            "Duration":    recordingData.get("duration", ""),
            "SampleRate":  recordingData.get("sampleRate", ""),
            "BitDepth":    recordingData.get("bitDepth", ""),
            "Channels":    recordingData.get("channels", ""),
            "Device":      recordingData.get("device", ""),
            "Rating":      recordingData.get("rating", "0"),
        }
        record.update(_recording_meta_fields(recordingData))
        with open(self.photoDataFile, mode='a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def appendRecordingDeletionToJsonl(self, fileName):
        if not self.photoDataFile or not self.photoDataFile.lower().endswith(".jsonl"):
            return
        with open(self.photoDataFile, mode='a', encoding='utf-8') as f:
            f.write(json.dumps({"type": "audio", "FileName": fileName, "deleted": True}) + '\n')

    def compactJsonlFile(self):
        if self.photoDataFile and self.photoDataFile.lower().endswith(".jsonl"):
            self.writePhotoDataToFile(self.photoDataFile)
            self.photosNeedSaving = False


    def readPhotoDataFromFile(self, fileName):

        self.photoDataFile = fileName

        if fileName.lower().endswith(".csv"):
            self._readPhotoDataFromCsv(fileName)
        else:
            self._readPhotoDataFromJsonl(fileName)

        self.refreshPhotoLists()
        self.photoDataFileOpenFlag = True


    _CSV_REQUIRED_FIELDS = ("ChecklistID", "CommonName", "FileName", "Camera",
                             "Lens", "ShutterSpeed", "Aperture", "ISO", "FocalLength")

    def _readPhotoDataFromCsv(self, fileName):
        self.csvSkippedRows = 0
        try:
            with open(fileName, mode='r', encoding='utf-8') as photoDataFile:
                csv_reader = csv.DictReader(photoDataFile)
                for row in csv_reader:
                    if any(f not in row for f in self._CSV_REQUIRED_FIELDS):
                        self.csvSkippedRows += 1
                        continue
                    photoData = {}
                    filter = code_Filter.Filter()
                    filter.setChecklistID(row["ChecklistID"])
                    filter.setSpeciesName(row["CommonName"])
                    photoData["fileName"] = row["FileName"]
                    photoData["camera"] = row["Camera"]
                    photoData["lens"] = row["Lens"]
                    photoData["shutterSpeed"] = row["ShutterSpeed"]
                    photoData["aperture"] = row["Aperture"]
                    photoData["iso"] = row["ISO"]
                    photoData["focalLength"] = row["FocalLength"]
                    rating = row.get("Rating", "0")
                    photoData["rating"] = rating if rating in ["0","1","2","3","4","5"] else "0"
                    if "ExifDateTime" in row:
                        photoData["exifDatetime"] = row.get("ExifDateTime") or None
                        photoData["exifSubsec"] = row.get("ExifSubSec") or None
                        photoData["exifDateInvalid"] = bool(row.get("ExifDateInvalid"))
                    self.addPhotoToDatabase(filter, photoData, skip_file_check=True)
        except Exception:
            pass


    def _readPhotoDataFromJsonl(self, fileName):
        try:
            self.jsonlSkippedLines = 0
            photo_state = {}      # fn → record or None
            recordings_state = {}      # (fn, checklistID, commonName) → record

            with open(fileName, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        self.jsonlSkippedLines += 1
                        continue
                    fn = record.get("FileName", "")
                    if not fn:
                        continue
                    record_type = record.get("type", "photo")
                    if record_type == "audio":
                        if record.get("deleted"):
                            for k in [k for k in recordings_state if k[0] == fn]:
                                del recordings_state[k]
                        else:
                            key = (fn, record.get("ChecklistID", ""), record.get("CommonName", ""))
                            recordings_state[key] = record
                    else:
                        photo_state[fn] = None if record.get("deleted") else record

            self.photoRecordsInCatalog = (
                sum(1 for v in photo_state.values() if v is not None) + len(recordings_state)
            )

            for fn, row in photo_state.items():
                if row is None:
                    continue
                filter = code_Filter.Filter()
                filter.setChecklistID(row.get("ChecklistID", ""))
                filter.setSpeciesName(row.get("CommonName", ""))
                photoData = {}
                photoData["fileName"] = row.get("FileName", "")
                photoData["camera"] = row.get("Camera", "")
                photoData["lens"] = row.get("Lens", "")
                photoData["shutterSpeed"] = row.get("ShutterSpeed", "")
                photoData["aperture"] = row.get("Aperture", "")
                photoData["iso"] = row.get("ISO", "")
                photoData["focalLength"] = row.get("FocalLength", "")
                rating = row.get("Rating", "0")
                photoData["rating"] = rating if rating in ["0","1","2","3","4","5"] else "0"
                # Cached EXIF capture time (present only once gleaned); absent →
                # Rename Media reads it on demand and caches it back.
                if "ExifDateTime" in row:
                    photoData["exifDatetime"] = row.get("ExifDateTime") or None
                    photoData["exifSubsec"] = row.get("ExifSubSec") or None
                    photoData["exifDateInvalid"] = bool(row.get("ExifDateInvalid"))
                self.addPhotoToDatabase(filter, photoData, skip_file_check=True)

            for (fn, checklistID, commonName), row in recordings_state.items():
                filter = code_Filter.Filter()
                filter.setChecklistID(checklistID)
                filter.setSpeciesName(commonName)
                recordingData = {}
                recordingData["fileName"] = fn
                recordingData["duration"] = row.get("Duration", "")
                sr_val = row.get("SampleRate", "")
                bd_val = row.get("BitDepth", "")
                ch_val = row.get("Channels", "")
                # Backfill format fields for catalogs written before these were
                # captured (one cheap header read via libsndfile).
                if (not sr_val or not bd_val or not ch_val) and os.path.isfile(fn):
                    g_sr, g_bd, g_ch = _glean_audio_format(fn)
                    sr_val = sr_val or g_sr
                    bd_val = bd_val or g_bd
                    ch_val = ch_val or g_ch
                recordingData["sampleRate"] = sr_val
                recordingData["bitDepth"] = bd_val
                recordingData["channels"] = ch_val
                # Recording device: backfill from the file if not persisted yet.
                dev_val = row.get("Device", "")
                if not dev_val and "Device" not in row and os.path.isfile(fn):
                    dev_val = _read_wav_device(fn)
                recordingData["device"] = dev_val
                rating = row.get("Rating", "0")
                recordingData["rating"] = rating if rating in ["0","1","2","3","4","5"] else "0"
                # Cached embedded date/time (present only once gleaned); absent →
                # Rename Media reads it on demand and caches it back.
                if "MetaDate" in row:
                    recordingData["metaDate"] = row.get("MetaDate") or ""
                    recordingData["metaTime"] = row.get("MetaTime") or ""
                self.addRecordingToDatabase(filter, recordingData, skip_file_check=True)
        except Exception:
            pass


    def refreshPhotoLists(self):
        
        self.cameraList = []
        self.lensList = []
        self.shutterSpeedList = []
        self.apertureList = []
        self.focalLengthList=[]
        self.isoList = []
        
        cameraSet = set()
        lensSet = set()
        shutterSpeedSet = set()
        apertureSet= set()
        focalLengthSet = set()
        isoSet = set()
        
        for s in self.sightingList:
            if "photos" in s:
                for p in s["photos"]:
                    if p["camera"] != "":
                        cameraSet.add(p["camera"])
                    if p["lens"] != "":
                        lensSet.add(p["lens"])
                    if p["shutterSpeed"] != "":
                        shutterSpeedSet.add(p["shutterSpeed"])
                    if p["aperture"] != "":
                        apertureSet.add(p["aperture"])
                    if p["iso"] != "":
                        isoSet.add(p["iso"])
                    if p["focalLength"] != "":
                        focalLengthSet.add(p["focalLength"])
                    
        self.cameraList = list(cameraSet)
        self.lensList = list(lensSet)
        self.shutterSpeedList = natsorted(list(shutterSpeedSet), reverse=True)
        self.apertureList = natsorted(list(apertureSet))
        self.isoList = natsorted(list(isoSet))
        self.focalLengthList = natsorted(list(focalLengthSet))

        self.refreshRecordingsLists()


    def refreshRecordingsLists(self):
        import math
        duration_set = set()
        rate_set = set()
        depth_set = set()
        device_set = set()
        has_unknown_device = False
        for s in self.sightingList:
            if "audio" in s:
                for a in s["audio"]:
                    dur_str = a.get("duration", "")
                    if dur_str:
                        try:
                            parts = dur_str.split(":")
                            total_sec = int(parts[0]) * 60 + int(parts[1])
                            rounded = math.ceil(total_sec / 5) * 5
                            if rounded > 0:
                                duration_set.add(rounded)
                        except (ValueError, IndexError):
                            pass
                    hz = _hz_from_rate_str(a.get("sampleRate", ""))
                    if hz:
                        rate_set.add(hz)
                    bd = a.get("bitDepth", "")
                    if bd:
                        depth_set.add(bd)
                    dev = a.get("device", "")
                    if dev:
                        device_set.add(dev)
                    else:
                        has_unknown_device = True
        self.durationList = [f"{d}s" for d in sorted(duration_set)]
        # Sample rates as kHz combo labels, low→high; bit depths in fidelity order.
        self.sampleRateList = [_khz_label(hz) for hz in sorted(rate_set)]
        self.bitDepthList = [d for d in _BIT_DEPTH_ORDER if d in depth_set]
        # Recording devices found (alphabetical); "Unknown" last if any recording
        # has no device metadata, so those can still be filtered.
        self.deviceList = sorted(device_set)
        if has_unknown_device:
            self.deviceList.append("Unknown")


    def CountSpecies(self, speciesList):
        
        # method to count true species in a list. Entries with parens, /, or sp. or hybrids should not be counted,
        # unless no non-paren entries exist for that species.append
        speciesSet = set()
        
        # use a set (which deletes duplicates) to hold species names
        # remove parens from species names if they exist
        for s in speciesList:
            if "(" in s and " x " not in s:
                speciesSet.add(s.split(" (")[0])
            elif "sp." in s:
                pass
            elif "/" in s:
                pass
            elif " x " in s:
                pass
            else:
                speciesSet.add(s)
        
        # count the species, including species whose parens have been removed
        count = len(speciesSet)
        
        return(count)
        
        
    def ReadCountryStateCodeFile(self, dataFile):
        
        # initialize variable used to store CSV file's data
        countryCodeData = []
        
        # open the country and state code data file
        # and read its lines into a list for future searching
        with open(dataFile, 'r', errors='replace') as csvfile:
            csvdata = csv.reader(csvfile, delimiter=',', quotechar='"')
            for line in csvdata:
                countryCodeData.append(line)
        csvfile.close()
        
        # clear the countryList and stateList because we'll use longer names
        self.countryList = []
        self.stateList = []

        # search through each location in the master location file
        # append the long country and state names when found in the country state code data
        for c in countryCodeData:

#             # append two place holders in the masterLocationList for long country and state names
#             l.append("")
#             l.append("")
#             
            for l in self.masterLocationList:

                # find the long country name by looking for a perfect match of "cc-" for the state code
                # this match is actually for the country because states have characters
                # after the - character
                if l["countryCode"] + "-" == c[1]:

                    # when found, save the long country name to the masterLocationList
                    l["countryName"] = c[2]
                    self.countryList.append(c[2])

                # look for a perfect match for the state code
                elif l["stateCode"] == c[1]:
                    
                    # when found, save the long state name to the masterLocationList
                    l["stateName"] = c[2]
                    self.stateList.append(c[2])
                    
                    # no need to keep searching. We've found our long names.
                    break
                    
        # get rid of duplicates in master country and state lists using the set command
        self.countryList = list(set(self.countryList))
        self.stateList = list(set(self.stateList))

        # sort the master country and state lists
        self.countryList.sort()
        self.stateList.sort()

        # self.countryCodeData = countryCodeData

        # Pre-build O(1) lookup dicts so GetCountryName/GetStateName don't iterate all records
        self._countryLookup = {}
        self._stateLookup = {}
        for l in self.masterLocationList:
            if "countryCode" in l and "countryName" in l:
                self._countryLookup[l["countryCode"]] = l["countryName"]
            if "stateCode" in l and "stateName" in l:
                self._stateLookup[l["stateCode"]] = l["stateName"]

        self.countryStateCodeFileFound = True


    def _computeRegionCodes(self, country, state):
        """Compute region code list for a (country, state) pair, with caching."""
        key = (country, state)
        cached = self._regionCache.get(key)
        if cached is not None:
            return cached

        regionCodes = []

        # ----------------------------------------
        # add ABA if in US, Canada, or St. Pierre et Miquelon, but exclude Hawaii
        if country in ["US", "CA", "PM"]:
            if state != "US-HI":
                regionCodes.append("ABA")

        # ----------------------------------------
        # add AOU if if in US, Canada, St. Pierre et Miquelon, Mexico, Central America
        if country in [
            "US", "CA", "PM", "MX", "GT", "SV", "HN", "CR", "PA",
            "CU", "HT", "DO", "JM", "KY", "PR", "VG", "VI", "AI",
            "MF", "BL", "BQ", "KN", "AG", "MS", "GP", "DM", "BS",
            "BB", "GD", "LC", "VC", "BM", "CP", "NI"
            ]:
            regionCodes.append("AOU")

        if state in [
            "CO-SAP", "UM-67", "UM-71"
            ]:
            regionCodes.append("AOU")

        # ----------------------------------------
        # add USL if if in Lower 48 US states listing region as designated by eBird

        if country == "US":
            if state not in ["US-AK", "US-HI"]:
                regionCodes.append("USL")


        #---------------------------------------
        # add AFR if if in Africa
        if country in [
            "DZ", "AO", "SH", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD",
            "KM", "CG", "CD", "DJ", "GQ", "ER", "SZ", "ET", "GA", "GM",
            "GH", "GN", "GW", "CI", "KE", "LS", "LR", "LY", "MG", "MW", "ML",
            "MR", "MU", "YT", "MA", "MZ", "NA", "NE", "NG", "ST", "RE", "RW",
            "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SH", "SD", "SZ", "TZ",
            "TG", "TN", "UG", "CD", "ZM", "TZ", "ZW"
            ]:
            regionCodes.append("AFR")

        if state == "ES-CN":
            regionCodes.append("AFR")

        if country == "EG":
            if state not in ["EG-PTS", "EG-JS", "EG-SIN"]:
                regionCodes.append("AFR")

        # ----------------------------------------
        # add ASI if if in Asia
        if country in [
            "AF", "AM", "AZ", "BH", "BD", "BT", "BN", "KH", "CN", "CX", "CC",
            "IO", "GE", "HK", "IN", "IR", "IQ", "IL", "JP", "JO",
            "KW", "KG", "LA", "LB", "MO", "MY", "MV", "MN", "MM", "NP", "KP",
            "OM", "PK", "PS", "PH", "QA", "SA", "SG", "KR", "LK", "SY", "TW",
            "TJ", "TH", "TM", "AE", "UZ", "VN", "YE", "SD", "SZ", "TZ",
            "TG", "TN", "UG", "CD", "ZM", "TZ", "ZW"
            ]:
            regionCodes.append("ASI")

        if country == "TR":
            if state not in ["TR-22", "TR-39", "TR-59"]:
                regionCodes.append("ASI")

        if country == "KZ":
            if state not in ["KZ-ATY", "KZ-ZAP"]:
                regionCodes.append("ASI")

        if country == "ID":
            if state != "ID-IJ":
                regionCodes.append("ASI")

        if country == "EG":
            if state in ["EG-PTS", "EG-JS", "EG-SIN"]:
                regionCodes.append("ASI")

        if country == "RU":
            if state in [
                "RU-YAN", "RU-KHM", "RU-TYU", "RU-OMS", "RU-TOM", "RU-NVS",
                "RU-ALT", "RU-KEM", "RU-AL", "RU-KK", "RU-KYA", "RU-TY",
                "RU-IRK", "RU-SA", "RU-BU", "RU-ZAB", "RU-AMU", "RU-KHA",
                "RU-YEV", "RU-PRI", "RU-MAG", "RU-CHU", "RU-KAM", "RU-SAK"
                ]:
                regionCodes.append("ASI")

        # ----------------------------------------
        # add ATL if if in Atlantic listing region

        # Note that pelagic sightings more than 200 miles from a state
        # will not be counted here because I don't know how to calculate
        # if a log/lat sighting is 200 miles from a state

        if country in [
            "BM", "FK", "SH"
            ]:
            regionCodes.append("ATL")


        # ----------------------------------------
        # add AUE if if in Australasia (eBird) listing region

        if country in [
            "AU", "AC", "NF", "NZ", "SB", "VU", "NC", "PG",
            ]:
            regionCodes.append("AUE")

        if state in [
            "ID-IJ", "ID-MA"
            ]:
            regionCodes.append("AUE")


        # ----------------------------------------
        # add AUA if if in Australasia (ABA) listing region

        if country in [
            "AU", "ID"
            ]:
            regionCodes.append("AUA")


        # ----------------------------------------
        # add AUS if if in Australia listing region as designated by eBird

        if country in [
            "AU", "HM", "CX", "CC", "NF", "AC"
            ]:
            regionCodes.append("AUS")


        # ----------------------------------------
        # add EUR if if in Europe listing region as designated by eBird

        if country in [
            "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CY", "CZ", "DK",
            "EE", "FO", "FI", "FR", "DE", "GI", "GR", "HU", "IS", "IE", "IM",
            "IT", "RS", "LV", "LI", "LT", "LU", "MK", "MT", "MD", "MC", "ME",
            "NL", "NO", "PL", "PT", "RO", "RU", "SM", "RS", "SK", "SI",
            "SE", "CH", "UA", "GB", "VA", "JE"
            ]:
            regionCodes.append("EUR")

        # include Spain, but not Canaries
        if country == "ES":
            if state != "ES-CN":
                regionCodes.append("EUR")

        # include Russia, but exclude Asian regions of Russia
        if country == "RU":
            if state not in [
                "RU-YAN", "RU-KHM", "RU-TYU", "RU-OMS", "RU-TOM", "RU-NVS",
                "RU-ALT", "RU-KEM", "RU-AL", "RU-KK", "RU-KYA", "RU-TY",
                "RU-IRK", "RU-SA", "RU-BU", "RU-ZAB", "RU-AMU", "RU-KHA",
                "RU-YEV", "RU-PRI", "RU-MAG", "RU-CHU", "RU-KAM", "RU-SAK"
                ]:
                    regionCodes.append("EUR")

        # include European areas of Turkey
        if state in ["TR-22", "TR-39", "TR-59"]:
            regionCodes.append("EUR")

        # include European areas of Kazakhstan
        if state in ["KZ-ATY", "KZ-ZAP"]:
            regionCodes.append("EUR")


        # ----------------------------------------
        # add NAM if if in North America listing region as designated by eBird

        if country in [
            "CA", "PM", "MX", "GT", "SV", "HN", "CR", "PA",
            "CU", "HT", "DO", "JM", "KY", "PR", "VG", "VI", "AI",
            "MF", "BL", "BQ", "KN", "AG", "MS", "GP", "DM", "BS",
            "BB", "GD", "LC", "VC", "BM", "CP", "GL", "NI"
            ]:
            regionCodes.append("NAM")

        if state in [
            "CO-SAP"
            ]:
            regionCodes.append("NAM")

        if country == "US":
            if state != "US-HI":
                regionCodes.append("NAM")


        # ----------------------------------------
        # add SAM if if in South America listing region as designated by eBird

        if country in [
            "AR", "BO", "BR", "CL", "CO", "FK", "GF",
            "GY", "GY", "PY", "PE", "SR", "UY", "VE", "TT", "CW", "AW"
            ]:
            regionCodes.append("SAM")

        if state in [
            "BQ-BO"
            ]:
            regionCodes.append("SAM")

        if country == "EC" and state != "EC-W":
            regionCodes.append("SAM")


        # ----------------------------------------
        # add WIN if if in West Indies listing region as designated by eBird

        if country in [
            "AI", "AG", "AW", "BS", "BB", "VG", "KY", "VI"
            "CU", "DM", "DO", "GD", "GP", "HT", "JM", "MQ",
            "MS", "AN", "PR", "KN", "LC", "VC", "TT", "TC"
            ]:
            regionCodes.append("WIN")

        if state == "CO-SAP":
            regionCodes.append("WIN")


        # ----------------------------------------
        # add CAM if if in Central America listing region as designated by eBird

        if country in [
            "BZ", "CR", "SV", "GT", "HN", "NI", "PA"
            ]:
            regionCodes.append("CAM")


        # ----------------------------------------
        # add SPO if if in South Polar listing region as designated by eBird

        if country in [
            "AQ", "BV", "GS", "HM"
            ]:
            regionCodes.append("SPO")


        # ----------------------------------------
        # add WH if if in Western Hemisphere listing region as designated by eBird

        if "NAM" in regionCodes:
            regionCodes.append("WHE")

        if "SAM" in regionCodes:
            regionCodes.append("WHE")

        if country in [
            "CP", "BM", "FK"
            ]:
            regionCodes.append("WHE")

        if state in [
            "US-HI", "UM-67", "UM-71", "EC-W"
            ]:
            regionCodes.append("WHE")


        # ------------------------------------------------------
        # add EH if in Eastern Hemisphere  (not Western, and not South Polar)

        if "WHE" not in regionCodes and "SPO" not in regionCodes:
            regionCodes.append("EHE")

        self._regionCache[key] = regionCodes
        return regionCodes

    def ReadDataFile(self, DataFile, progress_callback=None):

        self.ClearDatabase()

        # extract data from zip file if user has chosen a zip file
        import zipfile

        if zipfile.is_zipfile(DataFile):

            filehandle = open(DataFile, 'rb')

            zfile = zipfile.ZipFile(filehandle)

            try:
                csvfile = io.StringIO(zfile.read("MyEBirdData.csv").decode('utf-8'))

            except (KeyError):
                self.eBirdFileOpenFlag = False
                return

        # use csv reader to process csv file if user has selected a csv file

        if os.path.splitext(DataFile)[1] == ".csv":
            csvfile = open(DataFile, 'r', encoding='utf-8')

        # Count total data rows so the caller can show a determinate progress bar.
        # A single pass over the raw text is fast even for large files.
        total_rows = max(sum(1 for _ in csvfile) - 1, 1)  # −1 for the header row
        csvfile.seek(0)

        # process CSV values from csvfile.
        csvdata = csv.DictReader(csvfile)

        # initialize temporary list variable to hold location data
        thisMasterLocationEntry = []

        _row_num = 0
        for line in csvdata:
            _row_num += 1
            if progress_callback and _row_num % 500 == 0:
                progress_callback(int(100 * _row_num / total_rows))
              
            # convert date format from mm-dd-yyyy to yyyy-mm-dd for international standard and sorting ability
            # THIS IS NO LONGER NECESSARY, AS IN MARCH 2019 EBIRD CHANGED THE DATA FORMAT TO THE ONE WE PREFER
            # line[10] = line[10][6:] + "-" + line[10][0:2] + "-" + line[10][3:5]
            
            # append state name in parentheses to county name to differentiate between
            # counties that have the same name but are in different states
            if line["County"] != "":
                line["County"] = line["County"] + " (" + line["State/Province"] + ")" 
                           
            # add blank elements to list so we can later add family and order names if taxonomic file exists
            # also add blank line for subspecies name
            
            # store full name (maybe a subspecies) in sighting
            subspeciesName = line["Common Name"]
            line["Subspecies"] = subspeciesName
            
            # remove any subspecies data in parentheses in species name
            # but keep "(hybrid)" if it's in the name
            if "(" in line["Common Name"]:
                if "hybrid" not in line["Common Name"]:
                    line["Common Name"] = line["Common Name"][:line["Common Name"].index("(") - 1]    
             
            # convert 12-hour time format to 24-hour format for easier sorting and display
            time = line["Time"]
            if "AM" in time:
                time = line["Time"][0:5]
            if "PM" in time:
                time = line["Time"][0:5]
                hour = int(line["Time"][0:2])
                hour = str(hour + 12)
                if hour == "24":
                    hour = "12"
                time = hour + line["Time"][2:5]  
            line["Time"] = time
            
            # add sighting to the main database for use by later searches etc.
            # this sightingList will be used in nearly every search performed by user
            
            # convert line's CSV data into our own dictionary to remove spaces, abbreviations, etc.
            thisSightingDict = dict(
                checklistID=line["Submission ID"],
                commonName=line["Common Name"],
                scientificName=line["Scientific Name"],
                subspeciesName=line["Subspecies"],
                taxonomicOrder=line["Taxonomic Order"],
                count=line["Count"],
                country=line["State/Province"][0:2],
                state=line["State/Province"],
                county=line["County"],
                locationID=line.get("Location ID", ""),
                location=line["Location"],
                latitude=line["Latitude"],
                longitude=line["Longitude"],
                date=line["Date"],
                time=line["Time"],
                protocol=line["Protocol"],
                duration=line["Duration (Min)"],
                allObsReported=line["All Obs Reported"],
                distance=line["Distance Traveled (km)"],
                areaCovered=line["Area Covered (ha)"],
                observers=line["Number of Observers"],
                breedingCode=line["Breeding Code"],
                checklistComments=line["Checklist Comments"],
                regionCodes=[]
                )
            
            if thisSightingDict["areaCovered"] is None:
                thisSightingDict["areaCovered"] = ""
            if thisSightingDict["distance"] is None:
                thisSightingDict["distance"] = ""
            if thisSightingDict["observers"] is None:
                thisSightingDict["observers"] = ""
            if thisSightingDict["breedingCode"] is None:
                thisSightingDict["breedingCode"] = ""
            if "Observation Details" in line:
                thisSightingDict["speciesComments"]=line["Observation Details"]
            if "Species Comments" in line:
                thisSightingDict["speciesComments"]=line["Species Comments"]
            if thisSightingDict["speciesComments"] is None:
                thisSightingDict["speciesComments"] = ""
            if thisSightingDict["checklistComments"] is None:
                thisSightingDict["checklistComments"] = ""
            thisSightingDict["family"] = ""
            thisSightingDict["order"] = ""

            # If a US sighting, use countyCodeDict to assign the unique 5-digit FIPS code for the county
            # we'll use this for choropleths
            if thisSightingDict["country"] == "US" and thisSightingDict["state"] not in ["US-HI", "US-AK"]:
                countyNameWithoutParentheses = thisSightingDict["county"].split(" (")[0]
                if countyNameWithoutParentheses != "":
                    fips = self._countyFipsLookup.get((countyNameWithoutParentheses, thisSightingDict["state"][3:5]))
                    if fips:
                        thisSightingDict["countyCode"] = fips

            # compute region codes using cached helper
            regionCodes = self._computeRegionCodes(thisSightingDict["country"], thisSightingDict["state"])
            thisSightingDict["regionCodes"] = regionCodes

            # add sighting to checklistDict, even if it's a sp or / species
            # use checklistID as the key
            checklistID = thisSightingDict["checklistID"]
            self.checklistDict.setdefault(checklistID, []).append(thisSightingDict)  

            # add sighting to other dicts only if it's a full species, not a / or sp.
            commonName = thisSightingDict["commonName"]

            #if ("/" not in commonName) and ("sp." not in commonName):
                
            self.allSpeciesList.append(commonName)

            # use species common name as key
            self.speciesDict.setdefault(commonName, []).append(thisSightingDict)

            # also add subspecies as key to speciesDict
            # to facilitate lookup
            subspeciesName = thisSightingDict["subspeciesName"]
            self.speciesDict.setdefault(subspeciesName, []).append(thisSightingDict)

            # add sighting to yearDict
            # use 4-digit year as the key
            year = thisSightingDict["date"][0:4]
            self.yearDict.setdefault(year, []).append(thisSightingDict)

            # add sighting to monthDict
            # use 2-digit month as the key
            month = thisSightingDict["date"][5:7]
            self.monthDict.setdefault(month, []).append(thisSightingDict)

            # add sighting to dateDict
            # use full date (yyyy-mm-dd) as the key
            date = thisSightingDict["date"]
            self.dateDict.setdefault(date, []).append(thisSightingDict)

            # add sighting to regionDict
            # use 3-character code as key
            regionCodes = thisSightingDict["regionCodes"]
            for r in regionCodes:
                self.regionDict.setdefault(r, []).append(thisSightingDict)

            # add sighting to countryDict
            # use 2-character code as key
            countryCode = thisSightingDict["country"]
            self.countryDict.setdefault(countryCode, []).append(thisSightingDict)

            # add sighting to stateDict
            # use cc-ss code as the key
            stateCode = thisSightingDict["state"]
            self.stateDict.setdefault(stateCode, []).append(thisSightingDict)

            # add sighting to countyDict
            # use county name as key
            # don't add sightings whose county name is absent
            county = thisSightingDict["county"]
            if county != "":
                self.countyDict.setdefault(county, []).append(thisSightingDict)

            # add sighting to locationDict
            # use location name as key
            location = thisSightingDict["location"]
            self.locationDict.setdefault(location, []).append(thisSightingDict)
            
            # get just the location data from this particular sighting
            # thisMasterLocationEntry = [country, state, county, location]
            thisMasterLocationEntry = {
                "regionCodes": regionCodes,
                "countryCode": countryCode,
                "stateCode": stateCode,
                "county": county,
                "location": location,
            }

            # if this location isn't already in the list, add it
            # we use this list later for populating the filter list of countries, states, counties, locations
            if location not in self._seenLocations:
                self._seenLocations.add(location)
                self.masterLocationList.append(thisMasterLocationEntry)
                for r in regionCodes:
                    self.regionList.append(self.GetRegionName(r))
                self.countryList.append(countryCode)
                self.stateList.append(stateCode)
                if county != "":
                    self.countyList.append(county)
                self.locationList.append(location)
                loc_id = thisSightingDict.get("locationID", "")
                if loc_id:
                    self.locationIDDict[location] = loc_id
                
            self.sightingList.append(thisSightingDict)

        if progress_callback:
            progress_callback(100)

        csvfile.close()
        
        # use set function to remove duplicates and then return to a list
        self.allSpeciesList = list(set(self.allSpeciesList))
        self.regionList = list(set(self.regionList))
        self.countryList = list(set(self.countryList))
        self.stateList = list(set(self.stateList))
        self.locationList = list(set(self.locationList))

        # sort 'em 
        self.regionList.sort()
        self.locationList.sort()
        self.countryList.sort()
        self.stateList.sort()
        # self.masterLocationList.sort()
        
        # remove parenthetical state names from counties, unless needed to
        # differentiate counties with same name in different states
        countyNamesWithoutParens = Counter(cdk.split(" (")[0] for cdk in self.countyDict.keys())
        countyKeyChanges = []

        for cdk in self.countyDict.keys():
            if countyNamesWithoutParens[cdk.split(" (")[0]] == 1:
                for s in self.countyDict[cdk]:
                    s["county"] = cdk.split(" (")[0]
                countyKeyChanges.append([cdk, cdk.split(" (")[0]])
        
        for ckc in countyKeyChanges:
            self.countyDict[str(ckc[1])] = self.countyDict.pop(str(ckc[0]))
            for ml in self.masterLocationList:
                if ml["county"] == str(ckc[0]):
                    ml["county"] = str(ckc[1])
            
        self.countyList = list(self.countyDict.keys())
        self.countyList.sort()

        # set flat indicating that a data file is now open
        self.eBirdFileOpenFlag = True
        self.eBirdFilePath = DataFile


    def ReadTaxonomyDataFile(self, taxonomyDataFile):

        # open the CSV taxonomy file and build a dict keyed by SCI_NAME for O(1) lookup
        # utf-8-sig strips the UTF-8 BOM so the first column name is 'TAXON_ORDER', not '﻿TAXON_ORDER'
        with open(taxonomyDataFile, "r", encoding='utf-8-sig', errors='replace') as csvfile:
            csvdata = csv.DictReader(csvfile, delimiter=',', quotechar='"')
            taxDict = {row["SCI_NAME"]: row for row in csvdata}

        # determine which column name this file uses for taxonomic order
        firstRow = next(iter(taxDict.values())) if taxDict else {}
        orderCol = "ORDER1" if "ORDER1" in firstRow else "ORDER"

        # track minimum TAXON_ORDER per family/order for taxonomic sorting
        familyTaxonOrder = {}   # family -> min TAXON_ORDER float
        orderTaxonOrder  = {}   # order  -> min TAXON_ORDER float
        masterFamilyOrderSet = set()

        # loop through sighting list to get each species and add order and family
        thisSciName = ""
        thisOrder = ""
        thisFamily = ""
        thisQuickEntryCode = ""

        for s in self.sightingList:

            # if this species already has order/family found, no need to search again
            if thisSciName != s["scientificName"]:

                taxEntry = taxDict.get(s["scientificName"])
                if taxEntry:
                    thisSciName = taxEntry["SCI_NAME"]
                    thisOrder = taxEntry[orderCol]
                    thisFamily = taxEntry["FAMILY"]
                    thisQuickEntryCode = taxEntry["SPECIES_CODE"]
                    self.eBirdCodeDict[thisSciName] = thisQuickEntryCode

                    try:
                        taxon_order = float(taxEntry.get("TAXON_ORDER", 0))
                    except (ValueError, TypeError):
                        taxon_order = 0.0
                    if thisFamily and (thisFamily not in familyTaxonOrder or taxon_order < familyTaxonOrder[thisFamily]):
                        familyTaxonOrder[thisFamily] = taxon_order
                    if thisOrder and (thisOrder not in orderTaxonOrder or taxon_order < orderTaxonOrder[thisOrder]):
                        orderTaxonOrder[thisOrder] = taxon_order
                    masterFamilyOrderSet.add((thisFamily, thisOrder))

                    # add species to orderSpeciesDict
                    if thisOrder not in self.orderSpeciesDict:
                        self.orderSpeciesDict[thisOrder] = [s["commonName"]]
                    else:
                        self.orderSpeciesDict[thisOrder].append(s["commonName"])

                    # add species to familySpeciesDict
                    if thisFamily not in self.familySpeciesDict:
                        self.familySpeciesDict[thisFamily] = [s["commonName"]]
                    else:
                        self.familySpeciesDict[thisFamily].append(s["commonName"])

            # append the order and family names to the sighting
            s["order"] = thisOrder
            s["family"] = thisFamily
            s["quickEntryCode"] = thisQuickEntryCode

            # populate orderDict and familyDict for fast filtering
            if thisOrder:
                self.orderDict.setdefault(thisOrder, []).append(s)
            if thisFamily:
                self.familyDict.setdefault(thisFamily, []).append(s)

        # sort by taxonomic order and store
        self.familyList = sorted(familyTaxonOrder.keys(), key=lambda f: familyTaxonOrder[f])
        self.orderList  = sorted(orderTaxonOrder.keys(),  key=lambda o: orderTaxonOrder[o])
        self.masterFamilyOrderList = [[f, o] for f, o in masterFamilyOrderSet]

        # persist full sci-name → taxon-order mapping for community sightings sorting
        self.taxonOrderBySciName = {}
        for _sci, _row in taxDict.items():
            try:
                _to = float(_row.get("TAXON_ORDER", 0))
                if _to:
                    self.taxonOrderBySciName[_sci] = _to
            except (ValueError, TypeError):
                pass


    def ReadBBLCodeFile(self, bblFile):

        # initialize variable to hold the csv data from the BBL Code file
        # open the CSV taxonomy file, using "replace" for any problematic characters
        with open(bblFile, "r", errors='replace') as csvfile:
            csvdata = csv.reader(csvfile, delimiter=',', quotechar='"')
            # store the BBL code in a dictionary, using the sci name as the key
            for row in csvdata:
                self.bblCodeDict[str(row[2]).strip()] = row[0].strip()                    
        
                
    def GetFamilies(self, filter, filteredSightingList=[]):
        familiesList = []

        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        # for each sighting, test date if necessary. Append new dates to return list.
        # don't consider spuh or slash species
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            if "sp." not in s["commonName"] and "/" not in s["commonName"] and " x " not in s["commonName"]:
                if self.TestSightingCompiled(s, cf) is True:
                    if s["family"] not in familiesList:
                        familiesList.append(s["family"])

        return(familiesList)

    def GetSightings(self, filter):
        returnList = []

        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            # this is not a single checklist, so remove spuh and slash sightings
            if filter.getChecklistID() == "":
                commonName = s["commonName"]
                # if "/" not in commonName and "sp." not in commonName:
                if self.TestSightingCompiled(s, cf) is True:
                    returnList.append(s)
            else:
                # this is a single checklist, so allow spuh and slash sightings
                if self.TestSightingCompiled(s, cf) is True:
                    returnList.append(s)

        return(returnList)


    def GetSpeciesWithPhotos(self, filter):
        returnSet = set()

        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            commonName = s["commonName"]
            if "/" not in commonName and "sp." not in commonName:
                if self.TestSightingCompiled(s, cf) is True:
                    if "photos" in s:
                        returnSet.add(s["commonName"])

        return(returnSet)


    def GetSpeciesWithoutPhotos(self, filter):
        
        unphotographedSpeciesSet = set()

        photographedSpeciesSet = self.GetSpeciesWithPhotos(filter)

        for species in self.allSpeciesList:
            if species not in photographedSpeciesSet:
                unphotographedSpeciesSet.add(species)        
        
        return(unphotographedSpeciesSet)
    

    def GetSpeciesWithRecordings(self, filter):
        returnSet = set()
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            commonName = s["commonName"]
            if "/" not in commonName and "sp." not in commonName:
                if self.TestSightingCompiled(s, cf) is True:
                    if "audio" in s:
                        returnSet.add(commonName)
        return returnSet

    def GetSpeciesWithoutRecordings(self, filter):
        recordedSpeciesSet = self.GetSpeciesWithRecordings(filter)
        return {species for species in self.allSpeciesList if species not in recordedSpeciesSet}

    def GetSightingsWithPhotos(self, filter, progress_callback=None):
        returnList = []
        photosFound = set()

        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        cf = self.CompileFilter(filter)
        total = len(filteredSightingList)
        for i, s in enumerate(filteredSightingList):
            # Report progress periodically so the caller can drive a determinate
            # progress bar while we work through the catalog.
            if progress_callback is not None and i % 200 == 0:
                progress_callback(i, total)
            commonName = s["commonName"]
            # if "/" not in commonName and "sp." not in commonName:
            if self.TestSightingCompiled(s, cf) is True:
                if "photos" in s:
                    if s["photos"][0]["fileName"] not in photosFound:
                        photosFound.add(s["photos"][0]["fileName"])
                        returnList.append(s)
        if progress_callback is not None:
            progress_callback(total, total)

        returnList = sorted(returnList, key=lambda x: (float(x["taxonomicOrder"]), x["date"], x["time"]))

        return(returnList)


    def hasPhotos(self):
        """True if any sighting in the loaded catalog has at least one photo."""
        return any(s.get("photos") for s in self.sightingList)

    def hasRecordings(self):
        """True if any sighting in the loaded catalog has at least one recording."""
        return any(s.get("audio") for s in self.sightingList)

    def GetPhotos(self, filter):
        returnList = []

        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        for s in filteredSightingList:
            if "photos" in s:
                for p in s["photos"]:
                    if p["fileName"] not in returnList:
                        returnList.append(p["fileName"])
        
        returnList.sort()
        
        return(returnList)


    def GetSightingsWithRecordings(self, filter):
        returnList = []
        audioFound = set()
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            if self.TestSightingCompiled(s, cf):
                if "audio" in s:
                    if s["audio"][0]["fileName"] not in audioFound:
                        audioFound.add(s["audio"][0]["fileName"])
                        returnList.append(s)
        returnList = sorted(returnList, key=lambda x: (float(x["taxonomicOrder"]), x["date"], x["time"]))
        return returnList

    def GetSightingsByRecordingFile(self, filter):
        """Return {filename: [sighting, ...]} for all sightings with audio matching filter.

        Each file maps to every sighting it is associated with, sorted by
        taxonomic order.  Files are ordered by the taxonomic order of their
        first (lowest-ranked) species.
        """
        result = {}
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            if self.TestSightingCompiled(s, cf):
                if "audio" in s:
                    for a in s["audio"]:
                        fn = a["fileName"]
                        if fn not in result:
                            result[fn] = []
                        if s not in result[fn]:
                            result[fn].append(s)
        for fn in result:
            result[fn].sort(key=lambda x: float(x["taxonomicOrder"]))
        return dict(sorted(result.items(),
                           key=lambda kv: float(kv[1][0]["taxonomicOrder"])))

    def GetAudio(self, filter):
        returnList = []
        filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
        for s in filteredSightingList:
            if "audio" in s:
                for a in s["audio"]:
                    if a["fileName"] not in returnList:
                        returnList.append(a["fileName"])
        returnList.sort()
        return returnList

    def GetSpecies(self, filter, filteredSightingList=[]):
        speciesList = []

        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)

        # for each sighting, test filter. Append filtered species to return list.
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            if self.TestSightingCompiled(s, cf) is True:
                if s["commonName"] not in speciesList:
                    speciesList.append(s["commonName"])

        return(speciesList)


    def GetMinimalFilteredSightingsList(self, filter):

        returnList = []
        speciesName = filter.getSpeciesName()
        speciesList = filter.getSpeciesList()
        startDate = filter.getStartDate()
        endDate = filter.getEndDate()
        locationType = filter.getLocationType()
        locationName = filter.getLocationName()
        checklistID = filter.getChecklistID()
        order = filter.getOrder()
        family = filter.getFamily()
        commonNameSearch = filter.getCommonNameSearch()

        # if we're dealing with a sp. or slash species,
        # we need to return the whole database since those sightings
        # aren't in dictionaries
        if "sp." in speciesName or "/" in speciesName:
            return(self.sightingList)

        # use narrowest subset possible, according to filter
        if checklistID != "":
            returnList = self.checklistDict[checklistID]
        elif speciesName != "" and speciesName in self.speciesDict:
            returnList = self.speciesDict[speciesName]
        elif speciesList != []:
            for sp in speciesList:
                for s in self.speciesDict[sp]:
                    returnList.append(s)
        elif startDate != "" and startDate == endDate:
            if startDate in self.dateDict:
                returnList = self.dateDict[startDate]
            else:
                returnList = []
        elif startDate != "" and endDate != "":
            startYear = startDate[:4]
            endYear = endDate[:4]
            if startYear == endYear:
                returnList = self.yearDict.get(startYear, [])
            else:
                for y in range(int(startYear), int(endYear) + 1):
                    returnList.extend(self.yearDict.get(str(y), []))
        elif locationType == "Country":
            returnList = self.countryDict[locationName]
        elif locationType == "State":
            returnList = self.stateDict[locationName]
        elif locationType == "County":
            returnList = self.countyDict[locationName]
        elif locationType == "Location" and locationName in self.locationDict:
            returnList = self.locationDict[locationName]
        elif commonNameSearch != "" and "s:" not in commonNameSearch:
            # Name Search (substring on the common/subspecies name): instead of
            # scanning every sighting, scan the far smaller set of species names
            # in speciesDict and gather the sightings of matching species.  A
            # sighting is filed under both its common and subspecies name, so
            # dedupe by object identity.  Placed below the more-specific date /
            # location dimensions (so those still win when set) but above the
            # broad order / family fallbacks and the whole-database else.
            # Scientific-name searches ("s:" prefix) fall through, since
            # speciesDict is not keyed by sci-name; the per-sighting test still
            # validates the full filter in every case.
            needle = commonNameSearch.lower()
            seen = set()
            for speciesName_key, speciesSightings in self.speciesDict.items():
                if needle in speciesName_key.lower():
                    for s in speciesSightings:
                        if id(s) not in seen:
                            seen.add(id(s))
                            returnList.append(s)
        elif order != "" and order in self.orderDict:
            returnList = self.orderDict[order]
        elif family != "" and family in self.familyDict:
            returnList = self.familyDict[family]
        else:
            returnList = self.sightingList

        return(returnList)

    def GetSpeciesWithData(self, filter, filteredSightingList=[], includeSpecies="Species"):
        filteredDictWithDates = {}
        checklistIDs = {}
        returnList = []
        allChecklists = set()
        
        # if no filteredSightingList is specified, create one.
        # use narrowest subset possible, according to filter            
        if filteredSightingList == []:

            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            
        # loop through sightingList and check each sighting for the filtered list criteria
        cf = self.CompileFilter(filter)
        for sighting in filteredSightingList:

            if self.TestSightingCompiled(sighting, cf) is True:
                
                # store the sighting date so we can get first and last later
                # include the taxonomy entry so we can sort the list by taxonomy later
                # include the main species name so we can store it in SpeciesList hidden data
                # include the checklist number so we can count checklists for each species
                thisDateTaxSpecies = [sighting["date"], sighting["taxonomicOrder"], sighting["commonName"], sighting["checklistID"], sighting["count"]]
                
                # decide whether we're returning only species or also subspecies
                if includeSpecies == "Species":
                    key = sighting["commonName"]
                if includeSpecies == "Subspecies":
                    key = sighting["subspeciesName"]
                
                # add the date and taxonomy number to a temp dictionary 
                # we'll use this dictionary later to find the first and last dates
                if key not in filteredDictWithDates:
                    filteredDictWithDates[key] = [thisDateTaxSpecies]
                else:
                    filteredDictWithDates[key].append(thisDateTaxSpecies)

                # add the checklist ID to a temp dictionary
                # we'll use this dictionary later to sum the checklists per species
                if key not in checklistIDs:
                    checklistIDs[key] = [thisDateTaxSpecies[3]]
                else:
                    checklistIDs[key].append(thisDateTaxSpecies[3])       
       
                # add checklistID to allChecklist set so we can count all the checklists later
                allChecklists.add(sighting["checklistID"])
    
        # get the total number of checklists so we can compute percentages 
        # of checklists for each species
        allChecklistCount = len(allChecklists)
        
        if len(filteredDictWithDates) > 0:            
            
            # initiate currentSpeciesIndex with data from first element in filteredListWithDates
            for s in filteredDictWithDates.keys():
                tempSpeciesList = filteredDictWithDates[s]
                tempSpeciesList.sort()
                thisCommonName = s
                thisFirstDate = tempSpeciesList[0][0]
                thisLastDate = tempSpeciesList[len(tempSpeciesList) - 1][0]
                thisTaxNumber = float(tempSpeciesList[0][1])
                thisTopLevelSpeciesName = tempSpeciesList[0][2]
                thisChecklistCount = len(checklistIDs[s])
                percentageOfChecklists = round(100 * thisChecklistCount / allChecklistCount, 2)
                
                # count up the number of individuals seen
                count = 0
                for sighting in tempSpeciesList:
                    if sighting[4] == "X" or count == "X":
                        count = "X"
                    else:
                        count = count + int(sighting[4])
                
                returnList.append([
                    thisCommonName,
                    thisFirstDate,
                    thisLastDate,
                    thisTaxNumber,
                    thisTopLevelSpeciesName,
                    thisChecklistCount,
                    percentageOfChecklists,
                    count
                    ])
                
        returnList = sorted(returnList, key=lambda x: (x[3]))
        
        return(returnList)

    def GetUniqueSpeciesForLocation(self, filter, location, speciesList, filteredSightingList=[],):
        uniqueSpeciesList = []

        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightings(filter)

        # for each sighting, test date if necessary. Append new dates to return list.
        cf = self.CompileFilter(filter)
        for species in speciesList:
            isSeenNowhereElse = True
            for s in filteredSightingList:
                if self.TestSightingCompiled(s, cf) is True:
                    if s["commonName"] == species and s["location"] != location:
                        isSeenNowhereElse = False
                        break

            if isSeenNowhereElse == True:
                if species not in uniqueSpeciesList:
                    uniqueSpeciesList.append(species)

        return(uniqueSpeciesList)


    def TestIndividualPhoto(self, photoData, filter):

        filterCamera = filter.getCamera()
        filterLens = filter.getLens()
        filterStartShutterSpeed = filter.getStartShutterSpeed()
        filterEndShutterSpeed = filter.getEndShutterSpeed()
        filterStartAperture = filter.getStartAperture()
        filterEndAperture = filter.getEndAperture()
        filterStartFocalLength = filter.getStartFocalLength()
        filterEndFocalLength = filter.getEndFocalLength()
        filterStartIso = filter.getStartIso()
        filterEndIso = filter.getEndIso()
        filterStartRating = filter.getStartRating()
        filterEndRating = filter.getEndRating()

        # Cache photo attribute values once to avoid repeated dict lookups
        photoCamera = photoData["camera"]
        photoLens = photoData["lens"]
        photoShutterSpeed = photoData["shutterSpeed"]
        photoAperture = photoData["aperture"]
        photoISO = photoData["iso"]
        photoFocalLength = photoData["focalLength"]
        photoRating = photoData["rating"]

        # check photo settings
        # note that a sighting can have several attached photos
        # we only reject a sighting here if all attached photos fail

        if filterCamera != "":
            if photoCamera != filterCamera:
                return(False)

        if filterLens != "":
            if photoLens != filterLens:
                return(False)

        if filterStartShutterSpeed != "" and filterEndShutterSpeed != "":
            # strip away the 1/ characters at start of shutter speeds
            filterStartShutterSpeed = int(filterStartShutterSpeed[2:])
            filterEndShutterSpeed = int(filterEndShutterSpeed[2:])
            filterStartShutterSpeed, filterEndShutterSpeed = max(filterStartShutterSpeed, filterEndShutterSpeed), min(filterStartShutterSpeed, filterEndShutterSpeed)
            if photoShutterSpeed != "":
                shutterSpeed = int(photoShutterSpeed[2:])
                if not (shutterSpeed <= filterStartShutterSpeed and shutterSpeed >= filterEndShutterSpeed):
                    return(False)
            else:
                return(False)

        if filterStartShutterSpeed != "" and filterEndShutterSpeed == "":
            # strip away the 1/ characters at start of shutter speeds
            filterStartShutterSpeed = int(filterStartShutterSpeed[2:])
            if photoShutterSpeed != "":
                shutterSpeed = int(photoShutterSpeed[2:])
                if shutterSpeed > filterStartShutterSpeed:
                    return(False)
            else:
                return(False)

        if filterStartShutterSpeed == "" and filterEndShutterSpeed != "":
            # strip away the 1/ characters at start of shutter speeds
            filterEndShutterSpeed = int(filterEndShutterSpeed[2:])
            if photoShutterSpeed != "":
                shutterSpeed = int(photoShutterSpeed[2:])
                if shutterSpeed < filterEndShutterSpeed:
                    return(False)
            else:
                return(False)

        if filterStartAperture != "" and filterEndAperture != "":
            filterStartAperture = float(filterStartAperture)
            filterEndAperture = float(filterEndAperture)
            filterStartAperture, filterEndAperture = min(filterStartAperture, filterEndAperture), max(filterStartAperture, filterEndAperture)
            if photoAperture != "":
                aperture = float(photoAperture)
                if aperture < filterStartAperture or aperture > filterEndAperture:
                    return(False)
            else:
                return(False)

        if filterStartAperture != "" and filterEndAperture == "":
            filterStartAperture = float(filterStartAperture)
            if photoAperture != "":
                aperture = float(photoAperture)
                if aperture < filterStartAperture:
                    return(False)
            else:
                return(False)

        if filterStartAperture == "" and filterEndAperture != "":
            filterEndAperture = float(filterEndAperture)
            if photoAperture != "":
                aperture = float(photoAperture)
                if aperture > filterEndAperture:
                    return(False)
            else:
                return(False)

        if filterStartIso != "" and filterEndIso != "":
            filterStartIso = int(filterStartIso)
            filterEndIso = int(filterEndIso)
            filterStartIso, filterEndIso = min(filterStartIso, filterEndIso), max(filterStartIso, filterEndIso)
            if photoISO != "":
                iso = int(photoISO)
                if iso < filterStartIso or iso > filterEndIso:
                    return(False)
            else:
                return(False)

        if filterStartIso != "" and filterEndIso == "":
            filterStartIso = int(filterStartIso)
            if photoISO != "":
                iso = int(photoISO)
                if iso < filterStartIso:
                    return(False)
            else:
                return(False)

        if filterStartIso == "" and filterEndIso != "":
            filterEndIso = int(filterEndIso)
            if photoISO != "":
                iso = int(photoISO)
                if iso > filterEndIso:
                    return(False)
            else:
                return(False)

        if filterStartFocalLength != "" and filterEndFocalLength != "":
            filterStartFocalLength = int(filterStartFocalLength.split(" mm")[0])
            filterEndFocalLength = int(filterEndFocalLength.split(" mm")[0])
            filterStartFocalLength, filterEndFocalLength = min(filterStartFocalLength, filterEndFocalLength), max(filterStartFocalLength, filterEndFocalLength)
            if photoFocalLength != "":
                focalLength = int(photoFocalLength.split(" mm")[0])
                if focalLength < filterStartFocalLength or focalLength > filterEndFocalLength:
                    return(False)
            else:
                return(False)

        if filterStartFocalLength != "" and filterEndFocalLength == "":
            filterStartFocalLength = int(filterStartFocalLength.split(" mm")[0])
            if photoFocalLength != "":
                focalLength = int(photoFocalLength.split(" mm")[0])
                if focalLength < filterStartFocalLength:
                    return(False)
            else:
                return(False)

        if filterStartFocalLength == "" and filterEndFocalLength != "":
            filterEndFocalLength = int(filterEndFocalLength.split(" mm")[0])
            if photoFocalLength != "":
                focalLength = int(photoFocalLength.split(" mm")[0])
                if focalLength > filterEndFocalLength:
                    return(False)
            else:
                return(False)

        if filterStartRating != "" and filterEndRating != "":
            filterStartRating = _safe_rating(filterStartRating)
            filterEndRating = _safe_rating(filterEndRating)
            filterStartRating, filterEndRating = min(filterStartRating, filterEndRating), max(filterStartRating, filterEndRating)
            if photoRating != "" and photoRating is not None:
                rating = _safe_rating(photoRating)
                if rating < filterStartRating or rating > filterEndRating:
                    return(False)
            else:
                return(False)

        if filterStartRating != "" and filterEndRating == "":
            filterStartRating = _safe_rating(filterStartRating)
            if photoRating != "":
                rating = _safe_rating(photoRating)
                if rating < filterStartRating:
                    return(False)
            else:
                return(False)

        if filterStartRating == "" and filterEndRating != "":
            filterEndRating = _safe_rating(filterEndRating)
            if photoRating != "":
                rating = _safe_rating(photoRating)
                if rating > filterEndRating:
                    return(False)
            else:
                return(False)                    
                                         
        # if we've arrived here, the photo passes the filter. 
        return(True)

    
    def CompileFilter(self, filter):
        """Extract all filter parameters into a dict for use with TestSightingCompiled."""
        return {
            'locationType':       filter.getLocationType(),
            'locationName':       filter.getLocationName(),
            'startDate':          filter.getStartDate(),
            'endDate':            filter.getEndDate(),
            'startSeasonalMonth': filter.getStartSeasonalMonth(),
            'startSeasonalDay':   filter.getStartSeasonalDay(),
            'endSeasonalMonth':   filter.getEndSeasonalMonth(),
            'endSeasonalDay':     filter.getEndSeasonalDay(),
            'checklistID':        filter.getChecklistID(),
            'speciesName':        filter.getSpeciesName(),
            'speciesList':        filter.getSpeciesList(),
            'scientificName':     filter.getScientificName(),
            'order':              filter.getOrder(),
            'family':             filter.getFamily(),
            'time':               filter.getTime(),
            'commonNameSearch':   filter.getCommonNameSearch(),
            'sightingHasPhoto':   filter.getSightingHasPhoto(),
            'speciesHasPhoto':    filter.getSpeciesHasPhoto(),
            'validPhotoSpecies':  filter.getValidPhotoSpecies(),
            'camera':             filter.getCamera(),
            'lens':               filter.getLens(),
            'startShutterSpeed':  filter.getStartShutterSpeed(),
            'endShutterSpeed':    filter.getEndShutterSpeed(),
            'startAperture':      filter.getStartAperture(),
            'endAperture':        filter.getEndAperture(),
            'startFocalLength':   filter.getStartFocalLength(),
            'endFocalLength':     filter.getEndFocalLength(),
            'startIso':           filter.getStartIso(),
            'endIso':             filter.getEndIso(),
            'startRating':         filter.getStartRating(),
            'endRating':           filter.getEndRating(),
            'speciesHasRecording': filter.getSpeciesHasRecording(),
            'validRecordingSpecies':   filter.getValidRecordingSpecies(),
            'channels':            filter.getChannels(),
            'startRecordingRating':    filter.getStartRecordingRating(),
            'endRecordingRating':      filter.getEndRecordingRating(),
            'startDuration':       filter.getStartDuration(),
            'endDuration':         filter.getEndDuration(),
            'startSampleRate':     filter.getStartSampleRate(),
            'endSampleRate':       filter.getEndSampleRate(),
            'bitDepths':           filter.getBitDepths(),
            'device':              filter.getDevice(),
        }

    def TestSightingCompiled(self, sighting, cf):

        locationType = cf['locationType']
        locationName = cf['locationName']
        startDate = cf['startDate']
        endDate = cf['endDate']
        startSeasonalMonth = cf['startSeasonalMonth']
        startSeasonalDay = cf['startSeasonalDay']
        endSeasonalMonth = cf['endSeasonalMonth']
        endSeasonalDay = cf['endSeasonalDay']
        checklistID = cf['checklistID']
        sightingDate = sighting["date"]
        speciesName = cf['speciesName']
        speciesList = cf['speciesList']
        scientificName = cf['scientificName']
        order = cf['order']
        family = cf['family']
        time = cf['time']
        commonNameSearch = cf['commonNameSearch']

        sightingHasPhoto = cf['sightingHasPhoto']
        speciesHasPhoto = cf['speciesHasPhoto']
        validPhotoSpecies = cf['validPhotoSpecies']
        camera = cf['camera']
        lens = cf['lens']
        startShutterSpeed = cf['startShutterSpeed']
        endShutterSpeed = cf['endShutterSpeed']
        startAperture = cf['startAperture']
        endAperture = cf['endAperture']
        startFocalLength = cf['startFocalLength']
        endFocalLength = cf['endFocalLength']
        startIso = cf['startIso']
        endIso = cf['endIso']
        startRating = cf['startRating']
        endRating = cf['endRating']
        speciesHasRecording = cf['speciesHasRecording']
        validRecordingSpecies = cf['validRecordingSpecies']
        channels = cf['channels']
        startRecordingRating = cf['startRecordingRating']
        endRecordingRating = cf['endRecordingRating']
        startDuration = cf['startDuration']
        endDuration = cf['endDuration']
        startSampleRate = cf['startSampleRate']
        endSampleRate = cf['endSampleRate']
        bitDepths = cf['bitDepths']
        device = cf['device']

        # Check every filter setting. Return False immediately if sighting fails.
        # If sighting survives the filter, return True

        # if any photo settings have been specified, check whether sighting has photos
        # reject sighting if it doesn't have a photo
        if (
            sightingHasPhoto == "Has photo" or
            camera != "" or
            lens != "" or
            startShutterSpeed != "" or
            endShutterSpeed != "" or
            startAperture != "" or
            endAperture != "" or
            startFocalLength != "" or
            endFocalLength != "" or
            startIso != "" or
            endIso != "" or
            speciesHasPhoto == "Photographed" or
            startRating != "" or
            endRating != ""
            ):
            if "photos" not in sighting:
                return(False)

        # reject if "no photo" was specified but sighting has photo
        if sightingHasPhoto == "No photo":
            if "photos" in sighting:
                return(False)

        # if user selected a value for whether a species has a photo,
        # check if commonName is in the supplied set.
        # if we're checking for "Photographed," the supplied set contains photographed species
        # if we're checking for "Not pPhotographed," the supplied set contains UNphotographed species
        if validPhotoSpecies != []:
            if sighting["commonName"] not in validPhotoSpecies:
                return(False)

        # if a commonNameSearch string has been specified, check if sighting matches
        if commonNameSearch != "":
            # check to see if s: prepends the search, in which case we need to search sci name
            if "s:" in commonNameSearch:
                commonNameSearch = commonNameSearch.strip()
                if len(commonNameSearch) > 2:
                    if commonNameSearch[0:2].lower() == "s:":
                        sciNameSearch = commonNameSearch[2:]
                        if sciNameSearch.lower() not in sighting["scientificName"].lower():
                            return(False)
                    else:
                        return(False)
                else:
                    return(False)

            else:
                if commonNameSearch.lower() not in sighting["commonName"].lower():
                    if commonNameSearch.lower() not in sighting["subspeciesName"].lower():
                        return(False)

        # if a checklistID has been specified, check if sighting matches
        if checklistID != "":
            if checklistID != sighting["checklistID"]:
                return(False)

        # if speciesName has been specified, check it
        if speciesName != "":
            if speciesName != sighting["commonName"] and speciesName != sighting["subspeciesName"]:
                return(False)

        # if scientificName has been specified, check it
        if scientificName != "":
            if scientificName != sighting["scientificName"]:
                return(False)

        # if order  has been specified, check it
        if order != "":
            if order != sighting["order"]:
                return(False)

        # if family  has been specified, check it
        if family != "":
            if family != sighting["family"]:
                return(False)

        # if speciesList has been specified, check it
        if speciesList != []:
            if sighting["commonName"] not in speciesList:
                return(False)

        # if time has been specified, check it
        # don't try checking if sighting is an historical sighting without a time
        if time != "" and sighting["time"] != "":
            # if time exactly matches sighting start time, it passes the filter test
            # if time doesn't match exactly, check whether time is between start time and end time
            if time != sighting["time"]:

                # now use DateTime functions so we can add duration minutes to find end time efficiently
                # adding duration minutes could take us to a new hour, day, month, or year
                durationMinutes = sighting["duration"]
                if durationMinutes is None or durationMinutes == "":
                    durationMinutes = 0
                else:
                    durationMinutes = int(durationMinutes)

                filterDateTime = datetime.datetime(int(startDate[0:4]), int(startDate[5:7]), int(startDate[8:10]), int(time[0:2]), int(time[3:5]))

                sightingStartDateTime = datetime.datetime(int(sightingDate[0:4]), int(sightingDate[5:7]), int(sightingDate[8:10]), int(sighting["time"][0:2]), int(sighting["time"][3:5]))

                sightingTimeDelta = datetime.timedelta(0, 0, 0, 0, durationMinutes)
                sightingEndDateTime = sightingStartDateTime + sightingTimeDelta

                if not ((sightingStartDateTime <= filterDateTime) and (filterDateTime <= sightingEndDateTime)):

                    return(False)

        # check if location matches for sighting; flag species that fit the location
        # no need to check if locationType is ""
        if not locationType == "":
            if locationType == "Region":
                if not locationName in sighting["regionCodes"]:
                    return(False)
            if locationType == "Country":
                if not locationName == sighting["country"]:
                    return(False)
            if locationType == "State":
                if not locationName == sighting["state"]:
                    return(False)
            if locationType == "County":
                if not locationName == sighting["county"]:
                    return(False)
            if locationType == "Location":
                if not locationName == sighting["location"]:
                    return(False)

        # check date for matches for sighting range or seasonal range; disqualify sighting if date doesn't fit specific date range
        if not ((startDate == "") or (endDate == "")):
            # if sightingDate is before start date
            if sightingDate < startDate:
                return(False)
            # if sightingDate is after end date
            if sightingDate > endDate:
                return(False)

        # check for seasonal range using month and date parts; disqualify sighting if date doesn't fit in seasonal range
        if not ((startSeasonalMonth == "") or (endSeasonalMonth == "")):
            sightingMonth = sightingDate[5:7]
            sightingDay = sightingDate[8:]
            # if startSeasonalMonth is earlier than endSeasonalMonth (e.g., July to October)
            if startSeasonalMonth < endSeasonalMonth:
                if sightingMonth < startSeasonalMonth:
                    return(False)
                if sightingMonth > endSeasonalMonth:
                    return(False)
                if sightingMonth == startSeasonalMonth:
                    if sightingDay < startSeasonalDay:
                        return(False)
                if sightingMonth == endSeasonalMonth:
                    if sightingDay > endSeasonalDay:
                        return(False)
            # if endSeasonalMonth is earlier than startSeasonalMonth (e.g., October to February)
            if startSeasonalMonth > endSeasonalMonth:
                if sightingMonth < startSeasonalMonth:
                    if sightingMonth > endSeasonalMonth:
                        return(False)
                if sightingMonth == startSeasonalMonth:
                    if sightingDay < startSeasonalDay:
                        return(False)
                if sightingMonth == endSeasonalMonth:
                    if sightingDay > endSeasonalDay:
                        return(False)
            # if endSeasonalMonth is same as startSeasonalMonth (e.g., October and October)
            if startSeasonalMonth == endSeasonalMonth:
                if startSeasonalDay < endSeasonalDay:
                    if not sightingMonth == startSeasonalMonth:
                        return(False)
                    if sightingDay < startSeasonalDay:
                        return(False)
                    if sightingDay > endSeasonalDay:
                        return(False)
                if startSeasonalDay > endSeasonalDay:
                    if sightingMonth < startSeasonalMonth:
                        if sightingMonth > endSeasonalMonth:
                            return(False)
                    if sightingMonth == startSeasonalMonth:
                        if sightingDay > startSeasonalDay:
                            if sightingDay < endSeasonalDay:
                                return(False)
                if startSeasonalDay == endSeasonalDay:
                    if not sightingDay == startSeasonalDay:
                        return(False)
                    if not sightingMonth == startSeasonalMonth:
                        return(False)

        # check photo settings
        # note that a sighting can have several attached photos
        # we only reject a sighting here if all attached photos fail
        # For each sighting, test each photo. If any photo passes filter, the sighting passes filter

        if camera != "":
            cameraOK = False
            for p in sighting["photos"]:
                if camera == p["camera"]:
                    cameraOK = True
            if cameraOK is False:
                return(False)

        if lens != "":
            lensOK = False
            for p in sighting["photos"]:
                if lens == p["lens"]:
                    lensOK= True
            if lensOK is False:
                return(False)

        if startShutterSpeed != "" and endShutterSpeed == "":
            shutterSpeedOK = False
            filterStartShutterSpeed = startShutterSpeed[2:]
            filterStartShutterSpeed = float(filterStartShutterSpeed)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                shutterSpeed = p["shutterSpeed"]
                if shutterSpeed != "":
                    shutterSpeed = shutterSpeed[2:]
                    shutterSpeed = float(shutterSpeed)
                    if shutterSpeed <= filterStartShutterSpeed:
                        shutterSpeedOK= True
            if shutterSpeedOK is False:
                return(False)

        if startShutterSpeed == "" and endShutterSpeed != "":
            shutterSpeedOK = False
            filterEndShutterSpeed = endShutterSpeed[2:]
            filterEndShutterSpeed = float(filterEndShutterSpeed)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                shutterSpeed = p["shutterSpeed"]
                if shutterSpeed != "":
                    shutterSpeed = shutterSpeed[2:]
                    shutterSpeed = float(shutterSpeed)
                    if shutterSpeed >= filterEndShutterSpeed:
                        shutterSpeedOK= True
            if shutterSpeedOK is False:
                return(False)

        if endShutterSpeed != "" and startShutterSpeed != "":
            shutterSpeedOK= False
            filterStartShutterSpeed = startShutterSpeed[2:]
            filterStartShutterSpeed = float(filterStartShutterSpeed)
            filterEndShutterSpeed = endShutterSpeed[2:]
            filterEndShutterSpeed = float(filterEndShutterSpeed)
            filterStartShutterSpeed, filterEndShutterSpeed = max(filterStartShutterSpeed, filterEndShutterSpeed), min(filterStartShutterSpeed, filterEndShutterSpeed)
            for p in sighting["photos"]:
                # convert the string to an integer
                shutterSpeed = p["shutterSpeed"]
                if shutterSpeed != "":
                    shutterSpeed = shutterSpeed[2:]
                    shutterSpeed = float(shutterSpeed)
                    if shutterSpeed <= filterStartShutterSpeed and shutterSpeed >= filterEndShutterSpeed:
                        shutterSpeedOK = True
            if shutterSpeedOK is False:
                return(False)

        if startAperture != "" and endAperture == "":
            apertureOK = False
            filterStartAperture = float(startAperture)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                aperture = p["aperture"]
                if aperture != "":
                    aperture = float(aperture)
                    if aperture >= filterStartAperture:
                        apertureOK= True
            if apertureOK is False:
                return(False)

        if startAperture == "" and endAperture != "":
            apertureOK = False
            filterEndAperture = float(endAperture)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                aperture = p["aperture"]
                if aperture != "":
                    aperture = float(aperture)
                    if aperture >= filterEndAperture:
                        apertureOK= True
            if apertureOK is False:
                return(False)

        if endAperture != "" and startAperture != "":
            apertureOK= False
            filterStartAperture = float(startAperture)
            filterEndAperture = float(endAperture)
            filterStartAperture, filterEndAperture = min(filterStartAperture, filterEndAperture), max(filterStartAperture, filterEndAperture)
            for p in sighting["photos"]:
                # convert the string to an integer
                aperture = p["aperture"]
                if aperture != "":
                    aperture = float(aperture)
                    if aperture >= filterStartAperture and aperture <= filterEndAperture:
                        apertureOK = True
            if apertureOK is False:
                return(False)

        if startIso != "" and endIso == "":
            isoOK = False
            filterStartIso = int(startIso)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                iso = p["iso"]
                if iso != "":
                    iso = int(iso)
                    if iso >= filterStartIso:
                        isoOK= True
            if isoOK is False:
                return(False)

        if startIso == "" and endIso != "":
            isoOK = False
            filterEndIso = int(endIso)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                iso = p["iso"]
                if iso != "":
                    iso = int(iso)
                    if iso <= filterEndIso:
                        isoOK= True
            if isoOK is False:
                return(False)

        if endIso != "" and startIso != "":
            isoOK= False
            filterStartIso = int(startIso)
            filterEndIso = int(endIso)
            filterStartIso, filterEndIso = min(filterStartIso, filterEndIso), max(filterStartIso, filterEndIso)
            for p in sighting["photos"]:
                # convert the string to an integer
                iso = p["iso"]
                if iso != "":
                    iso = int(iso)
                    if iso >= filterStartIso and iso <= filterEndIso:
                        isoOK = True
            if isoOK is False:
                return(False)

        if startFocalLength != "" and endFocalLength == "":
            focalLengthOK = False
            filterStartFocalLength = startFocalLength.split(" mm")[0]
            filterStartFocalLength = int(filterStartFocalLength)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                focalLength = p["focalLength"]
                if focalLength != "":
                    focalLength = focalLength.split(" mm")[0]
                    focalLength = int(focalLength)
                    if focalLength >= filterStartFocalLength:
                        focalLengthOK= True
            if focalLengthOK is False:
                return(False)

        if startFocalLength == "" and endFocalLength != "":
            focalLengthOK = False
            filterEndFocalLength = endFocalLength.split(" mm")[0]
            filterEndFocalLength = int(filterEndFocalLength)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                focalLength = p["focalLength"]
                if focalLength != "":
                    focalLength = focalLength.split(" mm")[0]
                    focalLength = int(focalLength)
                    if focalLength <= filterEndFocalLength:
                        focalLengthOK= True
            if focalLengthOK is False:
                return(False)

        if endFocalLength != "" and startFocalLength != "":
            focalLengthOK= False
            filterStartFocalLength = startFocalLength.split(" mm")[0]
            filterStartFocalLength = int(filterStartFocalLength)
            filterEndFocalLength = endFocalLength.split(" mm")[0]
            filterEndFocalLength = int(filterEndFocalLength)
            filterStartFocalLength, filterEndFocalLength = min(filterStartFocalLength, filterEndFocalLength), max(filterStartFocalLength, filterEndFocalLength)
            for p in sighting["photos"]:
                # convert the string to an integer
                focalLength = p["focalLength"]
                if focalLength != "":
                    focalLength = focalLength.split(" mm")[0]
                    focalLength = int(focalLength)
                    if focalLength >= filterStartFocalLength and focalLength <= filterEndFocalLength:
                        focalLengthOK = True
            if focalLengthOK is False:
                return(False)

        if startRating != "" and endRating == "":
            ratingOK = False
            filterStartRating = _safe_rating(startRating)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                rating = p["rating"]
                if rating != "":
                    rating = _safe_rating(rating)
                    if rating >= filterStartRating:
                        ratingOK= True
            if ratingOK is False:
                return(False)

        if startRating == "" and endRating != "":
            ratingOK = False
            filterEndRating = _safe_rating(endRating)
            # check each photo and set flag to true if at least one photo passes test
            # reject if all photos fail this test
            for p in sighting["photos"]:
                rating = p["rating"]
                if rating != "":
                    rating = _safe_rating(rating)
                    if rating >= filterEndRating:
                        ratingOK= True
            if ratingOK is False:
                return(False)

        if endRating != "" and startRating != "":
            ratingOK= False
            filterStartRating = _safe_rating(startRating)
            filterEndRating = _safe_rating(endRating)
            filterStartRating, filterEndRating = min(filterStartRating, filterEndRating), max(filterStartRating, filterEndRating)
            for p in sighting["photos"]:
                rating = p["rating"]
                if rating != "":
                    rating = _safe_rating(rating)
                    if rating >= filterStartRating and rating <= filterEndRating:
                        ratingOK = True
            if ratingOK is False:
                return(False)

        # check audio settings
        if (
            speciesHasRecording == "Recorded" or
            channels != "" or
            startRecordingRating != "" or
            endRecordingRating != "" or
            startDuration != "" or
            endDuration != "" or
            startSampleRate != "" or
            endSampleRate != "" or
            bitDepths != [] or
            device != ""
        ):
            if "audio" not in sighting:
                return False

        if speciesHasRecording == "Not recorded":
            if "audio" in sighting:
                return False

        if validRecordingSpecies != []:
            if sighting["commonName"] not in validRecordingSpecies:
                return False

        if "audio" in sighting:
            if startRecordingRating != "" and endRecordingRating == "":
                ratingOK = False
                filterStart = _safe_rating(startRecordingRating)
                for a in sighting["audio"]:
                    if _safe_rating(a.get("rating", "")) >= filterStart:
                        ratingOK = True
                if not ratingOK:
                    return False

            if startRecordingRating == "" and endRecordingRating != "":
                ratingOK = False
                filterEnd = _safe_rating(endRecordingRating)
                for a in sighting["audio"]:
                    if _safe_rating(a.get("rating", "")) <= filterEnd:
                        ratingOK = True
                if not ratingOK:
                    return False

            if startRecordingRating != "" and endRecordingRating != "":
                ratingOK = False
                lo = min(_safe_rating(startRecordingRating), _safe_rating(endRecordingRating))
                hi = max(_safe_rating(startRecordingRating), _safe_rating(endRecordingRating))
                for a in sighting["audio"]:
                    r = _safe_rating(a.get("rating", ""))
                    if lo <= r <= hi:
                        ratingOK = True
                if not ratingOK:
                    return False

            if channels != "":
                channelsOK = False
                for a in sighting["audio"]:
                    if a.get("channels", "") == channels:
                        channelsOK = True
                if not channelsOK:
                    return False

            def _dur_to_sec(dur_str):
                parts = dur_str.split(":")
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(parts[1])
                return 0

            if startDuration != "" and endDuration == "":
                durationOK = False
                filterSec = int(startDuration.rstrip("s"))
                for a in sighting["audio"]:
                    if a.get("duration", "") and _dur_to_sec(a["duration"]) >= filterSec:
                        durationOK = True
                if not durationOK:
                    return False

            if startDuration == "" and endDuration != "":
                durationOK = False
                filterSec = int(endDuration.rstrip("s"))
                for a in sighting["audio"]:
                    if a.get("duration", "") and _dur_to_sec(a["duration"]) <= filterSec:
                        durationOK = True
                if not durationOK:
                    return False

            if startDuration != "" and endDuration != "":
                durationOK = False
                sec1 = int(startDuration.rstrip("s"))
                sec2 = int(endDuration.rstrip("s"))
                lo, hi = min(sec1, sec2), max(sec1, sec2)
                for a in sighting["audio"]:
                    if a.get("duration", ""):
                        s = _dur_to_sec(a["duration"])
                        if lo <= s <= hi:
                            durationOK = True
                if not durationOK:
                    return False

            if startSampleRate != "" or endSampleRate != "":
                lo = _hz_from_rate_str(startSampleRate)
                hi = _hz_from_rate_str(endSampleRate)
                if lo is not None and hi is not None and lo > hi:
                    lo, hi = hi, lo
                rateOK = False
                for a in sighting["audio"]:
                    hz = _hz_from_rate_str(a.get("sampleRate", ""))
                    if hz is None:
                        continue
                    if (lo is None or hz >= lo) and (hi is None or hz <= hi):
                        rateOK = True
                if not rateOK:
                    return False

            if bitDepths != []:
                depthOK = False
                for a in sighting["audio"]:
                    if a.get("bitDepth", "") in bitDepths:
                        depthOK = True
                if not depthOK:
                    return False

            if device != "":
                # "Unknown" matches recordings with no device metadata.
                wanted = "" if device == "Unknown" else device
                deviceOK = False
                for a in sighting["audio"]:
                    if a.get("device", "") == wanted:
                        deviceOK = True
                if not deviceOK:
                    return False

        # if we've arrived here, the sighting passes the filter.
        return(True)

    def TestSighting(self, sighting, filter):
        return self.TestSightingCompiled(sighting, self.CompileFilter(filter))


    def GetDates(self, filter, filteredSightingList=[]):
        dateList = set()
        needToCheckFilter = False

        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            needToCheckFilter = True

        # for each sighting, test date if necessary. Append new dates to return list.
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            if needToCheckFilter is True:
                if self.TestSightingCompiled(s, cf) is True:
                    dateList.add(s["date"])
            else:
                dateList.add(s["date"])

        # convert the set to a list and sort it.
        dateList = list(dateList)
        dateList.sort()

        return(dateList)


    def GetStartTimes(self, filter, filteredSightingList=[]):
        timeList = set()
        needToCheckFilter = False

        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            needToCheckFilter = True

        # for each sighting, test time if necessary. Append new times to return list.
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:
            if needToCheckFilter is True:
                if self.TestSightingCompiled(s, cf) is True:
                    timeList.add(s["time"])
            else:
                timeList.add(s["time"])
        
        # convert the set to a list and sort it. 
        timeList = list(timeList)
        timeList.sort()
        
        return(timeList)
    
    def ClearDatabase(self):

        self.eBirdFileOpenFlag = False
        self.eBirdFilePath = ""
        self.photoDataFileOpenFlag = False
        self.photoDataFile = ""
        self.photoRecordsInCatalog = 0
        self.countryStateCodeFileFound = False
        self.allSpeciesList = []
        self.familyList = []
        self.masterLocationList = []
        self._seenLocations = set()
        self.countryList = []
        self.stateList = []
        self.countyList = []
        self.locationList = []
        self.sightingList = []
        self.speciesDict = {}
        self.yearDict = {}
        self.monthDict = {}
        self.dateDict = {}
        self.regionDict = {}
        self.countryDict = {}
        self.stateDict = {}
        self.countyDict = {}
        self.locationDict = {}
        self.locationIDDict = {}
        self.checklistDict = {}
        self.orderDict = {}
        self.familyDict = {}
        self._regionCache = {}

    def ClearPhotoSettings(self):

        self.jsonlSkippedLines = 0
        self.csvSkippedRows = 0
        self.photoRecordsInCatalog = 0
        self.cameraList = []
        self.lensList = []
        self.shutterSpeedList = []
        self.apertureList = []
        self.focalLengthList=[]
        self.isoList = []
        self.durationList = []
        self.sampleRateList = []
        self.bitDepthList = []
        self.deviceList = []

        # remove photo data from sightings
        for s in self.sightingList:
            if "photos" in s:
                del s["photos"]
                
        self.photoDataFileOpenFlag = False
        

    def GetChecklists(self, filter):
        returnList = []
        checklistIDs = set()
        
        # speed retreaval by choosing minimal set of sightings to search
        minimalSightingList = self.GetMinimalFilteredSightingsList(filter)

        # gather the IDs of checklists that match the filter
        cf = self.CompileFilter(filter)
        for s in minimalSightingList:
            if self.TestSightingCompiled(s, cf) is True:
                checklistIDs.add(s["checklistID"])
        
        # get all the sightings that match these checklistIDs
        for c in checklistIDs:
            
            # set up blank list to hold species names
            checklistSpecies = []
            
            # use the checklistDict to return sightings that match checklist ID
            for sighting in self.checklistDict[c]:
                
                # append species common name to list, so we can count the species
                checklistSpecies.append(sighting["commonName"])
                
            # count the species, discarding superfluous subspecies, spuhs and slashes when necessary
            speciesCount = self.CountSpecies(checklistSpecies)
            
            # compile data for checklist (id, state (which includes country prefix), county, location, date, time, speciesCount)
            checklistData = [
                sighting["checklistID"],
                sighting["state"],
                sighting["county"],
                sighting["location"],
                sighting["date"],
                sighting["time"],
                speciesCount,
                sighting["duration"]
                ]
            
            returnList.append(checklistData)    
            
        # sort by country, county, location, date, time
        returnList = sorted(returnList, key=lambda x: (x[1], x[2], x[3], x[4], x[5]))

        return(returnList)

    def GetFindResults(self, searchString, checkedBoxes):

        foundSet = set()
        searchLower = searchString.lower()

        for s in self.sightingList:
            for c in checkedBoxes:
                if c == "chkCommonName":
                    if searchLower in s["commonName"].lower():
                        foundSet.add(("Common Name", s["checklistID"], s["location"], s["date"], s["commonName"]))
                if c == "chkScientificName":
                    if searchLower in s["scientificName"].lower():
                        foundSet.add(("Scientific Name", s["checklistID"], s["location"], s["date"], s["scientificName"]))
                if c == "chkCountryName":
                    countryName = self.GetCountryName(s["country"])
                    if searchLower in countryName.lower():
                        foundSet.add(("Country", s["checklistID"], s["location"], s["date"], countryName))
                if c == "chkStateName":
                    stateName = self.GetStateName(s["state"])
                    if searchLower in stateName.lower():
                        foundSet.add(("State", s["checklistID"], s["location"], s["date"], stateName))
                if c == "chkCountyName":
                    if searchLower in s["county"].lower():
                        foundSet.add(("County", s["checklistID"], s["location"], s["date"], s["county"]))
                if c == "chkLocationName":
                    if searchLower in s["location"].lower():
                        foundSet.add(("Location", s["checklistID"], s["location"], s["date"], s["location"]))
                if c == "chkSpeciesComments":
                    if searchLower in s["speciesComments"].lower():
                        foundSet.add(("Species Comments", s["checklistID"], s["location"], s["date"], s["speciesComments"]))
                if c == "chkChecklistComments":
                    if searchLower in s["checklistComments"].lower():
                        foundSet.add(("Checklist Comments", s["checklistID"], s["location"], s["date"], s["checklistComments"]))

        foundList = list(foundSet)
        foundList.sort()

        return(foundList)

    def GetLastDayOfMonth(self, month):
                
        # find last day of the specified month
        if month in ["01", "1", "03", "3", "05", "5", "07", "7", "08", "8", "10", "12"]:
            lastDayOfThisMonth = "31"
        if month in ["04", "4", "06", "6", "09", "9", "11"]:
            lastDayOfThisMonth = "30"
        if month in ["02", "2"]:
            lastDayOfThisMonth = "29"
        return(lastDayOfThisMonth)

    def GetLocationCoordinates(self, location):
        coordinates = []
        s = self.locationDict[location][0]
        coordinates.append(s["latitude"])
        coordinates.append(s["longitude"])

        return(coordinates)

    def GetLocations(self, filter, queryType="OnlyLocations", filteredSightingList=[]):
        # queryType specifies which data fields to return in the returnList
        # "OnlyLocations" returns just the location names
        # "Checklist"returns  locationName, count, checklistID, and time
        # "LocationHierarchy" returns country, county, and location (country includes the state code)
        
        returnList = []
        
        if queryType == "Dates":
            tempDateDict = {}
        
        speciesName = filter.getSpeciesName()
        
        # set filteredSightingList to master list if no filteredSightingList specified
        if filteredSightingList == []:
            filteredSightingList = self.GetMinimalFilteredSightingsList(filter)
            
        sightingFound = False

        # for each sighting, test date if necessary. Append new dates to return list.
        cf = self.CompileFilter(filter)
        for s in filteredSightingList:

            # If a single species is specified:
            # since the file is ordered by species taxonomically, we can stop for loop when we've
            # found a species, processed all its entries, and then moved on to a different species
            # this prevents us from needlessly checking all sightings in the whole database
            if speciesName != "":
                if sightingFound is True:
                    if s["commonName"] != speciesName and speciesName != s["subspeciesName"]:
                        break

            if self.TestSightingCompiled(s, cf) is True:
                
                sightingFound = True
                                    
                if queryType == "OnlyLocations":
                    thisLocationList = s["location"]
                
                if queryType == "Checklist":
                    thisLocationList = [s["location"], s["count"], s["checklistID"], s["latitude"]]

                if queryType == "LocationHierarchy":
                    thisLocationList = [s["state"], s["county"], s["location"]]

                # if we're getting first and last dates, too, we need to 
                # store all dates in a dictionary keyed by location
                # so later we can sort them and return the first and last dates, too
                if queryType == "Dates":

                    keyName = s["location"]

                    if keyName not in tempDateDict:
                        tempDateDict[keyName] = {"dates": [s["date"] + " " + s["time"]], "checklists": {s["checklistID"]}}
                    else:
                        tempDateDict[keyName]["dates"].append(s["date"] + " " + s["time"])
                        tempDateDict[keyName]["checklists"].add(s["checklistID"])
                
                if queryType != "Dates":
                    # add entry to returnList if it's not a duplicate
                    if thisLocationList not in returnList:
                        returnList.append(thisLocationList)
        
        # if we're returning dates, find the first and last dates from dictionary
        # loop through all keys (location names) and append the name and dates
        # to the return list
        if queryType == "Dates":
            for k in tempDateDict.keys():
                tempDateList = tempDateDict[k]["dates"]
                tempDateList.sort()
                tempFirstDate = tempDateList[0]
                tempLastDate = tempDateList[-1]
                checklistCount = len(tempDateDict[k]["checklists"])
                thisLocationList = [k, tempFirstDate, tempLastDate, checklistCount]
                returnList.append(thisLocationList)
        
        # sort the list and return it
        returnList.sort()
        return(returnList)

    def _buildSpeciesSightingDict(self, sightingList):
        """Build a dict mapping commonName -> sorted list of sightings from sightingList.
        Used as a shared helper by all GetNew*Species methods."""
        tempSpeciesDict = {}
        for s in sightingList:
            commonName = s["commonName"]
            if commonName not in tempSpeciesDict:
                tempSpeciesDict[commonName] = [s]
            else:
                tempSpeciesDict[commonName].append(s)
        # Sort each species' sightings by date once
        for commonName in tempSpeciesDict:
            tempSpeciesDict[commonName].sort(key=lambda x: x["date"])
        return tempSpeciesDict

    def GetNewCountrySpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):

        countries = set()
        countrySpecies = []
        tempFilter = deepcopy(filter)

        # loop through sightingListForSpeciesSubset to gather relevant country names
        cf = self.CompileFilter(tempFilter)
        for s in sightingListForSpeciesSubset:
            if self.TestSightingCompiled(s, cf) is True:
                countries.add(s["country"])
        countries = list(countries)
        countries.sort()
        
        # loop through countries to gather first-time species sightings
        for country in countries:
            
            # get list of species with first/last dates for specific country filter
            tempFilter.setLocationType("Country")
            tempFilter.setLocationName(country)
            
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            # use dictionary created when data file was first loaded to get all sightings from 
            # the selected country
            thisCountrySightings = self.countryDict[country]
            
            # create temporary dictionary of sightings in selected country
            # keyed by species name
            tempSpeciesDict = self._buildSpeciesSightingDict(thisCountrySightings)

            # loop through species with dates to see if any sightings are the
            # first for the country
            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    countrySpecies.append([country, species[0]])
        
        return(countrySpecies)

    def GetNewCountySpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):

        # find which years are in the filtered sightingsfor the species in question
        counties = set()
        countySpecies = []
        tempFilter = deepcopy(filter)

        # loop through speciesWithFirstLastDates to gather county names for sightings subset
        cf = self.CompileFilter(tempFilter)
        for s in sightingListForSpeciesSubset:
            county = s["county"]
            if self.TestSightingCompiled(s, cf) is True:
                if county != "":
                    counties.add(county)
        counties = list(counties)
        counties.sort()
        
        # loop through counties, keeping species that are new sightings
        for county in counties:
            
            # get list of species with first/last dates for filter in selected county
            tempFilter.setLocationType("County")
            tempFilter.setLocationName(county)
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            thisCountySightings = self.countyDict[county]
            
            # create temporary dictionary of sightings in selected county
            # keyed by species name
            tempSpeciesDict = self._buildSpeciesSightingDict(thisCountySightings)

            # loop through species with dates to see if any sightings are the
            # first for the county
            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    countySpecies.append([county, species[0]])                    
        
        return(countySpecies)

    def GetNewLifeSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset):
        
        # find which years are in the filtered sightingsfor the species in question
        # DON'T use a SET here, because we want to keep the species taxonomic order 
        lifeSpecies = []
        
        # get list of species with first/last dates for filter
        speciesWithFirstLastDates = self.GetSpeciesWithData(filter, filteredSightingList)

        for species in speciesWithFirstLastDates:
            tempSpeciesSightings = sorted(self.speciesDict[species[0]], key=lambda x: x["date"])
            if species[1] <= tempSpeciesSightings[0]["date"]:
                lifeSpecies.append(species[0])

        return(lifeSpecies)

    def GetNewLocationSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):

        # find which years are in the filtered sightingsfor the species in question
        locations = set()
        locationSpecies = []
        tempFilter = deepcopy(filter)

        cf = self.CompileFilter(filter)
        for s in sightingListForSpeciesSubset:
            if self.TestSightingCompiled(s, cf) is True:
                locations.add(s["location"])
        locations = list(locations)
        locations.sort()
        
        # loop through speciesWithFirstLastDates for each state, keeping species that are new
        for location in locations:
            # get list of species with first/last dates for filter                
            tempFilter.setLocationType("Location")
            tempFilter.setLocationName(location)
            
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            thisLocationSightings = self.locationDict[location]
                        
            tempSpeciesDict = self._buildSpeciesSightingDict(thisLocationSightings)

            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    locationSpecies.append([location, species[0]])         
                        
        return(locationSpecies)            

    def GetNewMonthSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset):

        # find which months are in the filtered sightingsfor the species in question
        months = set()
        monthSpecies = []

        cf = self.CompileFilter(filter)
        for s in sightingListForSpeciesSubset:
            if self.TestSightingCompiled(s, cf) is True:
                months.add(s["date"][5:7])
        months = list(months)
        months.sort()
        
        # get list of species with first/last dates for filter
        for month in months:
            # set temporary filter with each month in loop in filter
            tempFilter = deepcopy(filter)
            tempFilter.setStartSeasonalMonth(month)
            tempFilter.setStartSeasonalDay("01")
            tempFilter.setEndSeasonalMonth(month)
            
            lastDayOfThisMonth = self.GetLastDayOfMonth(month)
            
            tempFilter.setEndSeasonalDay(lastDayOfThisMonth)
            
            speciesWithFirstLastDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            
            thisMonthSightings = self.monthDict[month]
            
            tempSpeciesDict = self._buildSpeciesSightingDict(thisMonthSightings)

            for species in speciesWithFirstLastDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    monthName = _MONTH_NAMES[int(month) - 1]
                    monthSpecies.append([monthName, species[0]])                       
        
        return(monthSpecies)

    def GetNewStateSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset, speciesList):

        # find which years are in the filtered sightingsfor the species in question
        states = set()
        stateSpecies = []
        tempFilter = deepcopy(filter)

        cf = self.CompileFilter(tempFilter)
        for s in sightingListForSpeciesSubset:
            if self.TestSightingCompiled(s, cf) is True:
                states.add(s["state"])
        states = list(states)
        states.sort()
        
        # loop through speciesWithFirstLastDates for each state, keeping species that are new
        for state in states:
            # get list of species with first/last dates for filter
            tempFilter.setLocationType("State")
            tempFilter.setLocationName(state)
            
            speciesWithDates = self.GetSpeciesWithData(tempFilter, filteredSightingList)
            thisStateSightings = self.stateDict[state]
            
            tempSpeciesDict = self._buildSpeciesSightingDict(thisStateSightings)

            for species in speciesWithDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    stateSpecies.append([state, species[0]])            
                        
        return(stateSpecies)

    def GetNewYearSpecies(self, filter, filteredSightingList, sightingListForSpeciesSubset):

        # find which years are in the filtered sightingsfor the species in question
        years = set()
        yearSpecies = []
        thisFilter = deepcopy(filter)

        cf = self.CompileFilter(filter)
        for s in sightingListForSpeciesSubset:
            if self.TestSightingCompiled(s, cf) is True:
                years.add(s["date"][0:4])
        years = list(years)
        years.sort()
        
        for year in years:
            thisYearSightings = self.yearDict[year]

            # get list of species with first/last dates for filter
            startDate = year + "-01-01"
            endDate = year + "-12-31"
            thisFilter.setStartDate(startDate)
            thisFilter.setEndDate(endDate)
            speciesWithDates = self.GetSpeciesWithData(thisFilter, filteredSightingList)

            tempSpeciesDict = self._buildSpeciesSightingDict(thisYearSightings)

            for species in speciesWithDates:
                tempSpeciesSightings = tempSpeciesDict[species[0]]
                if species[1] <= tempSpeciesSightings[0]["date"]:
                    yearSpecies.append([year, species[0]])   
                        
        return(yearSpecies)

    
    def GetQuickEntryCode(self, species):
                
        thisSpecies = deepcopy(species)
        
        if " (" in thisSpecies:
            thisSpecies = thisSpecies.split(" (")[0]
            
        if " x " in thisSpecies:
            return("Not applicable to hybrids")    
            
        cleanedSpeciesName = thisSpecies.replace('-',' ')
        wordList = cleanedSpeciesName.split(" ")
        
        quickEntryCode = ""
        
        if len(wordList) == 1:
            quickEntryCode = wordList[0][0:4]
        
        if len(wordList) == 2:
            quickEntryCode = wordList[0][0:2] + wordList[1][0:2]
            
        if len(wordList) == 3:
            quickEntryCode = wordList[0][0:1] + wordList[1][0:1] + wordList[2][0:2]

        if len(wordList) == 4:
            quickEntryCode = wordList[0][0:1] + wordList[1][0:1] + wordList[2][0:1] + wordList[3][0:1]
                        
        return(quickEntryCode)
    
        
    def GetBBLCode(self, species):

        thisScientificName = self.GetScientificName(species)

        if thisScientificName in self.bblCodeDict:
            bblCode = self.bblCodeDict[thisScientificName]
        else:
            bblCode = ""

        return(bblCode)


    def GeteBirdCode(self, species):

        thisScientificName = self.GetScientificName(species)

        return self.eBirdCodeDict.get(thisScientificName, "")
    

    def GetFamilyName(self, species):
                
        speciesDetails = self.speciesDict[species]
                        
        familyName = speciesDetails[0]["family"]
        
        return(familyName)
    
    
    def GetOrderName(self, species):
        
        speciesDetails = self.speciesDict[species]
                
        orderName = speciesDetails[0]["order"]
        
        return(orderName)   
         
    
    def GetScientificName(self, species):

        speciesDetails = self.speciesDict[species]
        
        scientificName = speciesDetails[0]["scientificName"]
        
        return(scientificName)


    def GetRegionCode(self, longName):
        
        if longName == "All Regions":
            return("All Regions")
        
        else:
            return(self.regionCodeDict[longName])


    def GetRegionName(self, code):
        
        return(self.regionNameDict[code])
            

    def GetCountryCode(self, longName):
        
        if longName == "All Countries":
            return("All Countries")
        
        if self.countryStateCodeFileFound is True:
            for l in self.masterLocationList:
                if "countryName" in l:
                    if l["countryName"] == longName:
                        return(l["countryCode"])
        else:
            return(longName) 
                           
                
    def GetStateCode(self, longName):
        
        if longName == "All States":
            return("All States")
            
        if self.countryStateCodeFileFound is True:
            for l in self.masterLocationList:
                if "stateName" in l:
                    if l["stateName"] == longName:
                        return(l["stateCode"])
        else:
            return(longName)
        

    def GetCountryName(self, shortCode):

        if shortCode == "All Countries":
            return("All Countries")

        if self.countryStateCodeFileFound is True:
            return self._countryLookup.get(shortCode, shortCode)
        else:
            return(shortCode)


    def GetMonthName(self, monthNumberString):
        
        monthName = self.monthNameDict[monthNumberString]
        return(monthName)
        
        
    def GetStateName(self, shortCode):

        if shortCode == "All States":
            return("All States")

        if self.countryStateCodeFileFound is True:
            return self._stateLookup.get(shortCode, shortCode)
        else:
            return(shortCode)

        
    def dumpDatabaseToFile(self):
        
        # routine used only in debugging
        f = open("yearbirder_Db_Dump.txt", "w+")
        for s in self.sightingList:
            f.write(str(s))
            f.write("\n")
        f.close()
            

    def setStartupFolder(self, startupFolder):
        self.startupFolder = startupFolder


    def getStartupFolder(self):
        return(self.startupFolder)


    def setPhotoDataFile(self, photoDataFile):
        self.photoDataFile = photoDataFile
        

    def getPhotoDataFile(self):
        return(self.photoDataFile)    


    def addPhotoDataToDb(self, photoData):
        # Append new unique values to the photo-attribute lists.
        # Sorting is intentionally deferred: call refreshPhotoLists() after a
        # batch of addPhotoDataToDb() calls to get sorted lists for display.

        if photoData["camera"] not in self.cameraList:
            if photoData["camera"] != "":
                self.cameraList.append(photoData["camera"])

        if photoData["lens"] not in self.lensList:
            if photoData["lens"] != "":
                self.lensList.append(photoData["lens"])

        if photoData["shutterSpeed"] not in self.shutterSpeedList:
            if photoData["shutterSpeed"] != "":
                self.shutterSpeedList.append(photoData["shutterSpeed"])

        if photoData["aperture"] not in self.apertureList:
            if photoData["aperture"] != "":
                self.apertureList.append(photoData["aperture"])

        if photoData["focalLength"] not in self.focalLengthList:
            if photoData["focalLength"] != "":
                self.focalLengthList.append(photoData["focalLength"])

        if photoData["iso"] not in self.isoList:
            if photoData["iso"] != "":
                self.isoList.append(photoData["iso"])



    def readPreferences(self):

        if sys.platform == "darwin":
            prefs_dir = os.path.expanduser("~/Library/Application Support/Yearbirder")
        elif sys.platform == "win32":
            prefs_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Yearbirder")
        else:
            prefs_dir = os.path.expanduser("~/.yearbirder")
        prefs_path = os.path.join(prefs_dir, "yearbirderPreferences.txt")

        if not os.path.isfile(prefs_path):
            return  # No preferences saved yet

        with open(prefs_path, "r") as settingsFile:
            for line in settingsFile:

                if line.startswith("startupFolder="):
                    value = line[len("startupFolder="):].strip()
                    self.startupFolder = value

                elif line.startswith("photoDataFile="):
                    value = line[len("photoDataFile="):].strip()
                    self.photoDataFile = value
                    self.photoDataFileDefault = value

                elif line.startswith("ebirdApiKey="):
                    self.ebirdApiKey = line[len("ebirdApiKey="):].strip()

                elif line.startswith("myCounty="):
                    self.myCounty = line[len("myCounty="):].strip()

                elif line.startswith("myPatch="):
                    self.myPatch = line[len("myPatch="):].strip()

                elif line.startswith("audioLatencyByDevice="):
                    try:
                        self.audioLatencyByDevice = json.loads(
                            line[len("audioLatencyByDevice="):].strip()) or {}
                    except (ValueError, TypeError):
                        self.audioLatencyByDevice = {}
                
    
    def writePreferences(self):
        if sys.platform == "darwin":
            prefs_dir = os.path.expanduser("~/Library/Application Support/Yearbirder")
        elif sys.platform == "win32":
            prefs_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Yearbirder")
        else:
            prefs_dir = os.path.expanduser("~/.yearbirder")
        os.makedirs(prefs_dir, exist_ok=True)

        prefs_path = os.path.join(prefs_dir, "yearbirderPreferences.txt")

        with open(prefs_path, "w") as f:
            f.write("startupFolder=" + self.startupFolder + "\n")
            f.write("photoDataFile=" + self.photoDataFileDefault + "\n")
            f.write("ebirdApiKey=" + self.ebirdApiKey + "\n")
            f.write("myCounty=" + self.myCounty + "\n")
            f.write("myPatch=" + self.myPatch + "\n")
            f.write("audioLatencyByDevice="
                    + json.dumps(self.audioLatencyByDevice) + "\n")
        
            
