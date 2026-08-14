# The AI-to-HubSpot Landing Page Playbook

How to run a production pipeline where an AI design tool (or any designer)
produces landing pages as HTML files, and those pages become editable,
tracked, branded HubSpot pages — repeatably, safely, and without anyone
hand-rebuilding markup in a page editor.

This playbook was distilled from a real production migration: two design
families, ~25 pages, forms, consent-gated analytics, and a scheduling
integration. Every rule below exists because skipping it cost us time.

The core idea:

```
designer AI ──HTML──▶ triage ──▶ extract ──▶ manifests ──▶ sync ──▶ HubSpot drafts ──▶ human publishes
                        │
                        └─▶ REVIEW: new design family → build template + modules ONCE,
                            then every future page is a content-only import
```

**Templates and code carry the design. Manifests carry the content. The
sync is idempotent. Published pages are never overwritten by machines.**

---

## Phase 0 — Prerequisites

- A HubSpot portal with CMS pages (Marketing Hub Pro / CMS Hub).
- The HubSpot CLI: `npm i -g @hubspot/cli` (needs Node ≥ 20.10), then
  `hs init` with a personal access key. This authenticates *design manager*
  operations (theme upload, File Manager).
- An API credential for *page* operations: a private app token or Service
  Key with the CMS landing-pages scope (often surfaced only as the umbrella
  `content` scope). Optionally add the `forms` scope — invaluable for
  debugging form behavior (see phase 7). Put it in `.env` as
  `HUBSPOT_ACCESS_TOKEN`; it is gitignored.
- `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Copy `config/config.example.json` → `config/config.json` and fill it in.

## Phase 1 — The intake contract

Incoming pages must be **one plain, self-contained HTML file each**. No
React bundles, no loaders, no external JS. If a preview needs JavaScript to
display content, it is the wrong format — send it back.

Each file carries its own metadata:

- `<title>`, `<meta name="description">`, and (for pre-launch pages)
  `<meta name="robots" content="noindex">`.
- A **review-chrome bar** at the top: a visually distinct strip containing
  the page ID and the intended URL slug. The pipeline reads the slug from
  it — filenames are NOT the slug source. The template never renders it.
- A **changelog comment** at the top:
  `<!-- REV YYYY-MM-DD: copy-only | copy+design | new page — summary -->`
  `copy-only` revisions can import automatically; anything else gets
  human review. Never write literal HTML tag names (like the style tag) as
  *text inside comments* — parsers reading the raw file will trip on them.
- Every `<section>` has an `aria-label`. Unlabeled sections can only import
  as raw-HTML blobs that editors can't edit field-by-field.
- Internal working notes live in HTML comments or the chrome bar only —
  never in visible copy. Visible internal text ships by accident.

Give your design tool these rules as project instructions — see
`docs/design-handoff-instructions.md` for a paste-ready template. The
contract is enforced by triage regardless, so a violated rule is caught,
not shipped.

## Phase 2 — Triage every incoming file

```bash
.venv/bin/python scripts/triage.py path/to/New_Page.html
```

Two checks, and the second is the one that saves you:

1. **Structure** — section labels vs. the family's expected set. Unknown
   sections mean module work before import.
2. **Coverage** — every visible text chunk in the file must appear in the
   extracted manifest. Anything the extractor would **silently drop** is
   listed. A 95%-compatible page importing with 5% of its copy missing is
   the failure mode nobody notices until production; this check makes it
   impossible.

`FITS` → content-only import (phase 4 onward). `REVIEW` → a human looks at
the listed gaps: either build/extend modules, or confirm the drop is
intentional (e.g. placeholder form markup the template replaces).

## Phase 3 — Building a design family (once per design system)

A *family* = one design system: a coded template, a set of modules, and an
extractor. You build it once; afterwards every page in that family is a
few-minute import. The `customers/demo/families/starter/` directory is a
complete worked example. The recipe:

1. **Fingerprint the corpus.** Across all pages of the family, list each
   page's ordered sections and the distinctive block types inside them
   (grep section labels + CSS classes). This tells you:
   - the universal backbone (always-present sections),
   - the variable middle (blocks that appear on some pages, possibly in
     different orders),
   - the per-page repeat counts (cards, FAQs...).
2. **Choose the template architecture.**
   - Fixed section order across pages → a fixed-slot template:
     `{% module %}` tags in order, optional modules render nothing when
     empty. Content syncs via the `widgets` API property. Simplest; start
     here (the starter family does this).
   - Variable composition/order → a `dnd_area` template with one module
     per block type; content syncs via `layoutSections`. More powerful,
     more API surface (see gotchas: module IDs).
3. **Dump one representative instance of each block** from the corpus and
   transplant its markup into a module, replacing content with HubL fields.
   Keep the source's inline styles verbatim — pixel parity beats elegance
   for imported designs. Repeaters (`"type": "group"` with `occurrence`)
   absorb per-page count differences.
   **Mind reserved field names** — see `docs/hubspot-gotchas.md`. `label`,
   `name`, and `body` will fail theme validation as module field names.
4. **Union the CSS.** If pages ship per-page style blocks, merge at the
   RULE level: dedupe identical selectors, verify identical bodies (any
   same-selector conflict needs a human), merge `@media` blocks by content.
   Strip HTML comments from the head before extracting style blocks.
5. **Write the extractor** (`families/<name>/extract.py`): parse each
   section into module fields, mirroring `fields.json` names exactly.
   Classic traps: hidden success-state markup shadowing the visible
   heading; trailing paragraphs after grids; content in hero chips/ratings
   outside the main slots. The coverage check in triage will catch what
   you miss — iterate until it reports zero drops for the whole corpus.
6. **Render local previews** (`scripts/render_preview.py` evaluates the
   HubL subset — no HubSpot needed) and eyeball them against the originals
   over any static file server. Then run the corpus-wide coverage check.
   **Gate: zero dropped text chunks across every page of the family.**

## Phase 4 — Manifests

```bash
.venv/bin/python scripts/extract_assets.py     # base64 images -> assets/
.venv/bin/python scripts/build_manifests.py    # source/*.html -> manifests/
.venv/bin/python scripts/apply_config.py       # theme-src -> theme-build/
.venv/bin/python scripts/render_preview.py     # manifests -> preview/
```

Manifests are the content contract: page meta + module field values (or an
ordered block list for dnd families). Images stay as `asset://<file>`
placeholders until uploaded; `create_pages.py` resolves them against
`asset_base_url`.

