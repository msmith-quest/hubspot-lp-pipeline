"""Extractor for the "starter" family — the reference implementation.

An extractor encodes ONE design family's markup conventions. This one reads
pages shaped like examples/acme-home.html: a review-chrome bar carrying the
slug, then sections labeled Hero / Features / FAQ / Form.

Copy this file when you build a family for your own design system; the
recipe is in PLAYBOOK.md phase 3. Keep the module-field names in sync with
your modules' fields.json — and mind HubSpot's reserved field names
(docs/hubspot-gotchas.md).
"""
import pathlib
import re

from bs4 import BeautifulSoup

# aria-labels triage expects, in page order
EXPECTED_SECTIONS = ["Hero", "Features", "FAQ", "Form"]

# containers whose text the TEMPLATE renders (or that never ships), so
# triage's coverage check must not count them
TEMPLATE_OWNED = [
    {"name": "header"},
    {"name": "footer"},
    {"class_": "review-chrome"},
    {"class_": "form-placeholder"},  # replaced by the live HubSpot form
]


def _text(el):
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _inner(el):
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.decode_contents().strip())


def _slug(soup, path):
    chrome = soup.find(class_="review-chrome")
    if chrome:
        for sp in chrome.find_all(["span", "strong", "code"]):
            t = sp.get_text(strip=True)
            if t.startswith("/"):
                return t.lstrip("/")
    return path.stem.lower().replace("_", "-").replace(" ", "-")


def extract(path: pathlib.Path) -> dict:
    soup = BeautifulSoup(path.read_text(), "html.parser")

    hero = soup.find("section", attrs={"aria-label": "Hero"})
    feats = soup.find("section", attrs={"aria-label": "Features"})
    faq = soup.find("section", attrs={"aria-label": "FAQ"})
    form = soup.find("section", attrs={"aria-label": "Form"})
    desc = soup.find("meta", attrs={"name": "description"})
    slug = _slug(soup, path)

    hero_img = hero.find("img") if hero else None
    widgets = {
        "lp_hero": {
            "eyebrow": _text(hero.find(class_="eyebrow")) if hero else "",
            "headline": _text(hero.h1) if hero else "",
            "subhead": _text(hero.find("p")) if hero else "",
            "cta_label": _text(hero.find("a", class_="cta")) if hero else "Book a demo",
            "image": {
                "src": hero_img.get("src", "") if hero_img else "",
                "alt": hero_img.get("alt", "") if hero_img else "",
                "width": int(hero_img.get("width", 0) or 0) if hero_img else 0,
                "height": int(hero_img.get("height", 0) or 0) if hero_img else 0,
            },
        },
        "lp_features": {
            "heading": _text(feats.h2) if feats else "",
            "cards": [
                {"card_title": _text(c.h3), "card_body": _text(c.find("p"))}
                for c in (feats.find_all(class_="card") if feats else [])
            ],
        },
        "lp_faq": {
            "heading": _text(faq.h2) if faq else "",
            "items": [
                {"question": _text(d.summary), "answer": _inner(d.find(["p", "div"]))}
                for d in (faq.find_all("details") if faq else [])
            ],
        },
        "lp_form": {
            "heading": _text(form.h2) if form else "",
            "subtext": _text(form.find("p")) if form else "",
            "__form__": True,  # create_pages injects the configured form here
        },
    }

    return {
        "file": path.name,
        "template_file": "templates/landing.html",
        "html_title": soup.title.string.strip() if soup.title else "",
        "meta_description": desc["content"].strip() if desc else "",
        "slug": slug,
        "internal_name": f"{path.stem.replace('_', ' ')} — /{slug}",
        "noindex": bool(soup.find("meta", attrs={"name": "robots", "content": "noindex"})),
        "widgets": widgets,
    }
