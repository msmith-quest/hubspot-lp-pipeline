#!/usr/bin/env python3
"""Triage an incoming HTML page: does it fit the configured family?

Two checks:
  1. Section structure — every EXPECTED_SECTIONS aria-label present, no
     unknown sections (unknown ones need new modules before import).
  2. Extraction coverage — every visible text chunk in the page must appear
     in the extracted manifest. Anything the extractor would silently DROP
     is listed; that's the failure mode this tool exists to catch.

Verdict FITS  -> content-only import; run the normal pipeline.
Verdict REVIEW -> the listed gaps need a human decision first.

Usage: python scripts/triage.py path/to/New_Page.html
"""
import html
import json
import pathlib
import re
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402, F401
from build_manifests import load_family  # noqa: E402


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def manifest_strings(node, acc):
    if isinstance(node, dict):
        for v in node.values():
            manifest_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            manifest_strings(v, acc)
    elif isinstance(node, str):
        # rich-text fields hold serialized HTML: strip tags AND decode
        # entities (&amp; vs &) so coverage compares like with like
        acc.append(norm(html.unescape(re.sub(r"<[^>]+>", " ", node))))


def main():
    family, _cfg = load_family()
    src = pathlib.Path(sys.argv[1]).expanduser()
    soup = BeautifulSoup(src.read_text(), "html.parser")

    problems = []
    expected = (family.sections_for(src, soup)
                if hasattr(family, "sections_for") else family.EXPECTED_SECTIONS)
    required = (family.required_sections_for(src, soup)
                if hasattr(family, "required_sections_for") else expected)
    owned = (family.template_owned_for(src, soup)
             if hasattr(family, "template_owned_for") else family.TEMPLATE_OWNED)
    labels = [s.get("aria-label") for s in soup.find_all("section")]
    extra = [l for l in labels if l not in expected]
    missing = [l for l in required if l is not None and l not in labels]
    if extra:
        problems.append(f"unknown sections (need new modules?): {extra}")
    if missing:
        problems.append(f"missing sections: {missing}")

    try:
        manifest = family.extract(src)
    except Exception as exc:  # noqa: BLE001
        print(f"VERDICT: REVIEW — extractor crashed: {exc!r}")
        print("The page structure has drifted from what the extractor expects.")
        return 1

    captured = []
    manifest_strings(manifest, captured)
    blob = " ␟ ".join(captured)

    body = soup.body
    for sel in owned:
        for el in body.find_all(**sel):
            el.decompose()
    for el in body.find_all(["script", "style", "svg", "select", "label", "input", "button"]):
        el.decompose()

    uncovered = [norm(t) for t in body.stripped_strings
                 if len(norm(t)) >= 4 and norm(t) not in blob]
    if uncovered:
        problems.append("visible text the extractor would DROP:")

    print(f"{src.name}: slug=/{manifest.get('slug')}")
    if not problems:
        print("VERDICT: FITS — run the pipeline (cp to source/, extract_assets, build_manifests, render_preview)")
        return 0
    print("VERDICT: REVIEW")
    for p in problems:
        print(f"  - {p}")
    for t in uncovered:
        print(f"      · {t[:110]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
