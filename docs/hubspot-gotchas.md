# HubSpot CMS gotchas (the expensive kind)

Everything here was learned the hard way on a production migration. None of
it is well-documented upstream.

## Themes & modules

- **Reserved module field names.** `label`, `name`, and `body` are rejected
  as field `name`s in a module's fields.json — but only at *theme-level*
  validation, which fails one file at a time (whack-a-mole). Uploading each
  module folder individually surfaces all errors in one round. Prefix your
  fields (`stat_label`, `product_name`, `rich_body`) from the start.
- **CLI v8 syntax**: everything lives under `hs cms ...`
  (`hs cms upload`, `hs cms list`). `hs filemanager upload` for assets.
  The CLI needs Node ≥ 20.10 — on 18.x it dies on import-attributes syntax.
- **File Manager URLs** are region-specific and redirect once
  (`...-na1.net` → `...-na2.net`). Curl an uploaded file with `-L` and use
  the FINAL url in config.
- **Template annotation** (`templateType: page`, `isAvailableForNewContent`)
  must be the first comment in a coded template. Coded templates don't get
  theme cards in the page-creation flow — they're behind the template
  picker's search / "All templates" view.
- Don't ship your own `<meta name="viewport">` — HubSpot injects one, and
  two of them trips the page audit.
- **No HTML-looking strings in CSS files — even in comments.** Upload
  validation content-sniffs each file; a tag-shaped string in a CSS
  comment (writing the html element in angle brackets was enough) fails
  the whole file with "line 0: Can not save html to a css file", while
  the rest of the theme uploads around it — templates can go live
  referencing a stylesheet that never arrived. Grep new CSS for `<`
  before upload, and read the CLI output for per-file errors, not just
  the final line.

## Pages API (v3, `/cms/v3/pages/landing-pages`)

- **Fixed-slot templates**: per-page module values live in
  `widgets: {module_name: {body: {field: value}}}`. Verify the shape by
  creating one page, then GET it — values round-trip exactly.
- **dnd templates**: values live in `layoutSections`. The tree is
  `{area_name: {type: "CELL", rows: [{"0": <node>}], ...}}` where each
  module node is `{type: "custom_widget", params: {...fields}}` — and the
  module reference MUST be the **numeric `module_id`** (+
  `schema_version: 2`) from `/content/api/v4/custom_widgets`, not the
  module path. With a path, the editor renders empty rows saying
  "Add [missing type] value".
- **`noindex`** is per-page: `headHtml: '<meta name="robots" content="noindex">'`.
- **Draft buffer**: `PATCH .../{id}/draft` updates a published page's
  pending draft without touching the live page. Publishing remains a
  separate act (UI, or `POST .../draft/push-live` if you dare).
