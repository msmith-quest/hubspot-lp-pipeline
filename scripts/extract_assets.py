#!/usr/bin/env python3
"""Pull base64 data-URI images out of the source LP files.

Writes decoded binaries to assets/ and a stripped copy of each page to
source/stripped/ that references the extracted filename instead of the blob.
The stripped copies are what the manifest extractor parses.
"""
import base64
import hashlib
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402
SRC = ROOT / "source"
OUT = SRC / "stripped"
ASSETS = ROOT / "assets"

DATA_URI = re.compile(r'data:(image/(?:jpeg|png|svg\+xml|webp));base64,([A-Za-z0-9+/=]+)')
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/svg+xml": "svg", "image/webp": "webp"}

def main():
    OUT.mkdir(exist_ok=True)
    ASSETS.mkdir(exist_ok=True)
    seen = {}  # sha1 -> filename, dedupes assets shared across pages
    for page in sorted(SRC.glob("*.html")):
        html = page.read_text()
        slug = page.stem.lower().replace("_", "-")
        counter = 0

        def repl(m):
            nonlocal counter
            mime, b64 = m.groups()
            raw = base64.b64decode(b64)
            sha = hashlib.sha1(raw).hexdigest()[:10]
            if sha not in seen:
                counter += 1
                name = f"{slug}-{counter:02d}-{sha}.{EXT[mime]}"
                (ASSETS / name).write_bytes(raw)
                seen[sha] = name
            return f"asset://{seen[sha]}"

        stripped = DATA_URI.sub(repl, html)
        (OUT / page.name).write_text(stripped)
        print(f"{page.name}: {len(html)//1024}K -> {len(stripped)//1024}K, {counter} new assets")
    print(f"total unique assets: {len(seen)}")

if __name__ == "__main__":
    sys.exit(main())
