# hubspot-lp-pipeline

Turn AI-designed (or hand-designed) HTML landing pages into editable,
tracked, branded **HubSpot** pages — through an automated, verifiable
pipeline instead of hand-rebuilding markup in a page editor.

```
designer AI ──HTML──▶ triage ──▶ extract ──▶ manifests ──▶ idempotent sync ──▶ HubSpot drafts ──▶ human publishes
```

Built from a real production migration (two design families, ~25 pages,
forms, consent-gated GTM, scheduler integration). The docs encode the
gotchas that cost the most time — reserved module field names, the
`layoutSections` module-ID trap, HubSpot Forms V4's teardown timing and
nameless widgets, form-publish caching, and more.

## What's in the box

| Path | What it is |
|---|---|
| [`PLAYBOOK.md`](PLAYBOOK.md) | The process, phase 0 → steady state. Start here. |
| `scripts/triage.py` | Does an incoming page fit the template? Structure + **text-coverage** check (nothing imports with silently dropped copy). |
| `scripts/build_manifests.py` | Family extractor → per-page content manifests (JSON). |
| `scripts/apply_config.py` | Renders the family's theme source with your config (GTM/CMP/scheduler blocks vanish when unconfigured). |
| `scripts/render_preview.py` | Local previews via a mini-HubL evaluator — parity-check against the source HTML with no HubSpot in the loop. |
| `scripts/create_pages.py` | Idempotent page sync: update drafts by slug, create missing, refuse published (`--update-published` stages a reviewable draft buffer). Supports fixed-slot (`widgets`) and drag-and-drop (`layoutSections`) templates. |
| `scripts/extract_assets.py` | Pulls base64 images out of source pages for File Manager upload. |
| `customers/demo/` | A complete worked example customer: the `starter` family (template, four modules, form-skin CSS, consent+GTM bootstrap, extractor) plus the acme sample page. Copy it to start your own. Org-specific JS (CMP SDK, schedulers, pixels) plugs in via the `custom_js` config hook. |
| `docs/hubspot-gotchas.md` | The expensive lessons, so you don't repay them. |
| `docs/design-handoff-instructions.md` | Paste-ready rules for the design tool producing your pages. |
| `docs/tracking-integrations.md` | Consent-before-GTM, post-submit scheduling, pixel patterns. |
| `skill/` | A Claude Code skill wrapping the workflow. |

## Quickstart (no HubSpot needed for the first three steps)

Everything runs inside a customer directory; `customers/demo/` is the
worked example, already populated with the acme sample page:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd customers/demo
cp config/config.example.json config/config.json   # fill in as you go

../../.venv/bin/python ../../scripts/triage.py source/acme-home.html   # -> FITS
../../.venv/bin/python ../../scripts/extract_assets.py
../../.venv/bin/python ../../scripts/build_manifests.py
../../.venv/bin/python ../../scripts/apply_config.py
../../.venv/bin/python ../../scripts/render_preview.py
# open preview/ over any static server and compare page vs original
```

Then connect a portal (PLAYBOOK phases 0 and 5–6), still from
`customers/demo/`:

```bash
npm i -g @hubspot/cli && hs init
hs cms upload theme-build my-lp-theme
cp .env.example .env                     # paste your API token
../../.venv/bin/python ../../scripts/create_pages.py --dry-run
../../.venv/bin/python ../../scripts/create_pages.py --only acme-home
../../.venv/bin/python ../../scripts/create_pages.py --inspect <pageId>   # verify shape
```

## Multi-customer / consultancy layout

The scripts resolve their working root via `LP_ROOT`, or by finding the
nearest ancestor of your current directory containing `config/config.json`.
Keep this repo as the shared toolkit and run any number of self-contained
customer directories against it, each holding its own `config/`,
`families/`, `source/`, `manifests/`, and `.env`:

```bash
cd customers/<name>
python ../../scripts/triage.py source/new-page.html   # root auto-discovered
```

A customer directory needs a `families/__init__.py` so its extractors are
importable. Everything under `customers/` except the `demo` example is
gitignored, so real customer directories can be versioned as their own
private repos. To start a new customer, copy the demo:

```bash
cp -r customers/demo customers/<name>
```

## The three rules the whole thing rests on

1. **Templates and code carry the design; manifests carry the content.**
   Build a design family once; every subsequent page is a content import.
2. **Nothing imports with silently dropped copy.** Triage's coverage check
   is the gate: every visible text chunk in the source must survive into
   the manifest, or a human looks first.
3. **Machines never overwrite published pages.** The sync updates drafts,
   creates missing pages, and stages published-page changes into a
   reviewable draft buffer. Publishing is a human act.

## License

MIT
