#!/usr/bin/env python3
"""Serve web/ the way Cloudflare Pages does, for previewing before a push.

python -m http.server is not a faithful preview: the site's links are
extensionless (/download, not /download.html), Pages resolves those itself,
and a plain file server answers 404 to every one of them.  It also knows
nothing about _redirects or 404.html, so the two things hardest to check
before deploying are the two it cannot show.

This mirrors the parts of Pages' behaviour the site actually relies on:

  1. _redirects rules, applied first, with their status code.
  2. /path        -> web/path.html   (the extensionless URLs in every nav)
  3. /path/       -> web/path/index.html
  4. anything else -> web/404.html, with a real 404 status.

Usage:  ./preview_site.py [port]      (default 8765)
"""

import http.server
import os
import posixpath
import socketserver
import sys
import urllib.parse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def load_redirects():
    """Parse _redirects into [(from, to, status)], ignoring comments."""
    rules = []
    path = os.path.join(ROOT, "_redirects")
    if not os.path.exists(path):
        return rules
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) == 3 and parts[2].isdigit():
            rules.append((parts[0], parts[1], int(parts[2])))
        elif len(parts) == 2:
            rules.append((parts[0], parts[1], 301))
    return rules


class Handler(http.server.SimpleHTTPRequestHandler):

    redirects = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def send_head(self):
        path = urllib.parse.urlparse(self.path).path

        for src, dest, status in self.redirects:
            if path == src:
                self.send_response(status)
                self.send_header("Location", dest)
                self.end_headers()
                return None

        local = self.translate_path(self.path)

        # A directory serves its index.html; a bare path tries <path>.html.
        if os.path.isdir(local):
            index = os.path.join(local, "index.html")
            if os.path.exists(index):
                return self.serve(index)
        elif not os.path.exists(local) and not path.endswith("/"):
            as_html = local + ".html"
            if os.path.exists(as_html):
                return self.serve(as_html)

        if os.path.exists(local) and not os.path.isdir(local):
            return super().send_head()

        return self.serve(os.path.join(ROOT, "404.html"), status=404)

    def serve(self, filename, status=200):
        if not os.path.exists(filename):
            self.send_error(404, "File not found")
            return None
        f = open(filename, "rb")
        self.send_response(status)
        self.send_header("Content-type", self.guess_type(filename))
        self.send_header("Content-Length", str(os.fstat(f.fileno()).st_size))
        self.end_headers()
        return f

    def end_headers(self):
        # Never let the browser cache during a preview: a stale style.css is
        # indistinguishable from a CSS bug, and costs far more time than the
        # re-fetch does.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    Handler.redirects = load_redirects()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"Serving {ROOT} at http://127.0.0.1:{port}/")
        print(f"  {len(Handler.redirects)} redirect rules, extensionless URLs, 404.html")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
