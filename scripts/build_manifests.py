#!/usr/bin/env python3
"""Run the configured family's extractor over source/*.html -> manifests/.

A "family" is one design system of incoming pages: a HubSpot template, a set
of modules, and an extractor that knows the family's markup. The extractor
lives at families/<name>/extract.py and must expose:

    extract(path: Path) -> dict   # the page manifest
    EXPECTED_SECTIONS: list[str]  # aria-labels triage checks for
    TEMPLATE_OWNED: list[dict]    # bs4 find_all kwargs for content the
                                  # template renders itself (skipped by
                                  # triage's coverage check)

Manifest contract (consumed by render_preview.py and create_pages.py):
    file, slug, internal_name, html_title, meta_description, noindex,
    template_file  ("templates/landing.html", relative to the theme)
    and EITHER widgets {module_name: {field: value}}   (fixed-slot template)
    OR blocks [{type, fields}] + form_section + form_module   (dnd template)
"""
import importlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402


def load_family():
    cfg = json.loads((ROOT / "config" / "config.json").read_text())
    return importlib.import_module(f"families.{cfg['family']}.extract"), cfg


def main():
    family, cfg = load_family()
    out_dir = ROOT / "manifests"
    out_dir.mkdir(exist_ok=True)
    for path in sorted((ROOT / "source").glob("*.html")):
        manifest = family.extract(path)
        out = out_dir / (path.stem.lower().replace("_", "-").replace(" ", "-") + ".json")
        out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print(f"{out.name}: /{manifest['slug']}")


if __name__ == "__main__":
    sys.exit(main())
