"""Live refresh of open report windows when the media catalog changes.

When the user deletes a media file, removes it from the catalog, or reassigns
its species, any open report that reflects that media should update on the fly.
The mechanism is:

  * Every report window's primary build method is decorated with @media_report.
    The decorator remembers how to rebuild the window (its own method + the exact
    arguments it was called with) and, if the window is media-relevant, stashes a
    cheap "media-scope signature" of the catalog data the report is built from.

  * On any media mutation, MainWindow.notifyMediaChanged() calls maybeRefresh()
    on each report.  It first applies a pre-filter so pure-sightings reports do
    no work at all, then recomputes the freshly-changed data and compares its
    signature to the stashed one.  Identical signature -> the change did not
    touch this report's scope -> abort; different -> rebuild.

Two subtleties this handles:

  * Baked media-species lists.  A filter's validPhotoSpecies/validRecordingSpecies
    are snapshots computed when the report was spawned.  refreshMediaFilterSpecies
    recomputes them against the current catalog before the signature/rebuild, so
    a deletion that drops a species from "photographed" is reflected.

  * deepcopy-at-build.  Several Web reports do self.filter = deepcopy(filter), so
    the report's live filter is a different object from the one the build method
    received.  We recompute media-species on both, and rebuild by replaying the
    window's own decorated method (which re-derives self.filter afresh).
"""

import functools

import code_Filter


def media_report(is_content=False):
    """Decorate a report window's primary build/Fill method.

    is_content=True marks reports that visualise media regardless of any media
    filter (geolocated-media maps, media-by-species galleries, media counts) —
    these are always media-relevant.  Everything else is media-relevant only
    when its filter carries a media constraint.

    is_content may also be a callable(window) -> bool, evaluated after each
    build, for reports whose media-dependence varies with their mode (e.g. a
    Graphs window is media-content only for its photo/recording chart types).
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            result = fn(self, *args, **kwargs)
            # Remember how to faithfully rebuild this exact report.
            self._mediaIsContent = is_content(self) if callable(is_content) else is_content
            self._mediaRebuildName = fn.__name__
            self._mediaRebuildArgs = (args, kwargs)
            # Stash the signature only when the report is media-relevant, so
            # pure-sightings reports never pay for the query.
            filt = getattr(self, "filter", None)
            if _isMediaRelevant(self, filt):
                self._mediaSig = _safeSignature(self, filt)
            else:
                self._mediaSig = None
            return result
        return wrapper
    return deco


def _isMediaRelevant(window, filt):
    if not filt or filt == ():
        return False
    if getattr(window, "_mediaIsContent", False):
        return True
    try:
        return filt.hasMediaConstraint()
    except AttributeError:
        return False


def _safeSignature(window, filt):
    try:
        return window.mdiParent.db.mediaScopeSignature(filt)
    except Exception:
        return None


def maybeRefresh(window):
    """Refresh one report window if an open catalog change touched its scope."""
    filt = getattr(window, "filter", None)
    if not _isMediaRelevant(window, filt):
        return
    db = window.mdiParent.db

    # Recompute the baked media-species lists so both the signature and any
    # rebuild reflect the current catalog — on the live filter and on any Filter
    # captured in the rebuild args (the deepcopy-at-build case re-derives from it).
    db.refreshMediaFilterSpecies(filt)
    origArgs, origKwargs = getattr(window, "_mediaRebuildArgs", ((), {}))
    for a in list(origArgs) + list(origKwargs.values()):
        if isinstance(a, code_Filter.Filter) and a is not filt:
            db.refreshMediaFilterSpecies(a)

    newSig = db.mediaScopeSignature(filt)
    if newSig == getattr(window, "_mediaSig", None):
        window._mediaSig = newSig
        return

    # Rebuild by replaying the window's own decorated method with its original
    # arguments; the wrapper re-stashes a fresh signature and rebuild record.
    name = getattr(window, "_mediaRebuildName", None)
    if not name:
        return
    getattr(window, name)(*origArgs, **origKwargs)
