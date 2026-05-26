"""Parse an EPUB file and insert book/chapter/section/paragraph rows into the DB."""
from __future__ import annotations
import io
import re
import warnings
from typing import BinaryIO

# Suppress ebooklib's verbose warnings about missing/optional fields
warnings.filterwarnings("ignore", category=UserWarning, module="ebooklib")

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from app import books as bk


def _extract_paragraphs(html: str) -> list[str]:
    """Extract non-trivial paragraph texts from HTML."""
    soup = BeautifulSoup(html, "lxml")
    texts = []
    for tag in soup.find_all("p"):
        t = tag.get_text(" ", strip=True)
        if t and len(t) > 10:
            texts.append(t)
    return texts


def parse_epub_to_db(fileobj: BinaryIO) -> int:
    """Parse EPUB from file-like object. Returns book_id."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
        tmp.write(fileobj.read())
        tmp_path = tmp.name
    try:
        book = epub.read_epub(tmp_path)
    finally:
        os.unlink(tmp_path)

    title_en = book.get_metadata("DC", "title")
    title_en = title_en[0][0] if title_en else "Unknown Title"

    creator = book.get_metadata("DC", "creator")
    author = creator[0][0] if creator else "Unknown Author"

    # Derive slug from title
    slug = re.sub(r"[^a-z0-9]+", "-", title_en.lower()).strip("-")[:50]

    # Ensure slug is unique
    base_slug = slug
    i = 1
    while True:
        try:
            book_id = bk.create_book(slug, title_en, title_en, author)
            break
        except bk.BookExistsError:
            slug = f"{base_slug}-{i}"
            i += 1

    # Parse spine items as chapters
    chapter_num = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        body_text = soup.get_text(" ", strip=True)
        if len(body_text) < 50:
            continue  # skip nav/toc pages

        chapter_num += 1
        h = soup.find(["h1", "h2"])
        title_zh = h.get_text(strip=True) if h else f"第{chapter_num}章"

        ch_id = bk.add_chapter(book_id, chapter_num, title_zh, body_text)

        # Split into sections by h2/h3 markers; each section gets its own paragraphs
        sections: list[list[str]] = []
        current: list[str] = []
        for tag in (soup.body.children if soup.body else []):
            if not hasattr(tag, "name"):
                continue
            if tag.name in ("h2", "h3"):
                if current:
                    sections.append(current)
                    current = []
            elif tag.name == "p":
                t = tag.get_text(" ", strip=True)
                if t and len(t) > 10:
                    current.append(t)
        if current:
            sections.append(current)

        if not sections:
            sections = [_extract_paragraphs(html)]

        for sec_num, para_texts in enumerate(sections, 1):
            sec_id = bk.add_section(ch_id, sec_num)
            for para_num, text in enumerate(para_texts, 1):
                bk.add_paragraph(sec_id, para_num, text)

    return book_id
