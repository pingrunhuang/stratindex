"""Fetch recent cryptocurrency-trading papers from the public arXiv API."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
DEFAULT_QUERY = "all:cryptocurrency AND all:trading AND all:strategy"


@dataclass
class RawPaper:
    source_url: str
    source_name: str
    title: str
    abstract: str
    raw_excerpt: str


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def fetch_arxiv(max_results: int = 3, search_query: str = DEFAULT_QUERY) -> list[RawPaper]:
    """Return up to max_results papers from arXiv Atom API (no API key)."""
    params = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": max(1, min(int(max_results), 10)),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"{ARXIV_API}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "StratIndexIngest/0.1 (local; +https://x.com/FRKHuang)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()

    root = ET.fromstring(body)
    papers: list[RawPaper] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = _clean(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
        summary = _clean(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
        # Prefer abs HTML link
        abs_url = ""
        for link in entry.findall("atom:link", ATOM_NS):
            if link.attrib.get("rel") == "alternate" and link.attrib.get("type") == "text/html":
                abs_url = link.attrib.get("href", "")
                break
        if not abs_url:
            id_text = entry.findtext("atom:id", default="", namespaces=ATOM_NS)
            abs_url = id_text.replace("http://arxiv.org/abs/", "https://arxiv.org/abs/").replace(
                "https://arxiv.org/abs/", "https://arxiv.org/abs/"
            )
            if id_text and "arxiv.org" not in abs_url:
                abs_url = id_text
        if not title or not abs_url:
            continue
        excerpt = f"{title}\n\n{summary}"
        papers.append(
            RawPaper(
                source_url=abs_url,
                source_name="arXiv",
                title=title,
                abstract=summary,
                raw_excerpt=excerpt[:8000],
            )
        )
    return papers
