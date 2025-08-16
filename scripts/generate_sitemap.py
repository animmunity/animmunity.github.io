#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sitemaps AniMMUnity:
- sitemap-static.xml[.gz]
- sitemap-anime-*.xml[.gz]       (da data/anime.csv)
- sitemap-manga-*.xml[.gz]       (merge data/manga_text_part*.csv + fallback lastmod da manga_core.csv)
- sitemap-characters-*.xml[.gz]  (da data/anime_characters_part[1..6].csv)
- sitemap-mini.xml               (home + pagine base, piccola per test)
- sitemap.xml                    (indice -> punta alle .gz)

Note:
- Split a 5_000 URL/file per facilitare il fetch.
- Dedup per URL canonico finale.
- lastmod in YYYY-MM-DD dove disponibile.
"""

import csv, os, re, html, gzip
from pathlib import Path
from urllib.parse import urlparse, quote
from datetime import datetime, timezone

# ===================== CONFIG =====================
BASE = os.environ.get("SITE_BASE", "https://animmunity.github.io")

ANIME_CSV   = Path("data/anime.csv")
MANGA_CORE  = Path("data/manga_core.csv")  # opzionale
MANGA_PARTS = [Path("data/manga_text_part1.csv"), Path("data/manga_text_part2.csv")]
CHAR_PARTS  = [
    Path("data/anime_characters_part1.csv"),
    Path("data/anime_characters_part2.csv"),
    Path("data/anime_characters_part3.csv"),
    Path("data/anime_characters_part4.csv"),
    Path("data/anime_characters_part5.csv"),
    Path("data/anime_characters_part6.csv"),
]

OUT_INDEX         = "sitemap.xml"
OUT_STATIC        = "sitemap-static.xml"
OUT_ANIME_PATTERN = "sitemap-anime-{i}.xml"
OUT_MANGA_PATTERN = "sitemap-manga-{i}.xml"
OUT_CHAR_PATTERN  = "sitemap-characters-{i}.xml"
OUT_MINI          = "sitemap-mini.xml"

MAX_URLS_PER_FILE = 5_000  # più piccoli = fetch più affidabile

# Solo pagine che ESISTONO nel repo
STATIC_PAGES = [
    "/",  # home
    "/anime-list.html",
    "/manga-list.html",
    "/top-anime.html",
    "/top-manga.html",
    "/anime-themes.html",
    "/character-list.html",
    "/index.html",   # spesso duplicato della home, ma ok
]

# ====== Root repo ======
ROOT = Path(__file__).resolve().parent
for p in [ROOT, *ROOT.parents]:
    if (p / ANIME_CSV).exists():
        ROOT = p
        break

# ========== Helpers ==========
def read_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def read_if_exists(rel: Path):
    fp = (ROOT / rel)
    return read_csv_rows(fp) if fp.exists() else []

def mal_slug_from_url(mal_url: str) -> str:
    try:
        u = urlparse(mal_url or "")
        parts = [s for s in (u.path or "").split("/") if s]
        return html.unescape(parts[-1] if parts else "")
    except Exception:
        return ""

CTL_RE = re.compile(r"[\u200E\u200F\u202A-\u202E]")  # invisibili/RTL

def is_bad_slug(s: str) -> bool:
    if not s: return True
    s = CTL_RE.sub("", s).strip()
    if not s or s == "-": return True
    if re.fullmatch(r"[^\w]+", s, flags=re.UNICODE):  # solo simboli
        return True
    return False

def enc(v: str) -> str:
    return quote(v, safe="~._-")

def to_iso(date_str: str) -> str | None:
    if not date_str: return None
    s = str(date_str).strip()
    if re.fullmatch(r"\d{4}", s):         # YYYY
        return f"{s}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", s):   # YYYY-MM
        return f"{s}-01"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None

def max_date(a: str | None, b: str | None) -> str | None:
    if not a: return b
    if not b: return a
    return a if a >= b else b

# Canoniche (coerenti con il front-end)
def anime_loc(slug: str | None, anime_id: str | None) -> str | None:
    if slug and not is_bad_slug(slug):
        return f"{BASE}/anime.html?slug={enc(slug)}"
    if anime_id:
        return f"{BASE}/anime.html?id={enc(anime_id)}"
    return None

def manga_loc(slug: str | None, manga_id: str | None) -> str | None:
    if slug and not is_bad_slug(slug):
        return f"{BASE}/manga.html?slug={enc(slug)}"
    if manga_id:
        return f"{BASE}/manga.html?id={enc(manga_id)}"
    return None

def slugify(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s

def char_loc(char_id: str | None, name: str | None) -> str | None:
    if not char_id and not name:
        return None
    s = slugify(name or "") if name else ""
    if char_id:
        return f"{BASE}/character.html?id={enc(str(char_id))}{('&slug=' + enc(s)) if s else ''}"
    return f"{BASE}/character.html?slug={enc(s)}" if s else None

# Writer (XML + opzionale .gz)
def _build_urlset_text(entries: list[dict]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in entries:
        out.append("  <url>")
        out.append(f"    <loc>{html.escape(u['loc'])}</loc>")
        if u.get("lastmod"):
            out.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        if u.get("changefreq"):
            out.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        if u.get("priority") is not None:
            out.append(f"    <priority>{u['priority']:.1f}</priority>")
        out.append("  </url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"

def write_urlset(path_xml: Path, entries: list[dict], also_gz: bool = True):
    text = _build_urlset_text(entries)
    path_xml.write_text(text, encoding="utf-8")
    if also_gz:
        with gzip.open(str(path_xml) + ".gz", "wt", encoding="utf-8") as f:
            f.write(text)

def write_index(path_xml: Path, locs: list[str]):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc in locs:
        out.append("  <sitemap>")
        out.append(f"    <loc>{html.escape(loc)}</loc>")
        out.append(f"    <lastmod>{now}</lastmod>")
        out.append("  </sitemap>")
    out.append("</sitemapindex>\n")
    path_xml.write_text("\n".join(out), encoding="utf-8")

def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

# ========== MAIN ==========
def main():
    # Cleanup vecchie sitemap (anche .gz) per evitare residui
    for p in list(ROOT.glob("sitemap*.xml")) + list(ROOT.glob("sitemap*.xml.gz")):
        try: p.unlink()
        except: pass

    anime_rows = read_if_exists(ANIME_CSV)
    manga_core_rows = read_if_exists(MANGA_CORE)
    manga_parts_rows = [read_if_exists(p) for p in MANGA_PARTS if (ROOT / p).exists()]
    char_parts_rows  = [read_if_exists(p) for p in CHAR_PARTS  if (ROOT / p).exists()]

    static_entries = build_static_group()
    anime_entries  = build_anime_group(anime_rows)
    manga_entries  = build_manga_group(manga_parts_rows, manga_core_rows) if manga_parts_rows else []
    char_entries   = build_char_group(char_parts_rows) if char_parts_rows else []

    out_locs_for_index = []

    # STATIC (+ .gz)
    write_urlset(ROOT / OUT_STATIC, static_entries, also_gz=True)
    out_locs_for_index.append(f"{BASE}/{OUT_STATIC}.gz")

    # MINI (home + 4-5 pagine) — non compressa: utile per test rapidi
    mini = [u for u in static_entries if u["loc"] in {
        f"{BASE}/", f"{BASE}/anime-list.html", f"{BASE}/manga-list.html",
        f"{BASE}/top-anime.html", f"{BASE}/top-manga.html"
    }]
    write_urlset(ROOT / OUT_MINI, mini, also_gz=False)
    out_locs_for_index.append(f"{BASE}/{OUT_MINI}")

    # ANIME
    if not anime_entries:
        fname = OUT_ANIME_PATTERN.format(i=1)
        write_urlset(ROOT / fname, [], also_gz=True)
        out_locs_for_index.append(f"{BASE}/{fname}.gz")
    else:
        idx = 1
        for ch in chunk(anime_entries, MAX_URLS_PER_FILE):
            fname = OUT_ANIME_PATTERN.format(i=idx); idx += 1
            write_urlset(ROOT / fname, ch, also_gz=True)
            out_locs_for_index.append(f"{BASE}/{fname}.gz")

    # MANGA
    if not manga_entries:
        fname = OUT_MANGA_PATTERN.format(i=1)
        write_urlset(ROOT / fname, [], also_gz=True)
        out_locs_for_index.append(f"{BASE}/{fname}.gz")
    else:
        idx = 1
        for ch in chunk(manga_entries, MAX_URLS_PER_FILE):
            fname = OUT_MANGA_PATTERN.format(i=idx); idx += 1
            write_urlset(ROOT / fname, ch, also_gz=True)
            out_locs_for_index.append(f"{BASE}/{fname}.gz")

    # CHARACTERS
    if not char_entries:
        fname = OUT_CHAR_PATTERN.format(i=1)
        write_urlset(ROOT / fname, [], also_gz=True)
        out_locs_for_index.append(f"{BASE}/{fname}.gz")
    else:
        idx = 1
        for ch in chunk(char_entries, MAX_URLS_PER_FILE):
            fname = OUT_CHAR_PATTERN.format(i=idx); idx += 1
            write_urlset(ROOT / fname, ch, also_gz=True)
            out_locs_for_index.append(f"{BASE}/{fname}.gz")

    # INDICE -> punta alle versioni .gz (più leggere)
    write_index(ROOT / OUT_INDEX, out_locs_for_index)

    # Log
    print(f"✔ statiche     : {len(static_entries)}")
    print(f"✔ mini         : {len(mini)}")
    print(f"✔ anime        : {len(anime_entries)}")
    print(f"✔ manga        : {len(manga_entries)}")
    print(f"✔ characters   : {len(char_entries)}")
    print(f"✔ indice scritto: {OUT_INDEX}")
    for loc in out_locs_for_index:
        print(" -", loc)

if __name__ == "__main__":
    main()
