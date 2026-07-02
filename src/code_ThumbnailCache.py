"""Persistent on-disk thumbnail cache.

Stores ~500x330 JPEG thumbnails in the platform cache directory
(QStandardPaths.CacheLocation), keyed by the source file's absolute path,
modification time and size.  Because the key embeds mtime+size, a hit is valid
by construction: if the source is edited or replaced the key changes and the
old entry is simply ignored (and reclaimed later by enforce_cap).

The cache is best-effort — every operation degrades gracefully to a miss /
no-op on any I/O error, so it can never break thumbnail loading.

Cross-platform location (via QStandardPaths):
    macOS   : ~/Library/Caches/Yearbirder/thumbs/v1/
    Windows : %LOCALAPPDATA%\\Yearbirder\\cache\\thumbs\\v1\\
    Linux   : ~/.cache/Yearbirder/thumbs/v1/   ($XDG_CACHE_HOME honoured)
"""

import hashlib
import os
import shutil
import tempfile

from PySide6.QtCore import QStandardPaths, QSize, Qt
from PySide6.QtGui import QImageReader, QImageWriter

# Bump the version subdir whenever any cached artifact's spec changes — old
# caches are then ignored and cleaned up by enforce_cap().
_CACHE_VERSION = "v2"
_CACHE_SUBDIR  = "thumbs"
_DEFAULT_CAP_BYTES = 1024 * 1024 * 1024  # ~1 GB (spectro ribbons are ~0.4-3 MB each)
THUMB_SIZE = QSize(500, 330)             # target photo-thumbnail bounding box

# Each cached artifact is identified by a "kind".  Photos use lossy JPEG; the
# grayscale spectrograms use lossless PNG (JPEG would smear the fine frequency
# detail).  kind -> (file extension, QImageWriter format, quality | -1 default).
_KIND_FMT = {
    "photo":            (".jpg", b"jpg", 85),
    "spectro_thumb":    (".png", b"png", -1),
    "spectro_overview": (".png", b"png", -1),
    "spectro_ribbon":   (".png", b"png", -1),   # large; cached grayscale by caller
}
_CACHE_EXTS = tuple(ext for (ext, _f, _q) in _KIND_FMT.values())

# PNG zlib effort (0-100).  PNG is lossless at every level, so this trades file
# size for encode speed with no effect on the decoded image.  The default (max)
# level spends ~920 ms zlib-packing a 16000x700 ribbon; level 50 is visually and
# byte-for-byte identical on decode but encodes ~3x faster (~290 ms) for only a
# slightly larger file (~3.1 vs ~2.6 MB) — a big win for the rebuild pass.
_PNG_COMPRESSION = 50

_cache_dir = None


