#!/usr/bin/env python3
import csv, sys, os, html
from urllib.parse import urlparse, quote

BASE = "https://animmunity.github.io"
CSV_PATH = "data/anime.csv"
OUT_PATH = "sitemap.xml"

def get_mal_slug(mal_url: str) -> str:
    try:
        p = urlparse(mal_url)
        parts = [s for s in p.path.split("/") if s]
        return parts[-1] if parts else ""
    except:
        return ""

def iso_date(s: str) -> str | None:
    if not s: return None
    s = s.strip()
    # accetta formati YYYY, YYYY-MM, YYYY-MM-DD
    if len(s) == 4 and s.isdigit(): return f"{s}-01-01"
    if len(s) == 7 and s[4] == "-": return f"{s}-01"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-": return s[:10]
    return None

def main():
    if not os.path.exists(CSV_PATH):
        print(f"Errore: {CSV_PATH} non trovato", file=sys.stderr)
        sys.exit(1)

    urls = []
    # homepage e index.html
    urls.append({"loc": f"{BASE}/"})
    urls.append({"loc": f"{BASE}/index.html"})

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        seen = set()
        for row in reader:
            mal_url = (row.get("url") or "").strip()
            slug = get_mal_slug(mal_url)
            if not slug: 
                continue
            loc = f"{BASE}/anime.html?slug={quote(slug)}"
            if loc in seen:
                continue
            seen.add(loc)

            # lastmod (se disponibile): preferisci updated_at, poi real_end_date, poi start_date
            lastmod = row.get("updated_at") or row.get("real_end_date") or row.get("start_date") or ""
            lastmod = iso_date(lastmod)
            urls.append({"loc": loc, "lastmod": lastmod})

    # genera XML
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(u['loc'])}</loc>")
        if u.get("lastmod"):
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")

    print(f"✔ Generata {OUT_PATH} con {len(urls)} URL")

if __name__ == "__main__":
    main()
