#!/usr/bin/env python3
"""Sync HubSpot landing pages from manifests/*.json (an idempotent sync).

Existing drafts are updated in place (matched by slug), missing pages are
created as drafts, and PUBLISHED pages are skipped — once live, copy edits
happen in the HubSpot editor, never by re-import. --update-published stages
content into a published page's draft buffer for human review instead.

Two manifest shapes are supported:
  * "widgets"  — fixed-slot coded templates ({% module %} tags); values are
    pushed per module name.
  * "blocks"   — drag-and-drop templates (dnd_area); an ordered block list is
    converted to a layoutSections tree (custom_widget nodes keyed by numeric
    module_id, resolved from the portal at runtime).

Usage:
  python scripts/create_pages.py --dry-run
  python scripts/create_pages.py
  python scripts/create_pages.py --inspect <pageId>
  python scripts/create_pages.py --only <slug-tail>

Token comes from .env (HUBSPOT_ACCESS_TOKEN) or the environment. Settings
come from config/config.json (copy config.example.json).

VERIFY THE SHAPE FIRST on a new portal: create one page, --inspect it, and
compare with --dry-run before bulk-creating (see PLAYBOOK.md phase 6).
"""
import argparse
import json
import os
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402
API = "https://api.hubapi.com/cms/v3/pages/landing-pages"


def load_dotenv():
    """Fill os.environ from ROOT/.env (KEY=value lines); env vars win."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv()


def fetch_existing(headers):
    """Map slug -> page summary for every non-archived landing page."""
    pages, url = {}, f"{API}?limit=100"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        for p in data.get("results", []):
            pages[p["slug"]] = p
        url = (data.get("paging") or {}).get("next", {}).get("link")
    return pages


def load_config():
    path = ROOT / "config" / "config.json"
    if not path.exists():
        sys.exit("config/config.json missing — copy config.example.json and fill it in")
    return json.loads(path.read_text())


def resolve_assets(node, base_url):
    """Swap asset://<file> placeholders for File Manager URLs."""
    if isinstance(node, dict):
        return {k: resolve_assets(v, base_url) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_assets(v, base_url) for v in node]
    if isinstance(node, str) and node.startswith("asset://"):
        return f"{base_url.rstrip('/')}/{node[len('asset://'):]}"
    return node


def build_widgets(manifest, cfg):
    widgets = {}
    for name, fields in manifest["widgets"].items():
        # send EXPLICIT empty values ("" / []) rather than omitting fields:
        # an absent field makes HubSpot render the module's fields.json
        # DEFAULT, silently resurrecting removed content
        body = {k: ("" if v is None else v) for k, v in fields.items()}
        if body.pop("__form__", None) or name == manifest.get("form_module"):
            body["form"] = cfg["form"]
        widgets[name] = {"body": body}
    return widgets


_MODULE_IDS = None


def module_ids(headers):
    """Map /theme/modules/<name> -> numeric module id (dnd nodes need ids)."""
    global _MODULE_IDS
    if _MODULE_IDS is None:
        r = requests.get("https://api.hubapi.com/content/api/v4/custom_widgets",
                         headers=headers, params={"limit": 500}, timeout=30)
        r.raise_for_status()
        _MODULE_IDS = {m["path"].split("/")[-1]: m["id"] for m in r.json().get("objects", [])}
    return _MODULE_IDS


def build_dnd_module(idx, module_type, fields, cfg, headers):
    params = {k: ("" if v is None else v) for k, v in fields.items()}
    if module_type.endswith("-form"):
        params["form"] = cfg["form"]
    mid = module_ids(headers).get(module_type)
    if mid is None:
        sys.exit(f"module {module_type} not found in portal — upload the theme first")
    params["module_id"] = mid
    params["schema_version"] = 2
    return {
        "name": f"module_{idx}",
        "type": "custom_widget",
        "cells": [], "cssClass": "", "cssId": "", "cssStyle": "",
        "params": params,
        "rowMetaData": [], "rows": [],
    }


def build_blocks_payload(manifest, cfg, headers):
    rows = []
    for i, block in enumerate(manifest["blocks"]):
        rows.append({"0": build_dnd_module(i, block["type"], block["fields"], cfg, headers)})
    payload = {
        "name": manifest["internal_name"],
        "slug": manifest["slug"],
        "templatePath": f"{cfg['theme_path']}/{manifest['template_file']}",
        "htmlTitle": manifest["html_title"],
        "metaDescription": manifest["meta_description"] or "",
        "state": "DRAFT",
        "layoutSections": {"main": {
            "name": "main", "type": "CELL",
            "cells": [], "cssClass": "", "cssId": "", "cssStyle": "",
            "params": {}, "rowMetaData": [],
            "rows": rows,
        }},
    }
    if manifest.get("form_section") is not None:
        form_body = dict(manifest["form_section"])
        form_body["form"] = cfg["form"]
        payload["widgets"] = {manifest.get("form_module", "lp_form"): {"body": form_body}}
    if cfg.get("domain"):
        payload["domain"] = cfg["domain"]
    if manifest.get("noindex"):
        payload["headHtml"] = '<meta name="robots" content="noindex">'
    return payload


