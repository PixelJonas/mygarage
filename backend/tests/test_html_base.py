"""``app.utils.html_base``: the SPA shell's <base href> and its CSP script hashes."""

import base64
import hashlib

from app.utils.html_base import inject_base_href, inline_script_hashes

_SCRIPT = "\n      (function () { document.documentElement.classList.add('dark'); })();\n    "
_HTML = (
    '<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n'
    f"    <script>{_SCRIPT}</script>\n"
    '    <script type="module" crossorigin src="./assets/main.js"></script>\n'
    "  </head>\n  <body></body>\n</html>\n"
)


def _sha256_source(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def test_injects_root_base_when_empty():
    out = inject_base_href(_HTML, "")
    assert '<base href="/">' in out
    assert out.index("<base") < out.index("<meta charset")


def test_injects_prefixed_base():
    out = inject_base_href(_HTML, "/mygarage")
    assert '<base href="/mygarage/">' in out


def test_idempotent_single_base():
    once = inject_base_href(_HTML, "/mygarage")
    assert inject_base_href(once, "/mygarage").count("<base ") == 1


def test_matches_the_csp_specification_example():
    # CSP Level 2 §4.2.2: the hash covers the script text verbatim.
    html = "<script>alert('Hello, world.');</script>"
    assert inline_script_hashes(html) == ("sha256-qznLcsROx4GACP2dm0UCKCzCG+HiZ1guq6ZZDob/Tng=",)


def test_hashes_the_shell_inline_script_and_skips_the_module_entry():
    # Surrounding whitespace is part of the hashed text; the src= script is
    # covered by 'self' and gets no hash.
    assert inline_script_hashes(_HTML) == (_sha256_source(_SCRIPT),)


def test_one_hash_per_inline_script_in_document_order():
    html = "<script>first</script><SCRIPT>second</SCRIPT>"
    assert inline_script_hashes(html) == (_sha256_source("first"), _sha256_source("second"))


def test_no_scripts_no_hashes():
    assert inline_script_hashes("<html><head></head><body></body></html>") == ()


def test_crlf_source_hashes_as_the_browser_sees_it():
    # The HTML parser normalises CR LF and CR to LF before the text is hashed.
    assert inline_script_hashes("<script>a\r\nb\rc</script>") == (_sha256_source("a\nb\nc"),)


def test_base_href_injection_leaves_the_hashes_unchanged():
    assert inline_script_hashes(inject_base_href(_HTML, "/mygarage")) == inline_script_hashes(_HTML)
