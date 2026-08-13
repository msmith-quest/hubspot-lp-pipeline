---
name: hubspot-lp-pipeline
description: Import designer-produced HTML landing pages into HubSpot as editable pages — triage incoming files, extract content to manifests, preview locally, and sync drafts idempotently. Use when the user wants to convert HTML landing pages to HubSpot, import LP designs, update HubSpot landing pages from HTML files, or build a new design family (template + modules) for this pipeline.
---

# HubSpot LP pipeline

You are operating the pipeline in this repository (see PLAYBOOK.md for the
full process and docs/hubspot-gotchas.md before touching anything
HubSpot-specific). Core invariants — enforce them even if asked to hurry:

1. Triage before importing anything: `scripts/triage.py <file>` must say
   FITS, or a human decides about the listed gaps.
2. Never bulk-create pages on a portal whose storage shape you haven't
   verified (`--only` one page, then `--inspect` it).
3. Never overwrite a published page; `--update-published` stages a draft
   buffer and a human publishes.
4. No real form submissions during integration testing — stub the
   scheduler (`window.ChiliPiper.submit = recorder`) and fire the form's
   success event synthetically.

## Routine import (existing family)

```
cp <file> source/
.venv/bin/python scripts/triage.py source/<file>          # gate: FITS
.venv/bin/python scripts/extract_assets.py
.venv/bin/python scripts/build_manifests.py
.venv/bin/python scripts/apply_config.py
.venv/bin/python scripts/render_preview.py                # eyeball preview/
hs filemanager upload assets <folder>                     # if new images
.venv/bin/python scripts/create_pages.py --dry-run
.venv/bin/python scripts/create_pages.py --only <slug>    # then full run
```

Report to the user: triage verdict, what changed per page (created /
updated / skipped-published), and anything the coverage check flagged.

## Triage says REVIEW

- Unknown sections → new module work: follow PLAYBOOK phase 3 (fingerprint
  → representative block dump → module with fields → extractor → coverage
  gate at zero drops). Check docs/hubspot-gotchas.md for reserved field
  names BEFORE writing fields.json.
- Dropped text → extend the family extractor until the corpus-wide
  coverage check reports zero, or get the user's explicit confirmation
  that the drop is intentional.

## New portal / first run

Walk PLAYBOOK phases 0, 5, 6 in order. Do not skip the `--inspect` shape
verification. Theme upload failures listing "field name cannot be X" are
reserved-name collisions — rename the module fields, don't fight it.

## Forms & integrations

All form behavior questions route through docs/hubspot-gotchas.md (V4
events, teardown timing, nameless widgets, email-first reveal, publish
caching) and docs/tracking-integrations.md (consent-before-GTM, scheduler
lead mapping). Style forms with CSS only, under `.hs-form-html`.
