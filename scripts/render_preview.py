#!/usr/bin/env python3
"""Render local previews of the theme for parity checks — no HubSpot needed.

Evaluates the SUBSET of HubL this toolkit's themes use ({{ vars }}, if/elif/
else with `not`, ==, |length comparisons, for with loop.first/last,
{% module %}, {% dnd_area %}, {% form %}) against each manifest, producing
preview/<page>.html next to preview/original-<page>.html. Open both over any
static file server and compare.

Run scripts/apply_config.py first — previews render from theme-build/.
This is a build-time QA tool only; HubSpot renders the real thing.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lproot import ROOT  # noqa: E402
BUILD = ROOT / "theme-build"
PREVIEW = ROOT / "preview"

TOKENS = re.compile(r"({%.*?%}|{{.*?}})", re.S)

FORM_PLACEHOLDER = (
    '<div style="border:2px dashed #bbb;border-radius:6px;padding:28px 18px;'
    'text-align:center;color:#667;font-size:14px;line-height:1.5">'
    "HubSpot form renders here<br>(selected per page in the editor)</div>"
)


def asset_url(path):
    # ../css/x.css (relative to templates/) -> ../theme-build/css/x.css
    # (relative to preview/)
    return "../theme-build/" + path.lstrip("./").lstrip("../")


def lookup(ctx, dotted):
    cur = ctx
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return ""
    return "" if cur is None else cur


def eval_expr(expr, ctx):
    expr = expr.strip()
    if " or " in expr:
        return any(eval_expr(part, ctx) for part in expr.split(" or "))
    if " and " in expr:
        return all(eval_expr(part, ctx) for part in expr.split(" and "))
    if expr.startswith("not "):
        return not eval_expr(expr[4:], ctx)
    m = re.match(r"(.+?)\|length\s*>\s*(\d+)$", expr)
    if m:
        return len(lookup(ctx, m.group(1).strip()) or []) > int(m.group(2))
    if "==" in expr:
        left, right = (s.strip() for s in expr.split("==", 1))
        return str(lookup(ctx, left)) == right.strip("\"'")
    return bool(lookup(ctx, expr))


def eval_var(expr, ctx):
    expr = expr.strip()
    if expr in ("standard_header_includes", "standard_footer_includes"):
        return ""
    m = re.match(r"require_css\(get_asset_url\([\"'](.+?)[\"']\)\)", expr)
    if m:
        return f'<link rel="stylesheet" href="{asset_url(m.group(1))}">'
    m = re.match(r"require_js\(get_asset_url\([\"'](.+?)[\"']\)", expr)
    if m:
        return f'<script src="{asset_url(m.group(1))}" defer></script>'
    m = re.match(r"get_asset_url\([\"'](.+?)[\"']\)", expr)
    if m:
        return asset_url(m.group(1))
    if expr == "year":
        return "20XX"
    return str(lookup(ctx, expr))


def parse(tokens, i=0, stop=None):
    nodes = []
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("{%"):
            tag = tok[2:-2].strip()
            word = tag.split()[0]
            if stop and word in stop:
                return nodes, i
            if word == "if":
                branches = []
                cond = tag[3:].strip()
                while True:
                    body, i = parse(tokens, i + 1, stop={"elif", "else", "endif"})
                    branches.append((cond, body))
                    end = tokens[i][2:-2].strip()
                    if end.startswith("elif"):
                        cond = end[5:].strip()
                        continue
                    if end == "else":
                        body, i = parse(tokens, i + 1, stop={"endif"})
                        branches.append((None, body))
                    break
                nodes.append(("if", branches))
            elif word == "for":
                m = re.match(r"for\s+(\w+)\s+in\s+(.+)", tag)
                body, i = parse(tokens, i + 1, stop={"endfor"})
                nodes.append(("for", m.group(1), m.group(2).strip(), body))
            elif word == "dnd_area":
                while i < len(tokens) - 1:
                    i += 1
                    if tokens[i].startswith("{%") and tokens[i][2:-2].strip() == "end_dnd_area":
                        break
                nodes.append(("dnd",))
            elif word == "module":
                m = re.match(r'module\s+"(\w+)"', tag)
                nodes.append(("module", m.group(1)))
            elif word == "form":
                nodes.append(("text", FORM_PLACEHOLDER))
            else:
                raise ValueError(f"unhandled tag: {tag[:60]}")
        elif tok.startswith("{{"):
            nodes.append(("var", tok[2:-2]))
        else:
            nodes.append(("text", tok))
        i += 1
    return nodes, i


def render_module(module_type, fields, ctx, widgets):
    src = (BUILD / "modules" / (module_type + ".module") / "module.html").read_text()
    nodes, _ = parse(TOKENS.split(src))
    return render_nodes(nodes, dict(ctx, module=fields), widgets)


def render_nodes(nodes, ctx, widgets):
    out = []
    for node in nodes:
        kind = node[0]
        if kind == "text":
            out.append(node[1])
        elif kind == "var":
            out.append(eval_var(node[1], ctx))
        elif kind == "if":
            for cond, body in node[1]:
                if cond is None or eval_expr(cond, ctx):
                    out.append(render_nodes(body, ctx, widgets))
                    break
        elif kind == "for":
            _, var, iterable, body = node
            items = lookup(ctx, iterable) or []
            for idx, item in enumerate(items):
                sub = dict(ctx, **{var: item,
                                   "loop": {"first": idx == 0, "last": idx == len(items) - 1}})
                out.append(render_nodes(body, sub, widgets))
        elif kind == "dnd":
            for block in ctx.get("__blocks__", []):
                out.append(render_module(block["type"], block["fields"], ctx, widgets))
        elif kind == "module":
            name = node[1]
            out.append(render_module(name.replace("_", "-"), widgets.get(name, {}), ctx, widgets))
    return "".join(out)


def render_page(manifest):
    widgets = manifest.get("widgets") or {}
    if manifest.get("blocks") and manifest.get("form_section") is not None:
        widgets = {manifest.get("form_module", "lp_form"): manifest["form_section"]}
    ctx = {
        "page_meta": {
            "html_title": manifest["html_title"],
            "meta_description": manifest["meta_description"],
        },
        "__blocks__": manifest.get("blocks", []),
    }
    template = (BUILD / manifest["template_file"]).read_text()
    template = re.sub(r"<!--.*?-->", "", template, count=1, flags=re.S)  # template annotation
    template = re.sub(r"\{#.*?#\}", "", template, flags=re.S)  # HubL comments
    nodes, _ = parse(TOKENS.split(template))
    html = render_nodes(nodes, ctx, widgets)
    return html.replace("asset://", "../assets/")


def main():
    PREVIEW.mkdir(exist_ok=True)
    for path in sorted((ROOT / "manifests").rglob("*.json")):
        manifest = json.loads(path.read_text())
        out = PREVIEW / (path.stem + ".html")
        out.write_text(render_page(manifest))
        orig = ROOT / "source" / manifest["file"]
        stripped = ROOT / "source" / "stripped" / manifest["file"]
        src = stripped if stripped.exists() else orig
        (PREVIEW / ("original-" + path.stem + ".html")).write_text(
            src.read_text().replace("asset://", "../assets/")
        )
        print(f"wrote {out.relative_to(ROOT)} (+ original)")


if __name__ == "__main__":
    sys.exit(main())
