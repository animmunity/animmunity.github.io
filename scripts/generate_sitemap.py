#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sitemaps AniMMUnity (in /sitemaps/):
- /sitemaps/static.xml
- /sitemaps/anime-*.xml        (da data/anime.csv)
- /sitemaps/manga-*.xml        (merge data/manga_text_part*.csv + fallback lastmod da manga_core.csv)
- /sitemaps/characters-*.xml   (da data/anime_characters_part[1..6].csv)
- /sitemaps/mini.xml           (home + pagine base, per smoke-test)
- /sitemaps/index.xml          (indice principale)

Split: 5_000 URL/file. Dedup su URL finale. <lastmod> in YYYY-MM-DD dove disponibile.
"""

import csv, os, re, html
from pathlib import Path
from urllib.parse import urlparse, quote
from datetime import datetime, timezone

# ===================== CONFIG =====================
BASE = os.environ.get("SITE_BASE", "https://wiki.animmunity.com")

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

OUT_DIR    = Path("sitemaps")
OUT_INDEX  = OUT_DIR / "index.xml"
OUT_STATIC = OUT_DIR / "static.xml"
OUT_ANIME  = OUT_DIR / "anime-{i}.xml"
OUT_MANGA  = OUT_DIR / "manga-{i}.xml"
OUT_CHAR   = OUT_DIR / "characters-{i}.xml"
OUT_MINI   = OUT_DIR / "mini.xml"

MAX_URLS_PER_FILE = 5_000

STATIC_PAGES = [
    "/",
    "/index.html",
    "/anime-list.html",
    "/manga-list.html",
    "/top-anime.html",
    "/top-manga.html",
    "/anime-themes.html",
    "/character-list.html",
]

# ===== Root del repo =====
ROOT = Path(__file__).resolve().parent
for p in [ROOT, *ROOT.parents]:
    if (p / ANIME_CSV).exists():
        ROOT = p
        break

# ===== Helpers =====
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
    if re.fullmatch(r"[^\w]+", s, flags=re.UNICODE):  # solo simboli/punteggiatura
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

# Canoniche
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
    if not char_id and not name: return None
    s = slugify(name or "") if name else ""
    if char_id:
        return f"{BASE}/character.html?id={enc(str(char_id))}{('&slug=' + enc(s)) if s else ''}"
    return f"{BASE}/character.html?slug={enc(s)}" if s else None

def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

# ===== Writer =====
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

def write_urlset(path_xml: Path, entries: list[dict]):
    path_xml.parent.mkdir(parents=True, exist_ok=True)
    path_xml.write_text(_build_urlset_text(entries), encoding="utf-8")

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
    path_xml.parent.mkdir(parents=True, exist_ok=True)
    path_xml.write_text("\n".join(out), encoding="utf-8")

# ===== Builders =====
def build_static_group() -> list[dict]:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    uniq = {}
    for p in STATIC_PAGES:
        loc = BASE + (p if p.startswith("/") else ("/" + p))
        pri = 1.0 if p == "/" else 0.6
        uniq[loc] = {"loc": loc, "lastmod": today, "changefreq": "daily", "priority": pri}
    return list(uniq.values())

def build_anime_group(rows: list[dict]) -> list[dict]:
    seen = {}
    for r in rows:
        slug = mal_slug_from_url(r.get("url") or "")
        aid  = str(r.get("anime_id") or "").strip() or None
        loc  = anime_loc(slug, aid)
        if not loc: continue
        lastmod = None
        for k in ("updated_at","real_end_date","end_date","start_date","created_at"):
            lastmod = max_date(lastmod, to_iso(r.get(k) or ""))
        d = seen.get(loc) or {"loc": loc, "lastmod": None}
        d["lastmod"] = max_date(d["lastmod"], lastmod)
        seen[loc] = d
    return [seen[k] for k in sorted(seen.keys())]

def build_manga_group(parts: list[list[dict]], core_rows: list[dict]) -> list[dict]:
    core_by_id = {}
    for r in core_rows:
        mid = str(r.get("manga_id") or "").strip()
        if mid: core_by_id[mid] = r
    seen = {}
    for rows in parts:
        for r in rows:
            slug = mal_slug_from_url(r.get("url") or "")
            mid  = str(r.get("manga_id") or "").strip() or None
            loc  = manga_loc(slug, mid)
            if not loc: continue
            lastmod = None
            for k in ("updated_at","real_end_date","end_date","start_date","created_at_before","created_at"):
                lastmod = max_date(lastmod, to_iso(r.get(k) or ""))
            if not lastmod and mid and mid in core_by_id:
                cr = core_by_id[mid]
                for k in ("updated_at","real_end_date","end_date","start_date","created_at"):
                    lastmod = max_date(lastmod, to_iso(cr.get(k) or ""))
            d = seen.get(loc) or {"loc": loc, "lastmod": None}
            d["lastmod"] = max_date(d["lastmod"], lastmod)
            seen[loc] = d
    return [seen[k] for k in sorted(seen.keys())]

def build_char_group(parts: list[list[dict]]) -> list[dict]:
    seen = {}
    for rows in parts:
        for r in rows:
            cid  = str(r.get("mal_id") or "").strip() or None
            name = (r.get("name") or "").strip() or None
            loc  = char_loc(cid, name)
            if not loc: continue
            seen[loc] = {"loc": loc, "lastmod": None}
    return [seen[k] for k in sorted(seen.keys())]

# ===== MAIN =====
def main():
    # Pulisci la cartella /sitemaps/
    if OUT_DIR.exists():
        for p in OUT_DIR.glob("*.xml"):
            try: p.unlink()
            except Exception: pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Carica dati
    anime_rows = read_if_exists(ANIME_CSV)
    manga_core_rows = read_if_exists(MANGA_CORE)
    manga_parts_rows = [read_if_exists(p) for p in MANGA_PARTS if (ROOT / p).exists()]
    char_parts_rows  = [read_if_exists(p) for p in CHAR_PARTS  if (ROOT / p).exists()]

    # Costruisci
    static_entries = build_static_group()
    anime_entries  = build_anime_group(anime_rows)
    manga_entries  = build_manga_group(manga_parts_rows, manga_core_rows) if manga_parts_rows else []
    char_entries   = build_char_group(char_parts_rows) if char_parts_rows else []

    out_locs = []

    # STATIC + MINI
    write_urlset(OUT_STATIC, static_entries)
    out_locs.append(f"{BASE}/sitemaps/{OUT_STATIC.name}")

    mini = [u for u in static_entries if u["loc"] in {
        f"{BASE}/", f"{BASE}/anime-list.html", f"{BASE}/manga-list.html",
        f"{BASE}/top-anime.html", f"{BASE}/top-manga.html"
    }]
    write_urlset(OUT_MINI, mini)
    out_locs.append(f"{BASE}/sitemaps/{OUT_MINI.name}")

    # ANIME
    if not anime_entries:
        f = OUT_ANIME.with_name(OUT_ANIME.name.format(i=1))
        write_urlset(f, [])
        out_locs.append(f"{BASE}/sitemaps/{f.name}")
    else:
        i = 1
        for ch in chunk(anime_entries, MAX_URLS_PER_FILE):
            f = OUT_ANIME.with_name(OUT_ANIME.name.format(i=i)); i += 1
            write_urlset(f, ch)
            out_locs.append(f"{BASE}/sitemaps/{f.name}")

    # MANGA
    if not manga_entries:
        f = OUT_MANGA.with_name(OUT_MANGA.name.format(i=1))
        write_urlset(f, [])
        out_locs.append(f"{BASE}/sitemaps/{f.name}")
    else:
        i = 1
        for ch in chunk(manga_entries, MAX_URLS_PER_FILE):
            f = OUT_MANGA.with_name(OUT_MANGA.name.format(i=i)); i += 1
            write_urlset(f, ch)
            out_locs.append(f"{BASE}/sitemaps/{f.name}")

    # CHARACTERS
    if not char_entries:
        f = OUT_CHAR.with_name(OUT_CHAR.name.format(i=1))
        write_urlset(f, [])
        out_locs.append(f"{BASE}/sitemaps/{f.name}")
    else:
        i = 1
        for ch in chunk(char_entries, MAX_URLS_PER_FILE):
            f = OUT_CHAR.with_name(OUT_CHAR.name.format(i=i)); i += 1
            write_urlset(f, ch)
            out_locs.append(f"{BASE}/sitemaps/{f.name}")

    # INDICE
    write_index(OUT_INDEX, out_locs)

    # Log
    print(f"✔ statiche     : {len(static_entries)}")
    print(f"✔ mini         : {len(mini)}")
    print(f"✔ anime        : {len(anime_entries)}")
    print(f"✔ manga        : {len(manga_entries)}")
    print(f"✔ characters   : {len(char_entries)}")
    print(f"✔ index scritto: {OUT_INDEX}")
    for loc in out_locs:
        print(" -", loc)

if __name__ == "__main__":
    main()
