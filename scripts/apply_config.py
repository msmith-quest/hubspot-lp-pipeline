#!/usr/bin/env python3
"""Render families/<family>/theme-src into theme-build/ with config applied.

Theme sources may contain:
  * tokens        __GTM_CONTAINER_ID__ — replaced with config values.
  * guard blocks  <!-- IF:tracking.gtm_container_id --> ... <!-- ENDIF -->
                  — removed entirely when the config value is empty, so a
                  portal without GTM ships none of that code. Guards cannot
                  nest.

Customer-specific JS (CMP bootstraps, schedulers, pixels) is NOT part of
the shared theme: point config "custom_js" at a file in your working root
and it is copied to theme-build/js/custom.js and loaded by the template.

theme-build/ is what you upload:  hs cms upload theme-build <theme_path>
"""
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402

TOKENS = {
    "__GTM_CONTAINER_ID__": ("tracking", "gtm_container_id"),
}

GUARD = re.compile(
    r"(?:<!--|/\*)\s*IF:([a-z_.]+)\s*(?:-->|\*/)(.*?)(?:<!--|/\*)\s*ENDIF\s*(?:-->|\*/)",
    re.S,
)


def cfg_get(cfg, dotted):
    cur = cfg
    for part in dotted.split("."):
        cur = cur.get(part, "") if isinstance(cur, dict) else ""
    return cur or ""


def main():
    cfg = json.loads((ROOT / "config" / "config.json").read_text())
    src = ROOT / "families" / cfg["family"] / "theme-src"
    build = ROOT / "theme-build"
    if build.exists():
        shutil.rmtree(build)
    shutil.copytree(src, build)
    # customer-supplied JS (CMP bootstrap, scheduler wiring, pixels...):
    # ingested into the theme at build; the template references it behind
    # an IF:custom_js guard. Path is relative to the working root.
    custom = cfg.get("custom_js") or ""
    if custom:
        custom_path = (ROOT / custom).resolve()
        (build / "js").mkdir(exist_ok=True)
        shutil.copyfile(custom_path, build / "js" / "custom.js")
    for path in build.rglob("*"):
        if path.suffix not in (".html", ".css", ".js", ".json"):
            continue
        text = path.read_text()
        text = GUARD.sub(lambda m: m.group(2) if cfg_get(cfg, m.group(1)) else "", text)
        for token, keys in TOKENS.items():
            text = text.replace(token, cfg_get(cfg, ".".join(keys)))
        path.write_text(text)
    print(f"theme-build/ rendered from families/{cfg['family']}/theme-src "
          f"(upload with: hs cms upload theme-build {cfg['theme_path']})")


if __name__ == "__main__":
    sys.exit(main())