## Phase 5 — Theme + assets to HubSpot

```bash
hs cms upload theme-build <your-theme-path>
hs filemanager upload assets <folder>
```

Verify one uploaded image's public URL with curl (the File Manager host is
region-specific and may redirect once — use the FINAL URL as
`asset_base_url`). Upload brand fonts the same way and point your CSS
`@font-face` at them.

## Phase 6 — Page sync

`scripts/create_pages.py` is an idempotent sync, not a creator:

- existing **draft** (matched by slug) → updated in place
- **missing** page → created as a draft
- **published** page → refused, with the last-edited timestamp shown;
  `--update-published` stages content into HubSpot's **draft buffer**
  instead (live page untouched, review link printed, publishing stays a
  human act)

On a NEW portal, verify the storage shape before bulk-creating: run with
`--only <slug>` for one page, then `--inspect <pageId>` and confirm your
field values round-tripped. For dnd families the editor is the render
check — "Add [missing type] value" rows mean the module reference is
wrong (see gotchas: `module_id`).

`--dry-run` prints every payload and the planned action per page.

## Phase 7 — Forms

Use a native HubSpot form module (`"type": "form"` field) — never re-POST
a hand-rolled form. The form is chosen per page in the editor or injected
by the sync from config; HubSpot owns validation, submission, contact
creation, and tracking.

Things that will bite you (details + fixes in `docs/hubspot-gotchas.md`):

- The modern renderer ("Forms V4") shows an **email-first progressive
  reveal** when contact lookup is on — it looks like a multi-step form and
  it isn't. It's a form setting, not markup.
- Form definition changes only take effect on **publish** ("Review and
  update"), and the publish flow fails quietly if you don't complete it —
  verify via the API (`forms` scope) rather than trusting the editor.
- CMS page renders **bake the form definition into the page cache**; form
  publishes lag on live pages. `?hsCacheBuster=<anything>` forces a fresh
  page render.
- Style forms with **CSS only**, targeting the renderer's stable `hsfc-*`
  classes, `!important` on contested properties, scoped under
  `.hs-form-html`. See the starter family's `landing.css` for a complete
  skin. Never do JS DOM surgery on the form — React re-renders will fight
  you.

## Phase 8 — Tracking & integrations

- **Consent + GTM belong in the template**, not portal settings: consent
  defaults must execute before `gtm.js` loads, and only code you own can
  guarantee that ordering. The starter template ships the region-scoped
  consent-mode pattern; keep it in sync with your main site's.
- Gate the whole tracking stack on `{% if not is_in_editor %}` — kills
  editor console noise and keeps editor sessions out of analytics.
- **Org-specific integrations** (CMP SDK loaders, post-submit schedulers,
  extra pixels) do NOT belong in the shared theme: put them in a JS file
  in your working root and point config `custom_js` at it — the build
  ingests it and the template loads it after the shared JS. Reference
  implementations (CMP bootstrap; the scheduler capture pattern for V4
  forms — teardown timing, nameless widgets, click snapshots) are in
  `docs/tracking-integrations.md`. Trigger schedulers from the form's
  confirmed-submission event only, and verify with a stubbed submit
  before any real submission.

## Phase 9 — Publish governance

- **Source-of-truth rule:** the HTML file is canonical until the page is
  published. After that, copy edits happen in the HubSpot editor, and
  re-imports must not overwrite them. The sync enforces this in code.
- Pages launch `noindex` (per-page head HTML, set by the sync); lift it
  deliberately per page when cleared.
- `--update-published` overwrites the page's *draft buffer* — fine when
  imports are the copy channel, destructive if marketers also draft in
  the editor. Pick one channel per page and say so out loud.

## Phase 10 — The steady state

Once a family exists, the loop per page is minutes:

```
new HTML → triage → (FITS) → cp to source/ → extract → manifests → preview → sync → QA draft → publish
```

`REVIEW` verdicts route to a human. New design families repeat phase 3 —
and each one makes the next cheaper, because the machinery is shared.

Feed lessons back into the intake contract: every time a handoff surprises
the pipeline, the fix is usually one new sentence in the design tool's
instructions, not more code.
