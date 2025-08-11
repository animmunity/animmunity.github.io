#!/usr/bin/env python3
import csv
import sys
import os
import html
from pathlib import Path
from urllib.parse import urlparse, quote
from datetime import datetime

# ===================== Config =====================
BASE = os.environ.get("SITE_BASE", "https://animmunity.github.io")
CSV_REL = Path("data/anime.csv")     # rispetto alla root del repo
OUT_MAIN = "sitemap.xml"             # nome file principale in root
MAX_URLS_PER_FILE = 50000            # limite sitemap
# ==================================================

def repo_root() -> Path:
    # Se lo script è in /scripts, la root è il parent
    here = Path(__file__).resolve().parent
    # prova a risalire finché trovi data/anime.csv
    for p in [here, *here.parents]:
        if (p / "data" / "anime.csv").exists():
            return p
    # fallback: parent di scripts
    return here.parent

def get_mal_slug(mal_url: str) -> str:
    try:
        p = urlparse(mal_url or "")
        parts = [s for s in (p.path or "").split("/") if s]
        return parts[-1] if parts else ""
    except Exception:
        return ""

def iso_date(s: str):
    """Ritorna YYYY-MM-DD se riconoscibile, altrimenti None."""
    if not s:
        return None
    s = s.strip()
    if len(s) == 4 and s.isdigit():
        return f"{s}-01-01"
    if len(s) == 7 and s[4] == "-":
        return f"{s}-01"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None

def max_date(a, b):
    """Ritorna la data massima (stringhe YYYY-MM-DD o None)."""
    if not a: return b
    if not b: return a
    return a if a >= b else b  # confronto lessicografico valido per YYYY-MM-DD

def build_loc_from_slug(slug: str) -> str:
    # mantieni caratteri “puliti”, escapa il resto
    safe_slug = quote(slug, safe="~._-")
    return f"{BASE}/anime/{safe_slug}"

def read_csv_rows(csv_path: Path):
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def build_url_entries(rows):
    urls = {}

    # Home (niente /index.html duplicato)
    urls[f"{BASE}/"] = {"loc": f"{BASE}/", "lastmod": None}

    for row in rows:
        mal_url = (row.get("url") or "").strip()
        slug = get_mal_slug(mal_url)
        if not slug:
            continue

        loc = build_loc_from_slug(slug)

        # lastmod: preferisci updated_at, poi real_end_date, poi start_date
        lastmod_raw = row.get("updated_at") or row.get("real_end_date") or row.get("start_date") or ""
        lastmod = iso_date(lastmod_raw)

        if loc in urls:
            # tieni la data più recente
            urls[loc]["lastmod"] = max_date(urls[loc]["lastmod"], lastmod)
        else:
            urls[loc] = {"loc": loc, "lastmod": lastmod}

    # Ordina: prima home, poi per loc
    ordered = [urls[f"{BASE}/"]] + [v for k, v in sorted(urls.items()) if k != f"{BASE}/"]
    return ordered

def write_sitemap_file(path: Path, url_entries):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in url_entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(u['loc'])}</loc>")
        if u.get("lastmod"):
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def write_sitemap_index(path: Path, file_names):
    # file_names relativi alla root, es: ["sitemap-1.xml", "sitemap-2.xml"]
    now = datetime.utcnow().strftime("%Y-%m-%d")
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for name in file_names:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{html.escape(BASE + '/' + name)}</loc>")
        lines.append(f"    <lastmod>{now}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    root = repo_root()
    csv_path = (root / CSV_REL).resolve()
    if not csv_path.exists():
        print(f"Errore: {csv_path} non trovato", file=sys.stderr)
        sys.exit(1)

    rows = read_csv_rows(csv_path)
    entries = build_url_entries(rows)

    # Scrivi una singola sitemap oppure splitta se > MAX_URLS_PER_FILE
    if len(entries) <= MAX_URLS_PER_FILE:
        out_path = (root / OUT_MAIN).resolve()
        write_sitemap_file(out_path, entries)
        print(f"✔ Generata {out_path} con {len(entries)} URL")
    else:
        # Split
        chunks = [
            entries[i:i + MAX_URLS_PER_FILE]
            for i in range(0, len(entries), MAX_URLS_PER_FILE)
        ]
        names = []
        for idx, chunk in enumerate(chunks, start=1):
            name = f"sitemap-{idx}.xml"
            write_sitemap_file(root / name, chunk)
            names.append(name)
            print(f"✔ Generata {name} con {len(chunk)} URL")

        # Sitemap index
        index_name = "sitemap_index.xml"
        write_sitemap_index(root / index_name, names)
        print(f"✔ Generato {index_name} che indicizza {len(names)} file")

if __name__ == "__main__":
    main()