- Deleting = archiving (`DELETE .../{id}`). Slug frees up.
- **Page render caching** is aggressive (hours). `?hsCacheBuster=<x>`
  forces a fresh server render; `?hsDebug=true` bypasses more but skips
  form prefetch (form markup won't be in the HTML at all).

## Forms (the modern "V4" renderer)

- The CMS form module renders **inline in your page DOM** (no iframe) via
  `HubSpotFormsV4`, with stable `hsfc-*` classes and `data-hsfc-id`
  attributes. This is what makes CSS styling, badge hiding, and field
  capture possible at all.
- **Events**: `hs-form-event:on-ready`, `:on-submission`,
  `:on-submission:success` — window-level CustomEvents. The legacy
  `hsFormCallback` postMessage NEVER fires from this renderer.
- **Teardown timing**: the renderer clears/replaces the form DOM *before*
  its submission events fire. Reading field values at submit time returns
  empties. Capture continuously as the user types instead.
- **Nameless widgets**: dropdowns and phone render as custom comboboxes —
  no `<select>`, no `name` attribute, and picking an option is a click
  that fires no input event. Resolve fields by label text and snapshot on
  (debounced) clicks inside the form. Hidden fields (utm_*, click IDs)
  never fire events either — snapshot the whole form, not the changed
  field.
- **Email-first reveal**: with contact-lookup prefill enabled
  (`prePopulateKnownValues`), the renderer shows ONLY the email field
  until a valid email is entered, then reveals the rest. It looks exactly
  like a multi-step form and isn't one. Toggle the setting if you want all
  fields visible.
- **Form publishes fail quietly.** "Review and update" has a final confirm
  that's easy to miss; the editor keeps saying "Saved with unpublished
  changes". Verify what's actually published via
  `GET /marketing/v3/forms/{guid}` (needs the `forms` scope).
- Form definitions are **baked into CMS page renders** — a form publish
  reaches live pages only after the page cache re-renders.
- **Styling**: target `hsfc-*` classes, scope under `.hs-form-html`, use
  `!important` on font/border/radius/width (HubSpot's injected default
  sheet competes there). Field labels/order/placeholders are form-editor
  territory; CSS can't reach them.
- The `hs-cmsf-branding` badge: hide via CSS
  (`hs-cmsf-branding{display:none!important}`) plus a shadow-root-walking
  fallback in JS. Check your plan's terms before removing branding.
- Embedding the **same form twice** on a page (inline + modal) works; each
  instance gets unique ids.
- **Never put the `hs-form-html` class on your own wrappers.** The V4 embed
  script boots every `.hs-form-html` element on the page; one without the
  generated `data-form-id`/`data-portal-id` attributes logs "has missing or
  invalid data attributes" and can leave the real targets unrendered. The
  class belongs exclusively to the target divs `{% form %}` generates.
- **Form-type module fields reject `"default": null`** — the binding fails
  silently and `{% form %}` renders nothing. Declare them like the working
  modules: `{"type": "form", "required": true}`, no default. Corollary:
  clone a proven fields.json for new modules instead of writing fresh JSON
  (a nested occurrence-group for an image round-trips as a LIST in HubL,
  which is the same class of quiet breakage).
- Multi-step vs single-step is form-definition structure ("steps" in the
  editor); the same form serves every embed, so flattening it changes
  every page using it.
- **The post-submit state can't be removed.** A V4 embed always renders
  something after submit — an inline message or a redirect; the forms UI
  has no "stay on the form" option (the message text is per-embed:
  `response_message` on `{% form %}`). To hand off to a scheduler without
  the thank-you flash, hide it with page CSS/JS on the success event and
  reveal it if the scheduler never arrives — it's the blocked/no-consent
  fallback (tracking-integrations.md, rule 7).

## Module field defaults resurrect removed content

If a page's stored module body LACKS a field, HubSpot renders the module's
fields.json DEFAULT for it. Two consequences:

- Never put real production copy in module defaults — when a later design
  round removes that content, any page without an explicit stored value
  quietly renders the old copy again ("ghost" badges, callouts...).
- A sync that OMITS empty fields from its payload triggers exactly that.
  Send explicit empty values ("" / []) so they override the defaults —
  this toolkit's create_pages.py does.

## Repeater `min` occurrence blocks editor saves

A group field with `"occurrence": {"min": 1}` makes the EDITOR refuse to
save any page whose stored value is an empty list ("The list of X requires
at least 1 entries. There are 0.") — the API sync writes the empty value
happily, so the trap only fires later, on a human editing an unrelated
part of the page. When imports are the copy channel and sections come and
go between design rounds, set `min: 0` on every repeater and guard the
module template (`{% if module.<repeater> %}`) so an empty module renders
nothing instead of an empty shell.

## Editor & preview

- The HubSpot editor serves its own **report-only CSP** — every external
  script the preview loads gets logged as a violation. Nothing is blocked;
  it's console noise. Gate tracking on `{% if not is_in_editor %}` and it
  disappears (and your analytics stop counting editor sessions).
- Draft pages are not publicly fetchable; the editor is the render check
  for drafts.

## Scopes & credentials

- Personal access key (CLI) and API tokens are different credentials.
- The granular `cms.pages.landing_pages.*` scopes may not appear in newer
  key-creation flows — the umbrella `content` scope covers them.
- The Forms API needs the `forms` scope; add it to your API credential —
  form debugging without it is screenshot forensics.
