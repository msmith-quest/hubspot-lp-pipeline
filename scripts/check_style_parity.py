#!/usr/bin/env python3
"""Style parity: does the rendered preview carry the SOURCE page's design?

Triage's coverage check guards text; this guards styling. In this toolkit
the design rides in inline style="" attributes (plus classes) inside the
modules, so a family port that lags the incoming sources renders stale
design — old paddings, type scales and backgrounds around fresh copy —
and nothing else in the pipeline notices.

For every manifest, the page is split into chrome units (skip link,
header, footer, mobile CTA bar, demo modal) plus each top-level <main>
section, paired between preview/<page>.html and source/stripped/<file>.
Within a unit, every element becomes a token of tag|classes|styles
(declarations sorted, url(...) masked); the token sequences are diffed.
Any mismatch is stale or missing design and fails the run.

Excluded as expected deltas: script/style/noscript, the source review
chrome, the real <form> controls (source) and the form placeholder the
preview renders in their place.

Usage: python scripts/check_style_parity.py [page-stem ...]
"""
import json
import pathlib
import re
import sys
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402

PLACEHOLDER_MARK = "HubSpot form renders here"


def norm_style(style):
    style = re.sub(r"url\([^)]*\)", "url(#)", style or "")
    decls = sorted(" ".join(d.split()) for d in style.split(";") if d.strip())
    return ";".join(decls)


def tokens(root):
    out = []
    for el in [root, *root.find_all(True)]:
        cls = " ".join(sorted(el.get("class") or []))
        out.append(f"{el.name}|{cls}|{norm_style(el.get('style'))}")
    return out


def strip_expected(soup, is_preview):
    for el in soup.find_all(["script", "style", "noscript"]):
        el.decompose()
    for el in soup.find_all(class_="review-chrome"):
        el.decompose()
    if is_preview:
        for el in soup.find_all("div"):
            if PLACEHOLDER_MARK in el.get_text() and not el.find("div"):
                el.decompose()
    else:
        for el in soup.find_all("form"):
            el.decompose()


def is_modal(el):
    style = el.get("style") or ""
    return ("dm-ov" in (el.get("class") or [])
            or ("position:fixed" in style.replace(" ", "") and "inset:0" in style.replace(" ", "")))


def units(soup):
    """Ordered (label, element) chrome units + main sections."""
    body = soup.body
    out = []
    if (skip := body.find("a", class_="skip")):
        out.append(("skip-link", skip))
    for tag in ("header", "footer"):
        if (el := body.find(tag)):
            out.append((tag, el))
    main = body.find("main") or body
    for i, sec in enumerate(main.find_all("section", recursive=False)):
        out.append((sec.get("aria-label") or f"section {i}", sec))
    for el in body.find_all("div", recursive=False):
        if "mcta" in (el.get("class") or []):
            out.append(("mobile-cta", el))
        elif is_modal(el):
            out.append(("demo-modal", el))
    # module-rendered modals live inside <main>
    for el in main.find_all("div", recursive=False):
        if is_modal(el):
            out.append(("demo-modal", el))
    return out


def check_page(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    prev_p = ROOT / "preview" / (manifest_path.stem + ".html")
    src_p = ROOT / "source" / "stripped" / manifest["file"]
    if not src_p.exists():
        src_p = ROOT / "source" / manifest["file"]
    if not prev_p.exists():
        print(f"{manifest_path.stem}: SKIP (no preview; run render_preview.py)")
        return None

    docs = []
    for path, is_preview in ((src_p, False), (prev_p, True)):
        soup = BeautifulSoup(path.read_text(), "html.parser")
        strip_expected(soup, is_preview)
        docs.append(dict(units(soup)))
    src_units, prev_units = docs

    total = stale = 0
    lines = []
    for label, src_el in src_units.items():
        a = tokens(src_el)
        total += len(a)
        prev_el = prev_units.get(label)
        if prev_el is None:
            stale += len(a)
            lines.append(f"  {label}: MISSING from preview ({len(a)} elements)")
            continue
        b = tokens(prev_el)
        match = sum(m.size for m in SequenceMatcher(None, a, b).get_matching_blocks())
        if match < len(a) or match < len(b):
            stale += len(a) - match
            lines.append(f"  {label}: {len(a) - match}/{len(a)} source elements stale "
                         f"(+{len(b) - match} preview-only)")
            opcodes = SequenceMatcher(None, a, b).get_opcodes()
            samples = [(t, a[i1:i2], b[j1:j2]) for t, i1, i2, j1, j2 in opcodes if t != "equal"]
            for t, sa, sb in samples[:3]:
                if sa:
                    lines.append(f"      source : {sa[0][:150]}")
                if sb:
                    lines.append(f"      preview: {sb[0][:150]}")
    for label in prev_units:
        if label not in src_units:
            lines.append(f"  {label}: preview-only unit (not in source)")
            stale += 1
    return manifest_path.stem, total, stale, lines


def main():
    only = set(sys.argv[1:])
    failed = 0
    for mf in sorted((ROOT / "manifests").rglob("*.json")):
        if only and mf.stem not in only:
            continue
        result = check_page(mf)
        if result is None:
            continue
        stem, total, stale, lines = result
        if stale:
            failed += 1
            print(f"{stem}: DRIFT {stale}/{total} elements ({100 * stale / total:.0f}%)")
            for line in lines:
                print(line)
        else:
            print(f"{stem}: OK ({total} elements)")
    if failed:
        print(f"\n{failed} page(s) with style drift — the family port lags the sources.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
