# Design-side instructions (template)

Paste the block below into the project instructions of whatever AI design
tool produces your landing pages (or hand it to a human designer). Replace
the ALL-CAPS placeholders. Keep it short enough that it's actually
followed; the pipeline's triage enforces the rules regardless, so a
violation is caught at import, not shipped.

Evolve this file every time a handoff surprises the pipeline — one new
sentence here is cheaper than new code.

---

## Export rules for COMPANY landing pages (HubSpot import pipeline)

These pages are converted by an automated pipeline into HubSpot templates.
The pipeline reads the HTML structure directly, so consistency matters
more than cleverness.

**Export format**
- Deliver each page as ONE plain, self-contained .html file — static
  markup, no React, no loaders, no "offline bundle" exports, no external
  JS. If a preview needs JavaScript to display content, it's the wrong
  format.
- Keep the same base filename across revisions of the same page.
- Every page includes in the head: a title ending "| COMPANY", a meta
  description, and the robots noindex tag.
- Top of every file, a changelog comment:
  `REV YYYY-MM-DD: copy-only | copy+design | new page — summary`
  (as an HTML comment). copy-only imports automatically; design changes
  get human review. Never write literal HTML tag names as text inside
  comments — say "the style block" in words instead.
- Keep the review-chrome bar at the top with the page ID and the intended
  URL slug. The slug in the chrome bar is the source of truth for the
  page's URL — filenames are not.
- Internal working notes belong ONLY in HTML comments or the chrome bar —
  never in visible page copy or the footer.

**Structure**
- Every section element gets an aria-label, no exceptions. Sections
  without one import as raw-HTML blobs marketers can't edit field-by-field.
- Follow the established family structure exactly:
  LIST YOUR FAMILY'S SECTIONS / CLASS VOCABULARY HERE.
  Renaming or restyling a structural class is a design change — declare it.
- A genuinely NEW kind of section is welcome but must be flagged with a
  `NEW SECTION: name — what it is` comment at the top of the file, so a
  matching editable module gets built before import.
- The demo form internals are replaced by the live HubSpot form at
  import — keep placeholder form markup consistent and don't redesign it
  without flagging.

**Design tokens**
- Fonts are fixed: LIST YOUR FONTS. No new fonts.
- Colors come from the established token set. New tokens are a design
  change — declare them.

**Content hygiene**
- Embed images as base64 data URIs with meaningful alt text (or keep
  stable CDN URLs, per your family's convention); reuse identical bytes
  when an image hasn't changed.
- Translated pages: translate visible copy only; keep structure and class
  names identical.
