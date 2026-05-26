#!/usr/bin/env python3
"""
Seed the Great Gatsby book into the DB from gatsby-teaching-edition.html.
Run once on the server after the 002_books.sql migration.

Usage:
    python server/scripts/seed_gatsby.py /path/to/gatsby-teaching-edition.html
    python server/scripts/seed_gatsby.py  # auto-detects if run from repo root
"""
import sys
import os
from pathlib import Path

# Load env from /etc/belowiceberg/admin.env on server
env_file = Path("/etc/belowiceberg/admin.env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

if not os.environ.get("BELOWICEBERG_DATA_DIR"):
    print("ERROR: BELOWICEBERG_DATA_DIR not set")
    print("  Set it with: export BELOWICEBERG_DATA_DIR=/path/to/data")
    sys.exit(1)

# Add server/ to path so we can import app.*
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from bs4 import BeautifulSoup
from app.db import migrate, get_conn, reset_conn
from app import books as bk

# Locate the HTML file
if len(sys.argv) > 1:
    GATSBY_HTML = Path(sys.argv[1])
else:
    # Auto-detect: two dirs up from server/scripts/
    GATSBY_HTML = server_dir.parent / "gatsby-teaching-edition.html"

if not GATSBY_HTML.exists():
    print(f"ERROR: file not found: {GATSBY_HTML}")
    print("  Usage: python seed_gatsby.py /path/to/gatsby-teaching-edition.html")
    sys.exit(1)

CHAPTER_TITLES_ZH = {
    1: "第一章 · 尼克的世界",
    2: "第二章 · 灰烬谷",
    3: "第三章 · 盖茨比的派对",
    4: "第四章 · 过去的秘密",
    5: "第五章 · 重逢",
    6: "第六章 · 真相",
    7: "第七章 · 决裂",
    8: "第八章 · 死亡",
    9: "第九章 · 结局",
}

COVER_CSS = (
    "background:linear-gradient(135deg,#1a1a2e 0%,#16213e 40%,#0f3460 70%,#533483 100%);"
    "position:relative;"
)

reset_conn()
migrate()
conn = get_conn()

# Check if already seeded
if conn.execute("SELECT 1 FROM books WHERE slug='great-gatsby'").fetchone():
    print("Gatsby already seeded. Exiting.")
    sys.exit(0)

print(f"Parsing {GATSBY_HTML} ...")
soup = BeautifulSoup(GATSBY_HTML.read_text(encoding="utf-8"), "lxml")

# Chapter 1's chapter-content div only wraps the first para-section due to HTML
# structure quirks; all others are siblings. Strategy: collect all para-sections
# in document order, then group by chapter using data-chapter div positions.
all_para_sections = soup.find_all("section", class_="para-section")

# Build a map: para-section → chapter_num using source position.
# We assign each para-section to the most recently seen data-chapter div.
ch_sec_map: dict[int, list] = {i: [] for i in range(1, 10)}
current_ch = None
for tag in soup.find_all(["div", "section"]):
    ch_attr = tag.get("data-chapter")
    if ch_attr and tag.name == "div":
        current_ch = int(ch_attr)
    elif tag.name == "section" and "para-section" in (tag.get("class") or []):
        if current_ch is not None:
            ch_sec_map[current_ch].append(tag)

book_id = bk.create_book(
    slug="great-gatsby",
    title_en="The Great Gatsby",
    title_zh="了不起的盖茨比",
    author="F. Scott Fitzgerald",
    cover_css=COVER_CSS,
)
print(f"Created book id={book_id}")

total_sections = 0
total_paragraphs = 0

for ch_num in range(1, 10):
    sections_html = ch_sec_map.get(ch_num, [])
    if not sections_html:
        print(f"  WARNING: chapter {ch_num} not found in HTML")
        continue

    title_zh = CHAPTER_TITLES_ZH.get(ch_num, f"第{ch_num}章")

    # Build full text from all original paragraphs
    all_para_texts: list[str] = []
    for sec in sections_html:
        orig = sec.find("div", class_="original")
        if orig:
            for p in orig.find_all("p"):
                t = p.get_text(" ", strip=True)
                if t:
                    all_para_texts.append(t)

    text_full = "\n\n".join(all_para_texts)
    ch_id = bk.add_chapter(book_id, ch_num, title_zh, text_full)
    print(f"  Chapter {ch_num} ({title_zh}): {len(sections_html)} sections")

    for sec_num, sec_el in enumerate(sections_html, 1):
        heading_el = sec_el.find("span", class_="sec-label")
        sec_title = heading_el.get_text(strip=True) if heading_el else None

        sec_id = bk.add_section(ch_id, sec_num, sec_title)
        total_sections += 1

        orig = sec_el.find("div", class_="original")
        if not orig:
            continue

        para_num = 0
        for p in orig.find_all("p"):
            t = p.get_text(" ", strip=True)
            if t and len(t) > 5:
                para_num += 1
                bk.add_paragraph(sec_id, para_num, t)
                total_paragraphs += 1

print(f"\nDone.")
print(f"  book_id={book_id}")
print(f"  chapters=9, sections={total_sections}, paragraphs={total_paragraphs}")
