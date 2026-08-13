"""Resolve the pipeline's working root.

The working root is where a project's config/, families/, source/,
manifests/, assets/ and theme-build/ live. Three ways to set it, in
precedence order:

1. LP_ROOT environment variable — explicit.
2. The current directory (or the nearest ancestor) containing
   config/config.json — so `cd customers/acme && python <repo>/scripts/...`
   just works.
3. The repository root itself — the single-project layout.

This is what makes the multi-customer / consultancy layout work: keep this
repo as the toolkit, and run it against any number of self-contained
customer directories (typically gitignored here and versioned as their own
private repos). A customer directory needs its own `families/__init__.py`
so its extractors are importable.
"""
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def working_root() -> pathlib.Path:
    env = os.environ.get("LP_ROOT")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    cur = pathlib.Path.cwd()
    for candidate in (cur, *cur.parents):
        if (candidate / "config" / "config.json").exists():
            return candidate
    return REPO_ROOT


ROOT = working_root()
sys.path.insert(0, str(ROOT))  # customer families/ importable
