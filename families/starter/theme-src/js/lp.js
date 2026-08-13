(function () {
  'use strict';

  // ---- hide the <hs-cmsf-branding> badge the form embed injects -----------
  // It can land inside an open shadow root where page CSS can't reach, so
  // walk shadow roots too. MutationObserver catches (re)renders; the capped
  // interval is a fallback that stops after the first successful hide.
  function hideBranding(root) {
    var found = false;
    root.querySelectorAll('hs-cmsf-branding').forEach(function (el) {
      el.style.setProperty('display', 'none', 'important');
      found = true;
    });
    root.querySelectorAll('*').forEach(function (el) {
      if (el.shadowRoot) { found = hideBranding(el.shadowRoot) || found; }
    });
    return found;
  }
  var observer = new MutationObserver(function () { hideBranding(document); });
  observer.observe(document.body, { childList: true, subtree: true });
  var tries = 0;
  var poll = setInterval(function () {
    if (hideBranding(document) || ++tries > 40) { clearInterval(poll); }
  }, 250);
  hideBranding(document);

})();
