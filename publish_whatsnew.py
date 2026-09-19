#!/usr/bin/env python3
"""Generate the app's offline What's New page from the website's history.

The changelog is authored once, in web/history.html.  The app cannot simply
show that page live: a user running 2.14 would read about features their build
does not have and go hunting for menus that are not there.  So the build writes
a snapshot into src/guide/whatsnew.html containing the releases up to and
including the version being built, and the app loads that from disk.

Its footer names the newest release it contains and links to the live history,
so it never implies it is current.

Run it whenever history.html changes; build_release.sh runs it before the
PyInstaller step, since src/guide is bundled into the app.

Usage:  ./publish_whatsnew.py [version]      (default: versionNumber in code_MainWindow.py)
"""

import html
import os
import re
import sys

HISTORY = "web/history.html"
DEST    = "src/guide/whatsnew.html"
MAIN    = "src/code_MainWindow.py"
SITE_HISTORY = "https://yearbirder.org/history"


def current_version():
    src = open(MAIN, encoding="utf-8").read()
    m = re.search(r'versionNumber\s*=\s*"([^"]+)"', src)
    if not m:
        sys.exit(f"ERROR: no versionNumber in {MAIN}")
    return m.group(1)


def as_tuple(version):
    """"2.16-dev" -> (2, 16).  Development builds rank with their release."""
    core = version.split("-")[0]
    return tuple(int(p) for p in core.split(".") if p.isdigit())


def releases():
    """Every release in history.html, newest first: (version, date, [(title, body)])."""
    page = open(HISTORY, encoding="utf-8").read()
    # Each release is introduced by an HTML comment naming it, which is the one
    # reliable delimiter: the blocks themselves are nested divs.
    chunks = re.split(r"<!--\s*v[\d.]+\s*-->", page)[1:]
    out = []
    for chunk in chunks:
        ver = re.search(r'class="release-version">v([\d.]+)<', chunk)
        date = re.search(r'class="release-date">([^<]+)<', chunk)
        if not ver:
            continue
        items = re.findall(
            r'<span class="feat-title">(.*?)</span>\s*<p>(.*?)</p>',
            chunk, re.S)
        out.append((ver.group(1),
                    date.group(1).strip() if date else "",
                    [(t.strip(), b.strip()) for t, b in items]))
    return out


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>What's New in Yearbirder</title>
  <style>
    /* Matches the User Guide, which mirrors the website's palette:
       forest #1B4332  grove #2D6A4F  meadow #D8F3DC
       mist #F2FAF5    border #B7DFC3  ink #1A2B1C  slate #5A6E5B */
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 15px;
      line-height: 1.6;
      color: #1A2B1C;
      max-width: 860px;
      margin: 0 auto;
      padding: 2rem 2rem 4rem;
      background: #fff;
    }}
    h1 {{
      font-size: 2rem;
      border-bottom: 2px solid #2D6A4F;
      padding-bottom: 0.4rem;
      color: #1A2B1C;
      margin-bottom: 1.6rem;
    }}
    h2 {{
      font-size: 1.3rem;
      color: #1B4332;
      background: #D8F3DC;
      border: 1px solid #B7DFC3;
      border-radius: 6px;
      padding: 0.45rem 0.9rem;
      margin: 2.2rem 0 1rem;
    }}
    h2 .date {{ font-weight: 400; color: #5A6E5B; font-size: 0.9rem; float: right; }}
    .feat {{ margin: 0 0 1.1rem; }}
    .feat-title {{ font-weight: 600; color: #1A2B1C; }}
    .feat p {{ margin: 0.25rem 0 0; }}
    a {{ color: #2D6A4F; }}
    code {{ background: #F2FAF5; padding: 1px 4px; border-radius: 3px; }}
    .footer {{
      margin-top: 3rem;
      border-top: 1px solid #B7DFC3;
      padding-top: 1rem;
      color: #5A6E5B;
      font-size: 0.9rem;
    }}
  </style>
</head>
<body>

<h1>What's New in Yearbirder</h1>

{body}

<div class="footer">
  <p>Any release after v{newest} is listed at
     <a href="{site}">yearbirder.org/history</a>.</p>
</div>

</body>
</html>
"""


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root)

    version = sys.argv[1] if len(sys.argv) > 1 else current_version()
    cutoff = as_tuple(version)

    found = releases()
    if not found:
        sys.exit(f"ERROR: no releases parsed from {HISTORY} — its markup changed")

    kept = [r for r in found if as_tuple(r[0]) <= cutoff]
    if not kept:
        sys.exit(f"ERROR: {HISTORY} lists nothing at or below v{version}")

    blocks = []
    for ver, date, items in kept:
        feats = "\n".join(
            f'  <div class="feat"><span class="feat-title">{t}</span>\n'
            f'    <p>{b}</p></div>'
            for t, b in items)
        date_html = f'<span class="date">{html.escape(date)}</span>' if date else ""
        blocks.append(f'<h2>v{ver} {date_html}</h2>\n{feats}')

    # The footer names the newest release actually included, not the version
    # being built: with 2.17-dev in hand and no 2.17 entry written yet, saying
    # "after v2.17" would misdescribe what the page holds.
    out = PAGE.format(newest=kept[0][0],
                      body="\n\n".join(blocks),
                      site=SITE_HISTORY)
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    open(DEST, "w", encoding="utf-8").write(out)

    skipped = len(found) - len(kept)
    note = f", {skipped} newer release(s) left out" if skipped else ""
    print(f"  {DEST}: {len(kept)} releases through v{version}{note}")


if __name__ == "__main__":
    main()