def build_payload(manifest, cfg, headers=None):
    if manifest.get("blocks"):
        return build_blocks_payload(manifest, cfg, headers)
    payload = {
        "name": manifest["internal_name"],
        "slug": manifest["slug"],
        "templatePath": f"{cfg['theme_path']}/{manifest['template_file']}",
        "htmlTitle": manifest["html_title"],
        "metaDescription": manifest["meta_description"] or "",
        "state": "DRAFT",
        "widgets": build_widgets(manifest, cfg),
    }
    if cfg.get("domain"):
        payload["domain"] = cfg["domain"]
    if manifest.get("noindex"):
        # per-page head override; noindex at launch per the source comments
        payload["headHtml"] = '<meta name="robots" content="noindex">'
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print payloads, POST nothing")
    ap.add_argument("--inspect", metavar="PAGE_ID", help="GET one page and dump its JSON")
    ap.add_argument("--delete", metavar="PAGE_ID", help="delete (archive) one page by id")
    ap.add_argument("--only", metavar="SLUG", help="limit to one manifest by slug suffix")
    ap.add_argument("--update-published", action="store_true",
                    help="stage manifest content into published pages' DRAFT buffer "
                         "(live page untouched; review + publish in HubSpot)")
    args = ap.parse_args()

    token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not token and not args.dry_run:
        sys.exit("set HUBSPOT_ACCESS_TOKEN (private app token with cms.pages write scope)")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if args.delete:
        r = requests.delete(f"{API}/{args.delete}", headers=headers, timeout=30)
        r.raise_for_status()
        print(f"deleted page {args.delete}")
        return

    if args.inspect:
        r = requests.get(f"{API}/{args.inspect}", headers=headers, timeout=30)
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))
        return

    cfg = load_config()
    existing = {}
    if token:
        try:
            existing = fetch_existing(headers)
        except requests.HTTPError as exc:
            if not args.dry_run:
                sys.exit(f"could not list existing pages (bad token?): {exc}")
            print(f"warning: could not list existing pages ({exc}); dry-run assumes all-create")
    manifest_paths = sorted((ROOT / "manifests").rglob("*.json"))
    for path in manifest_paths:
        manifest = resolve_assets(json.loads(path.read_text()), cfg["asset_base_url"])
        if args.only and manifest["slug"].split("/")[-1] != args.only:
            continue
        payload = build_payload(manifest, cfg, headers)
        page = existing.get(manifest["slug"])
        published = page is not None and "PUBLISHED" in (page.get("currentState") or "")
        if published:
            action = "stage into draft buffer" if args.update_published else "skip (published)"
        else:
            action = "update" if page else "create"
        if args.dry_run:
            print(f"===== {path.name} — would {action} =====")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue
        if published and not args.update_published:
            # source-of-truth rule: once published, the live page is never
            # overwritten by re-import. --update-published stages into the
            # draft buffer for human review instead.
            print(f"skipped {path.name}: /{manifest['slug']} is PUBLISHED "
                  f"(last edited {page.get('updatedAt', '?')}) — "
                  f"use --update-published to stage a reviewable draft")
            continue
        if published:
            payload.pop("slug", None)
            payload.pop("state", None)  # draft buffer has no state of its own
            r = requests.patch(f"{API}/{page['id']}/draft", headers=headers, json=payload, timeout=30)
            if r.status_code < 300:
                print(f"staged {path.name}: draft buffer of /{manifest['slug']} updated — "
                      f"review and publish: https://app.hubspot.com/pages/{cfg['portal_id']}/editor/{page['id']}/content")
                continue
        elif page:
            payload.pop("slug", None)  # unchanged; avoids needless conflict checks
            r = requests.patch(f"{API}/{page['id']}", headers=headers, json=payload, timeout=30)
        else:
            r = requests.post(API, headers=headers, json=payload, timeout=30)
        if r.status_code >= 300:
            print(f"FAILED {path.name}: {r.status_code} {r.text}", file=sys.stderr)
            continue
        result = r.json()
        verb = "updated" if page else "created"
        print(f"{verb} {path.name}: id={result.get('id')} url={result.get('url', '(draft)')}")


if __name__ == "__main__":
    main()
