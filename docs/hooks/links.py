"""MkDocs hook: make README links work inside the site.

The README is written for GitHub and PyPI, so it links to files with absolute
GitHub URLs and to its own headings with in-page anchors. On the site those
sections live on separate pages; this rewrites both kinds of link.
"""

from __future__ import annotations

import re

BLOB = "https://github.com/nicoveraz/urg-forecast-core/blob/main/docs/"

# README heading anchor -> site page (and anchor) where that section now lives.
ANCHORS = {
    "#una-base-no-un-producto": "uso.md#una-base-no-un-producto",
    "#referencia-de-comandos": "uso.md#referencia-de-comandos",
    "#modelos": "modelos.md",
    "#cómo-construir-encima": "extender.md",
}


def on_page_markdown(markdown: str, page, config, files) -> str:
    # https://github.com/.../blob/main/docs/modelos.md -> modelos.md
    markdown = re.sub(re.escape(BLOB) + r"([\w\-./]+\.md)", r"\1", markdown)
    for anchor, target in ANCHORS.items():
        if page.file.src_uri.split("#")[0] == target.split("#")[0]:
            continue  # same page: keep the in-page anchor
        markdown = markdown.replace(f"]({anchor})", f"]({target})")
    return markdown
