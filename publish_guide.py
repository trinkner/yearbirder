#!/usr/bin/env python3
"""Publish the in-app User Guide to the website as web/guide/index.html.

The guide ships inside the .app, where Google can never see it — and it is by
far the most substantial writing about Yearbirder that exists: every feature,
in the words someone would search for.  This copies it to the site, adding the
things a web page needs and the app's copy does not: a description, a canonical
URL, social-card tags, and a bar linking back to the site.

Run it whenever the guide changes; build_release.sh runs it at release time so
the two cannot drift.  The source of truth is always src/guide, never the copy.
"""

import os
import re
import sys

SRC  = "src/guide/guide_Yearbirder.html"
DEST = "web/guide/index.html"
SITE = "https://yearbirder.org"

DESCRIPTION = (
    "The complete Yearbirder user guide: filtering your eBird sightings, lists "
    "and totals, charts and maps, the Trip Report, photos, sound recordings, "
    "and community sightings."
)

# Injected right after <head>, BEFORE the guide's own <style>: the site's
# stylesheet must lose to the guide's rules on anything they both set (body
# type, headings, tables), and later rules win at equal specificity.
HEAD_LINKS = """  <link rel="stylesheet" href="/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
"""

# Injected right before </head>: metadata, plus the few overrides that let the
# site's full-width navigation sit above the guide's 860px text column.
HEAD_EXTRA = f"""  <meta name="description" content="{DESCRIPTION}">
  <link rel="canonical" href="{SITE}/guide">
  <link rel="icon" type="image/x-icon" href="/images/favicon.ico">
  <link rel="icon" type="image/png" sizes="32x32" href="/images/favicon-32x32.png">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="Yearbirder">
  <meta property="og:url" content="{SITE}/guide">
  <meta property="og:title" content="Yearbirder User Guide">
  <meta property="og:description" content="{DESCRIPTION}">
  <meta property="og:image" content="{SITE}/images/og_yearbirder.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Yearbirder User Guide">
  <meta name="twitter:description" content="{DESCRIPTION}">
  <meta name="twitter:image" content="{SITE}/images/og_yearbirder.jpg">
  <style>
    /* Web-only: the guide centres its own 860px column via body, which would
       pen the site's navigation into that column too.  Hand the column to a
       wrapper instead and let body span the window. */
    body {{ max-width: none; margin: 0; padding: 0; background: #fff; }}
    .guide-page {{ max-width: 860px; margin: 0 auto; padding: 2rem 2rem 4rem; }}
    /* The bar matches the other pages, typeface included; the guide's own
       system-font stack would otherwise reach it through inheritance. */
    nav, nav * {{ font-family: 'Inter', system-ui, -apple-system, sans-serif; }}
    @media (max-width: 600px) {{ .guide-page {{ padding: 1rem; }} }}
  </style>
"""

# The site's navigation, verbatim in structure but with root-relative links:
# this page lives at /guide/, where "index.html" would resolve inside it.
SITE_NAV = """<nav>
  <div class="nav-inner">
    <a href="/" class="nav-brand">
      <img src="/images/opt/icon.webp" alt="Yearbirder icon" width="90" height="90">
      Yearbirder
    </a>
    <ul class="nav-links">
      <li><a href="/">Overview</a></li>
      <li><a href="/sighting-analysis">Sighting Analysis</a></li>
      <li><a href="/photography">Photography</a></li>
      <li><a href="/recordings">Recordings</a></li>
      <li><a href="/community">Community</a></li>
      <li><a href="/download" class="nav-download">Download</a></li>
      <li><a href="/history">Version History</a></li>
      <li><a href="/guide" class="active">User Guide</a></li>
    </ul>
  </div>
</nav>

<div class="guide-page">
"""


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    if not os.path.exists(SRC):
        sys.exit(f"ERROR: {SRC} not found")

    html = open(SRC, encoding="utf-8").read()

    for needed in ("<head>", "</head>", "<body>", "</body>"):
        if needed not in html:
            sys.exit(f"ERROR: {SRC} has no {needed} to inject into")

    html = html.replace("<head>", "<head>\n" + HEAD_LINKS, 1)
    html = html.replace("</head>", HEAD_EXTRA + "</head>", 1)
    html = html.replace("<body>", "<body>\n\n" + SITE_NAV, 1)
    html = html.replace("</body>", "</div>\n\n</body>", 1)

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    open(DEST, "w", encoding="utf-8").write(html)

    words = len(re.sub(r"<[^>]*>", " ", html).split())
    size = os.path.getsize(DEST) / 1024
    links = html.count('class="back-to-top"')
    print(f"  {DEST}: {size:.0f} KB, ~{words:,} words, {links} back-to-top links")

    sitemap = "web/sitemap.xml"
    if os.path.exists(sitemap) and "/guide" not in open(sitemap, encoding="utf-8").read():
        print(f"  NOTE: {sitemap} has no /guide entry yet")


if __name__ == "__main__":
    main()
