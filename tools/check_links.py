"""Checks every link and image in the rendered site.

    python3 tools/check_links.py            # local files only
    python3 tools/check_links.py --web      # also request every external URL once

Run after `quarto render site`. Local links must resolve to a file in site/_site; external links (with --web) must
answer with a status below 400. Exits non-zero if anything is broken.
"""

import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlparse

SITE = Path(__file__).resolve().parent.parent / "site" / "_site"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ("href", "src", "poster", "data-src"):
            if key in a and a[key]:
                self.found.append(a[key])


def main() -> int:
    web = "--web" in sys.argv
    broken, external = [], {}
    for page in sorted(SITE.rglob("*.html")):
        if "site_libs" in page.parts or page.name.startswith("dashboard") or page.parent.name in ("study-rooms", "cafe"):
            continue  # skip generated libraries and the example dashboards themselves
        parser = Links()
        parser.feed(page.read_text(encoding="utf-8", errors="ignore"))
        for link in parser.found:
            url, _ = urldefrag(link)
            if not url or url.startswith(("mailto:", "javascript:", "data:", "tel:")):
                continue
            if urlparse(url).scheme in ("http", "https"):
                external.setdefault(url, page.relative_to(SITE))
                continue
            target = (page.parent / unquote(url)).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                broken.append(f"{page.relative_to(SITE)} → {link}")
    for line in broken:
        print("BROKEN", line)
    print(f"{len(broken)} broken local links; {len(external)} distinct external links")
    bad_web = 0
    if web:
        for url, page in sorted(external.items()):
            if re.search(r"fonts\.(googleapis|gstatic)\.com|cdn\.jsdelivr|unpkg", url):
                continue
            try:
                req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 link-check"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    status = r.status
            except Exception as e:  # noqa: BLE001
                status = getattr(e, "code", str(e))
            ok = isinstance(status, int) and status < 400
            if not ok:
                bad_web += 1
            print(("ok  " if ok else "BAD ") + str(status), url, f"(from {page})")
    return 1 if broken or bad_web else 0


if __name__ == "__main__":
    sys.exit(main())
