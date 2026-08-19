# Tracking & integrations

## Consent Mode + GTM: ordering is everything

If you run Google Consent Mode, the consent *defaults* must execute before
`gtm.js` loads — synchronously, in the template head. If GTM loads first,
tags can fire once without a resolved default, which silently skews
analytics for a slice of every day's traffic. That ordering can only be
guaranteed in code you own, which is why the GTM snippet belongs in the
template, not in portal settings or a tag-injection feature.

The starter template ships the generic part of the pattern: region-scoped
consent defaults (denied for EEA/UK/CH, granted elsewhere — adjust to your
legal posture), then GTM. Your CMP's SDK loader (OneTrust, Cookiebot, ...)
is organization-specific and belongs in your **custom JS file** (config
`custom_js` — ingested into the theme at build, loaded after the shared
JS). If your main site has the same stack, copy ITS bootstrap verbatim and
keep the two in sync — drift between site and landing pages is a classic
source of unexplained analytics deltas.

A CMP loader for custom.js looks like:

```js
(function () {
  if (/^(localhost|127\.0\.0\.1)$/.test(location.hostname)) { return }
  var s = document.createElement('script');
  s.src = 'https://cdn.cookielaw.org/scripttemplates/otSDKStub.js'; // your CMP
  s.setAttribute('data-domain-script', 'YOUR-CMP-SCRIPT-ID');
  document.head.appendChild(s);
})();
```

Gate the whole stack on `{% if not is_in_editor %}`: editor sessions stay
out of analytics and the editor console stays quiet (see gotchas: the
editor's report-only CSP).

## Post-submit scheduling (Chili Piper pattern)

The goal: after a *confirmed* form submission, open the scheduler with the
lead's details so qualified leads book instantly. Scheduler wiring is
organization-specific, so it lives in your `custom_js` file, not the
shared theme. Rules that survived production:

1. **Trigger on the form's success event only** —
   `hs-form-event:on-submission:success` for HubSpot V4 forms. Never on
   button clicks or step advances.
2. **Capture field values continuously** (see gotchas: V4 teardown and
   nameless widgets): input/change listeners + debounced click snapshots +
   label-based field resolution for nameless dropdown/phone widgets.
   Reference implementation for custom.js:

```js
var liveValues = {};
var LABEL_KEYS = { 'country': 'country', 'industry': 'industry',
                   'phone number': 'phone', 'phone': 'phone' };
function fieldKey(el) {
  if (el.name) { return el.name.split('/').pop(); }
  var wrap = el.closest('[data-hsfc-id="DropdownField"], [data-hsfc-id="Row"]');
  var label = wrap && wrap.querySelector('label');
  var text = label ? label.textContent.replace(/\*/g, '').trim().toLowerCase() : '';
  return LABEL_KEYS[text] || null;
}
function takeSnapshot() {
  document.querySelectorAll('.hs-form-html input, .hs-form-html select').forEach(function (f) {
    if (!f.value) { return; }
    var key = fieldKey(f);
    if (key) { liveValues[key] = f.value; }
  });
}
document.addEventListener('input', function (e) {
  if (e.target.closest && e.target.closest('.hs-form-html')) { takeSnapshot(); }
}, true);
document.addEventListener('change', function (e) {
  if (e.target.closest && e.target.closest('.hs-form-html')) { takeSnapshot(); }
}, true);
document.addEventListener('click', function (e) {
  if (e.target.closest && e.target.closest('.hs-form-html')) { setTimeout(takeSnapshot, 120); }
}, true);
window.addEventListener('hs-form-event:on-submission:success', function () {
  // map liveValues -> your router's lead keys, then e.g.
  // ChiliPiper.submit(DOMAIN, ROUTER, {formType:'HubSpot', trigger:'ThirdPartyForm', lead: {...}});
  liveValues = {};
});
```
3. **Map field names explicitly.** Your form's internal field names
   (`name` for a company-object property, `country_dropdown`, ...) rarely
   match the router's expected lead keys (`Company`, `Country`, ...). Get
   the exact expected keys from the scheduler's own "third-party form"
   snippet in its admin, and check which fields its routing rules key on —
   an empty `Industry` can silently route every lead down the fallback
   path.
4. **Verify with a stub before any real submission**: replace
   `ChiliPiper.submit` with a function that records its arguments, walk
   the real form (type + click widgets), fire the success event, and
   assert the captured lead. No junk leads in the CRM, no noise in the
   router's logs, full confidence in the chain.
5. Degrade silently: if the concierge script never loads (consent refused,
   network), the visitor still gets the form's normal thank-you. A
   scheduling add-on must never break the submit.
6. Load the scheduler script **behind functional-cookie consent** if you
   run a CMP, and preload it once consent exists so the calendar opens
   instantly on submit.
7. **Suppressing the thank-you flash**: a V4 form always renders a
   post-submit state (inline message or redirect) — the forms UI cannot
   remove that step, so when the scheduler takes over it flashes between
   submit and the booking UI. Since you own the page: on the success
   event, set a class on `<html>` whose CSS hides the embed's post-submit
   DOM behind a spinner (hide the container's *children*, not a guessed
   thank-you class — the swapped-in DOM is undocumented), and remove the
   class when the scheduler closes, errors, or never arrives. The inline
   message must stay reachable — it is rule 5's fallback.

## Ad/conversion pixels

Fire lead conversions from the same confirmed-submission signal (usually
via a dataLayer event your GTM tags consume), with a shared event/dedup ID
when a platform supports both pixel + server-side legs. Keep hidden
UTM/click-ID fields on the FORM (form-editor config) so the values land on
the contact record — and remember hidden fields never fire input events
(see gotchas) if you also read them client-side.
