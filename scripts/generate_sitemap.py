#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Genera sitemap per AniMMUnity:
- sitemap-static.xml         (pagine statiche)
- sitemap-anime-*.xml        (dettagli Anime da data/anime.csv)
- sitemap-manga-*.xml        (dettagli Manga da data/manga_text_part*.csv)
- sitemap.xml                (indice)

Esegue dedup, pulizia slug e imposta lastmod.
"""

import csv
import os
import re
import html
from pathlib import Path
from urllib.parse import urlparse, quote
from datetime import datetime, timezone

# ===================== CONFIG =====================
BASE = os.environ.get("SITE_BASE", "https://animmunity.github.io")

# Dati
ANIME_CSV = Path("data/anime.csv")
MANGA_PARTS = [Path("data/manga_text_part1.csv"), Path("data/manga_text_part2.csv")]

# Output
OUT_INDEX          = "sitemap.xml"         # indice
OUT_STATIC         = "sitemap-static.xml"
OUT_ANIME_PATTERN  = "sitemap-anime-{i}.xml"
OUT_MANGA_PATTERN  = "sitemap-manga-{i}.xml"
MAX_URLS_PER_FILE  = 50_000

# Pagine statiche (aggiungi/rimuovi a piacere)
STATIC_PAGES = [
    "/",  # home
    "/anime-list.html",
    "/manga-list.html",
    "/top-anime.html",
    "/top-manga.html",
    "/anime-themes.html",
    "/character-list.html",
]

# ==================================================

ROOT = Path(__file__).resolve().parent
# se lo script è in /scripts, risali finché trovi /data/anime.csv
for p in [ROOT, *ROOT.parents]:
    if (p / ANIME_CSV).exists():
        ROOT = p
        break

def read_csv_rows(csv_path: Path):
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def mal_slug_from_url(mal_url: str) -> str:
    try:
        u = urlparse(mal_url or "")
        parts = [s for s in (u.path or "").split("/") if s]
        return html.unescape(parts[-1] if parts else "")
    except Exception:
        return ""

# Rimuove invisibili/controllo che mandano in tilt (U+200E, ecc.)
CTL_RE = re.compile(r"[\u200E\u200F\u202A-\u202E]")

def is_bad_slug(s: str) -> bool:
    if not s: return True
    s = s.strip()
    if not s or s == "-": return True
    s = CTL_RE.sub("", s)
    if not s: return True
    # solo simboli (no lettere/numeri)?
    if re.fullmatch(r"[^\w]+", s, flags=re.UNICODE):
        return True
    return False

def enc(v: str) -> str:
    # encode sicura per slug
    return quote(v, safe="~._-")

def to_iso(date_str: str) -> str | None:
    """Restituisce YYYY-MM-DD se riconoscibile, altrimenti None."""
    if not date_str: return None
    s = str(date_str).strip()
    # formati brevi
    if re.fullmatch(r"\d{4}", s):           # YYYY
        return f"{s}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", s):     # YYYY-MM
        return f"{s}-01"
    # ISO-like
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m: return m.group(1)
    return None

def max_date(a: str | None, b: str | None) -> str | None:
    if not a: return b
    if not b: return a
    return a if a >= b else b  # valido per YYYY-MM-DD

# ====== Costruttori URL CANONICI ======
def anime_loc_from_slug(slug: str) -> str:
    return f"{BASE}/anime.html?slug={enc(slug)}"

def manga_loc_from_slug(slug: str) -> str:
    return f"{BASE}/manga.html?slug={enc(slug)}"

# (Se in futuro passi a /anime/<slug>, cambia queste due funzioni sopra)

# ====== Scrittura file ======
def write_urlset(path: Path, entries: list[dict]):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(u['loc'])}</loc>")
        if u.get("lastmod"):
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        # facoltativi:
        if u.get("changefreq"):
            lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        if u.get("priority") is not None:
            lines.append(f"    <priority>{u['priority']:.1f}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>\n")
    path.write_text("\n".join(lines), encoding="utf-8")

def write_index(path: Path, locs: list[str]):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc in locs:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{html.escape(loc)}</loc>")
        lines.append(f"    <lastmod>{now}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>\n")
    path.write_text("\n".join(lines), encoding="utf-8")

# ====== Builder gruppi ======
def build_static_group() -> list[dict]:
    out = []
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for p in STATIC_PAGES:
        loc = BASE + (p if p.startswith("/") else ("/" + p))
        # priorità: home più alta
        pri = 1.0 if p == "/" else 0.6
        out.append({"loc": loc, "lastmod": today, "changefreq": "daily", "priority": pri})
    return out

def build_anime_group(rows: list[dict]) -> list[dict]:
    seen = {}
    for r in rows:
        slug = mal_slug_from_url(r.get("url") or "")
        if is_bad_slug(slug): continue
        loc = anime_loc_from_slug(slug)
        # lastmod: updated_at > real_end_date > end_date > start_date > created_at
        lastmod = None
        for k in ("updated_at", "real_end_date", "end_date", "start_date", "created_at"):
            lastmod = max_date(lastmod, to_iso(r.get(k) or ""))
        d = seen.get(loc) or {"loc": loc, "lastmod": None}
        d["lastmod"] = max_date(d["lastmod"], lastmod)
        seen[loc] = d
    # ordinamento per loc per stabilità
    return [seen[k] for k in sorted(seen.keys())]

def build_manga_group(parts: list[list[dict]]) -> list[dict]:
    # Merge part1/part2 su BASE slug (da url) → lastmod più recente
    seen = {}
    for rows in parts:
        for r in rows:
            slug = mal_slug_from_url(r.get("url") or "")
            if is_bad_slug(slug): continue
            loc = manga_loc_from_slug(slug)
            # lastmod: updated_at > real_end_date > end_date > start_date > created_at_before
            lastmod = None
            for k in ("updated_at", "real_end_date", "end_date", "start_date", "created_at_before", "created_at"):
                lastmod = max_date(lastmod, to_iso(r.get(k) or ""))
            d = seen.get(loc) or {"loc": loc, "lastmod": None}
            d["lastmod"] = max_date(d["lastmod"], lastmod)
            seen[loc] = d
    return [seen[k] for k in sorted(seen.keys())]

def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

def main():
    # --- carica dati
    anime_csv = (ROOT / ANIME_CSV)
    if not anime_csv.exists():
        raise SystemExit(f"CSV non trovato: {anime_csv}")
    anime_rows = read_csv_rows(anime_csv)

    manga_rows_parts = []
    for p in MANGA_PARTS:
        fp = (ROOT / p)
        if fp.exists():
            manga_rows_parts.append(read_csv_rows(fp))

    # --- costruisci gruppi
    static_entries = build_static_group()
    anime_entries  = build_anime_group(anime_rows)
    manga_entries  = build_manga_group(manga_rows_parts) if manga_rows_parts else []

    out_files = []

    # STATIC
    static_path = ROOT / OUT_STATIC
    write_urlset(static_path, static_entries)
    out_files.append(f"{BASE}/{OUT_STATIC}")

    # ANIME (split se necessario)
    if len(anime_entries) <= MAX_URLS_PER_FILE:
        fname = OUT_ANIME_PATTERN.format(i=1)
        write_urlset(ROOT / fname, anime_entries)
        out_files.append(f"{BASE}/{fname}")
    else:
        idx = 1
        for ch in chunk(anime_entries, MAX_URLS_PER_FILE):
            fname = OUT_ANIME_PATTERN.format(i=idx); idx += 1
            write_urlset(ROOT / fname, ch)
            out_files.append(f"{BASE}/{fname}")

    # MANGA (split se necessario)
    if manga_entries:
        if len(manga_entries) <= MAX_URLS_PER_FILE:
            fname = OUT_MANGA_PATTERN.format(i=1)
            write_urlset(ROOT / fname, manga_entries)
            out_files.append(f"{BASE}/{fname}")
        else:
            idx = 1
            for ch in chunk(manga_entries, MAX_URLS_PER_FILE):
                fname = OUT_MANGA_PATTERN.format(i=idx); idx += 1
                write_urlset(ROOT / fname, ch)
                out_files.append(f"{BASE}/{fname}")

    # INDICE
    write_index(ROOT / OUT_INDEX, out_files)

    # Log
    print(f"✔ statiche: {len(static_entries)}")
    print(f"✔ anime   : {len(anime_entries)}")
    print(f"✔ manga   : {len(manga_entries)}")
    print(f"✔ scritto indice: {OUT_INDEX}")
    for loc in out_files:
        print(f"  - {loc}")

if __name__ == "__main__":
    main()