def decode_thumbnail(source_path):
    """Decode source_path at reduced (thumbnail) scale, EXIF-oriented.

    Returns a QImage (possibly null on failure).  Uses QImageReader's scaled
    decode so large JPEGs are not fully decoded.  This is the single place the
    thumbnail is produced — shared by the Photos worker and the rebuild action.
    """
    reader = QImageReader(source_path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        size.scale(THUMB_SIZE, Qt.KeepAspectRatio)
        reader.setScaledSize(size)
    return reader.read()


def build(source_path):
    """Force-(re)generate and store the cached photo thumbnail.  True on success."""
    img = decode_thumbnail(source_path)
    if img.isNull():
        return False
    store(source_path, img)
    return True


def build_spectro(wav_path):
    """Force-(re)generate and store the cached spectrogram thumbnail (PNG).

    Lazily imports the renderer to avoid an import cycle.  True on success.
    """
    import code_Audio
    img, _dur, _sr, _bbox = code_Audio.render_spectrogram_qimage(wav_path)
    if img is None or img.isNull():
        return False
    store(wav_path, img, "spectro_thumb")
    return True


def rebuild_one(item):
    """Build all cache entries for one media file — module-level so it can run in
    a multiprocessing worker (spawn-picklable).

    ``item`` is ``(kind, path)`` where kind is "photo" or "recording".  For a
    recording it builds both the browser thumbnail and the enlargement ribbon.
    Returns ``path`` regardless of success (the caller only needs a progress
    tick); failures are swallowed so one bad file can't stall the pool.
    """
    kind, path = item
    try:
        if kind == "photo":
            build(path)
        else:
            build_spectro(path)
            import code_RecordingEnlargement
            code_RecordingEnlargement.build_ribbon_cache(path)
    except Exception:
        pass
    return path


def prebuild_async(photo_paths=(), recording_paths=()):
    """Populate the cache for newly-added media in background daemon threads.

    Best-effort and fire-and-forget: photos get a thumbnail; recordings get the
    spectrogram thumbnail AND the enlargement ribbon.  Items already cached are
    skipped (a cheap load check), so re-saving existing media costs almost
    nothing.  Safe to call from the GUI thread — returns immediately.
    """
    import threading
    import queue as _queue

    items = ([("photo", p) for p in photo_paths]
             + [("recording", p) for p in recording_paths])
    if not items:
        return

    # matplotlib's import is not thread-safe, so import the ribbon renderer once
    # here on the caller (GUI) thread before any worker uses it.
    cre = None
    if recording_paths:
        try:
            import code_RecordingEnlargement as cre
        except Exception:
            cre = None

    work = _queue.Queue()
    for it in items:
        work.put(it)

    def _worker():
        while True:
            try:
                kind, path = work.get_nowait()
            except _queue.Empty:
                break
            try:
                if kind == "photo":
                    if load(path, "photo") is None:
                        build(path)
                else:
                    if load(path, "spectro_thumb") is None:
                        build_spectro(path)
                    if cre is not None and load(
                            path, "spectro_ribbon",
                            cre._RIBBON_VARIANT) is None:
                        cre.build_ribbon_cache(path)
            except Exception:
                pass

    n = min(os.cpu_count() or 4, 4)
    for _ in range(min(n, len(items))):
        threading.Thread(target=_worker, daemon=True).start()


def clear():
    """Delete every file in the cache directory (full rebuild starts clean)."""
    d = cache_dir()
    if not d:
        return
    try:
        names = os.listdir(d)
    except OSError:
        return
    for name in names:
        try:
            os.remove(os.path.join(d, name))
        except OSError:
            pass


def cache_dir():
    """Return the (created) versioned cache directory, or None if unavailable."""
    global _cache_dir
    if _cache_dir is not None:
        return _cache_dir
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    if not base:
        return None
    root = os.path.join(base, _CACHE_SUBDIR)
    d = os.path.join(root, _CACHE_VERSION)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    # Remove stale version dirs (e.g. an old v1) so a version bump doesn't leak disk.
    try:
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if name != _CACHE_VERSION and os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
    except OSError:
        pass
    _cache_dir = d
    return d


def _hash_key(abspath, mtime, size, kind, variant=""):
    """The cache key for an artifact, given the source's identity components."""
    suffix = "|" + variant if variant else ""
    raw = "{}|{}|{}|{}{}".format(
        abspath, int(mtime), size, kind, suffix).encode("utf-8", "surrogatepass")
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


def _key_for(source_path, kind, variant=""):
    """Hash of absolute path + mtime + size + kind (+ variant), or None if the
    source is missing.  variant distinguishes parameterised artifacts (e.g. the
    ribbon at a given render width).  An empty variant keeps the legacy key."""
    try:
        st = os.stat(source_path)
    except OSError:
        return None
    return _hash_key(os.path.abspath(source_path), st.st_mtime, st.st_size, kind, variant)


def _all_kind_variants():
    """Every (kind, variant) artifact identity a media file might have cached.
    The ribbon's variant lives in code_RecordingEnlargement; imported lazily so
    this module has no hard dependency on it."""
    pairs = [("photo", ""), ("spectro_thumb", ""), ("spectro_overview", "")]
    try:
        import code_RecordingEnlargement as cre
        pairs.append(("spectro_ribbon", cre._RIBBON_VARIANT))
    except Exception:
        pass
    return pairs


def rename(old_path, new_path):
    """Re-key cached artifacts when a media file is renamed (or moved) so the
    renamed file keeps its cached thumbnails / spectrograms.  Best-effort.

    A rename does not change a file's content, so its mtime and size are
    unchanged — only the path (and therefore the cache key) differs.  We move
    each cached file from its old-path key to its new-path key.
    """
    d = cache_dir()
    if not d:
        return
    try:
        st = os.stat(new_path)   # file now lives at new_path; mtime/size unchanged
    except OSError:
        return
    old_abs = os.path.abspath(old_path)
    new_abs = os.path.abspath(new_path)
    if old_abs == new_abs:
        return
    for kind, variant in _all_kind_variants():
        ext = _KIND_FMT[kind][0]
        old_fp = os.path.join(d, _hash_key(old_abs, st.st_mtime, st.st_size, kind, variant) + ext)
        new_fp = os.path.join(d, _hash_key(new_abs, st.st_mtime, st.st_size, kind, variant) + ext)
        if os.path.exists(old_fp):
            try:
                os.replace(old_fp, new_fp)
            except OSError:
                pass


def _cache_path(source_path, kind, variant=""):
    d = cache_dir()
    if not d:
        return None
    fmt = _KIND_FMT.get(kind)
    if not fmt:
        return None
    key = _key_for(source_path, kind, variant)
    if not key:
        return None
    return os.path.join(d, key + fmt[0])


def load(source_path, kind="photo", variant=""):
    """Return a cached QImage for (source_path, kind, variant), or None on miss.

    A corrupt cache entry is deleted and treated as a miss.  On a hit the file
    is 'touched' so enforce_cap()'s LRU ordering reflects recent use.
    """
    cp = _cache_path(source_path, kind, variant)
    if not cp or not os.path.exists(cp):
        return None
    img = QImageReader(cp).read()
    if img.isNull():
        try:
            os.remove(cp)
        except OSError:
            pass
        return None
    try:
        os.utime(cp, None)   # mark as recently used
    except OSError:
        pass
    return img


def store(source_path, qimage, kind="photo", variant=""):
    """Write qimage as the cached artifact for (source_path, kind, variant).
    Atomic, best-effort (any I/O error is a silent no-op)."""
    if qimage is None or qimage.isNull():
        return
    cp = _cache_path(source_path, kind, variant)
    if not cp:
        return
    _ext, fmt, quality = _KIND_FMT[kind]
    d = os.path.dirname(cp)
    try:
        fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=d)
        os.close(fd)
    except OSError:
        return
    writer = QImageWriter(tmp, fmt)
    if quality >= 0:
        writer.setQuality(quality)
    elif fmt == b"png":
        writer.setCompression(_PNG_COMPRESSION)   # lossless; faster encode
    if writer.write(qimage):
        try:
            os.replace(tmp, cp)   # atomic on POSIX and Windows
            return
        except OSError:
            pass
    try:
        os.remove(tmp)
    except OSError:
        pass


def enforce_cap(max_bytes=_DEFAULT_CAP_BYTES):
    """Delete least-recently-used thumbnails if the cache exceeds max_bytes.

    Cheap (one listdir + stat per file); intended to run off the load path,
    e.g. when a browser window closes.  Best-effort.
    """
    d = cache_dir()
    if not d:
        return
    try:
        names = os.listdir(d)
    except OSError:
        return
    entries = []
    total = 0
    for name in names:
        if not name.endswith(_CACHE_EXTS):
            continue
        fp = os.path.join(d, name)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        entries.append((st.st_mtime, st.st_size, fp))
        total += st.st_size
    if total <= max_bytes:
        return
    entries.sort()   # oldest (least-recently-used) first
    for _mtime, size, fp in entries:
        if total <= max_bytes:
            break
        try:
            os.remove(fp)
            total -= size
        except OSError:
            pass
