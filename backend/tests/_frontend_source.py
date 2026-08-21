"""Shared loader for the frontend contract tests.

``index.html`` was split into ``css/styles.css`` + per-tab ``js/*.js`` modules.
The contract tests still express the same invariants; this helper gives them the
concatenated source the browser actually loads (``index.html`` followed by every
``js/*.js`` module in script-tag order) so the assertions keep working unchanged.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repository root
FRONTEND_DIR = ROOT / "frontend"
INDEX = FRONTEND_DIR / "index.html"

_SCRIPT_RE = re.compile(r'<script\s+src="(js/[^"]+)"\s*></script>')


def frontend_source() -> str:
    parts = [INDEX.read_text(encoding="utf-8")]
    index_html = parts[0]
    for match in _SCRIPT_RE.finditer(index_html):
        # Browser cache-busting query parameters are not part of the local path.
        script_path = match.group(1).split("?", 1)[0].split("#", 1)[0]
        parts.append((FRONTEND_DIR / script_path).read_text(encoding="utf-8"))
    return "".join(parts)
