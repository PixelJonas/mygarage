"""Inject a runtime <base href> into the SPA shell for subpath hosting (#107).

The frontend is built with Vite ``base: './'`` (relative asset + dynamic-import
resolution). A <base href> anchors those relative URLs at every route — WITHOUT
it, a deep-link reload like /vehicles/ABC would fetch entry assets from
/vehicles/assets/... and the SPA would never start. We therefore ALWAYS inject
one: "/" at root (functionally identical to the old absolute output, one added
tag) and "/{prefix}/" when MYGARAGE_ROOT_PATH is set.
"""

from __future__ import annotations

import base64
import hashlib
import re

_HEAD_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_SCRIPT_RE = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.IGNORECASE | re.DOTALL
)
_SRC_ATTR_RE = re.compile(r"\ssrc\s*=", re.IGNORECASE)


def inject_base_href(html: str, root_path: str) -> str:
    """Insert ``<base href="{root_path}/">`` after <head>. Idempotent."""
    if "<base " in html:
        return html
    href = f"{root_path}/" if root_path else "/"
    tag = f'<base href="{href}">'
    return _HEAD_RE.sub(lambda m: m.group(0) + "\n    " + tag, html, count=1)


def inline_script_hashes(html: str) -> tuple[str, ...]:
    """CSP ``sha256-…`` sources for every inline <script> in the shell.

    ``script-src 'self'`` refuses inline scripts, and index.html carries one
    (the theme/accent pre-paint). Hashing the served shell keeps the header
    and the file in step: an edited script changes the hash, not the policy.
    The browser hashes the script text after the HTML parser's newline
    normalisation, so CR LF and CR become LF first. External scripts
    (``src=``) are covered by ``'self'`` and skipped.
    """
    hashes: list[str] = []
    for match in _SCRIPT_RE.finditer(html):
        if _SRC_ATTR_RE.search(match.group("attrs")):
            continue
        body = match.group("body").replace("\r\n", "\n").replace("\r", "\n")
        digest = hashlib.sha256(body.encode("utf-8")).digest()
        hashes.append("sha256-" + base64.b64encode(digest).decode("ascii"))
    return tuple(hashes)
