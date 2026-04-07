"""
Genera un HTML visual con las guitarras SSS del catálogo TMS Music.
Incluye: nombre, precio, descripcion resumida, imagen, video de YouTube.
Ordenadas de la mas cara a la mas barata.

Uso:
    python generar_html.py
"""

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://tmsmusic.co/collections/guitarras-electricas/products.json"
PRODUCT_URL = "https://tmsmusic.co/products/"

# ── Reuse pickup detection from filtrar_sss ──────────────────────────────────

VALID_CONFIGS = {"SSS", "HSS", "HSH", "HH", "SS", "SSH", "HHH", "HS"}
CONFIG_PATTERN = re.compile(
    r"[Cc]onfigurac[ií][oó]n\s*:?\s*(?:</strong>)?\s*([SHsh]{2,3})\b",
)
DIRECT_PATTERN = re.compile(r"\b(SSS|HSS|HSH|HH|SS|SSH)\b")
SSS_MODEL_PATTERNS = [
    r"stratocaster(?!.*\b(?:hss|hsh|hh)\b)",
    r"strat(?:o)?(?!.*\b(?:hss|hsh|hh)\b)",
    r"\bstrato\b(?!.*\b(?:hss|hsh|hh)\b)",
]


def is_sss(product: dict) -> bool:
    body = product.get("body_html", "") or ""
    title = product.get("title", "").lower()
    # body_html check
    m = CONFIG_PATTERN.search(body)
    if m and m.group(1).upper() == "SSS":
        return True
    m = DIRECT_PATTERN.search(body)
    if m and m.group(1).upper() == "SSS":
        return True
    # Heuristic: Stratocaster models
    for pat in SSS_MODEL_PATTERNS:
        if re.search(pat, title):
            return True
    return False


# ── Fetch products ───────────────────────────────────────────────────────────

def fetch_all_raw() -> list[dict]:
    all_products = []
    page = 1
    while True:
        url = f"{BASE_URL}?limit=250&page={page}"
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                products = data.get("products", [])
        except (urllib.error.HTTPError, urllib.error.URLError):
            products = []
        if not products:
            break
        all_products.extend(products)
        page += 1
        time.sleep(0.3)
    return all_products


# ── Clean HTML description ───────────────────────────────────────────────────

def clean_description(body_html: str, max_chars: int = 300) -> str:
    if not body_html:
        return "Sin descripcion disponible."
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", body_html)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove leading generic phrases
    text = re.sub(r"^(Descripcion|Description)\s*:?\s*", "", text, flags=re.IGNORECASE)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "..."
    return text if text else "Sin descripcion disponible."


# ── YouTube search ───────────────────────────────────────────────────────────

def search_youtube(query: str) -> str | None:
    """Search YouTube via scraping the search results page, return first video ID."""
    encoded = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={encoded}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        # Find video IDs in the page
        matches = re.findall(r'"videoId"\s*:\s*"([a-zA-Z0-9_-]{11})"', page)
        if matches:
            return matches[0]
    except Exception:
        pass
    return None


def get_youtube_embed(product_title: str, vendor: str) -> str:
    """Get YouTube embed URL for a guitar."""
    # Build a search query focused on the guitar model
    # Clean up the title for better search results
    clean_title = re.sub(
        r"(?i)^guitarra\s+electr[io]ca\s+", "", product_title
    ).strip()
    query = f"{clean_title} review demo"
    print(f"  YouTube: buscando '{query[:50]}...'", file=sys.stderr)
    video_id = search_youtube(query)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    # Fallback: try simpler query
    simple = f"{vendor} {clean_title.split()[0] if clean_title else ''} guitar demo"
    video_id = search_youtube(simple)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return ""


# ── HTML Generation ──────────────────────────────────────────────────────────

def generate_html(guitars: list[dict]) -> str:
    cards = []
    for i, g in enumerate(guitars):
        precio = f"${g['price']:,.0f}"
        precio_antes = ""
        if g.get("compare_price"):
            precio_antes = f'<span class="old">${g["compare_price"]:,.0f}</span>'

        yt_btn = ""
        if g.get("youtube_url"):
            yt_btn = f'<a href="{g["youtube_url"]}" target="_blank" class="btn yt">&#9654; Video</a>'

        disp_cls = "av" if g["available"] else "unav"
        disp_txt = "Disponible" if g["available"] else "Agotada"

        # Shorten title: remove "Guitarra Electrica" prefix
        short_title = re.sub(r"(?i)^guitarra\s+electr[io]ca\s+", "", g["title"]).strip()

        card = f'''<div class="c">
  <div class="img"><img src="{g['image']}" alt="" loading="lazy"></div>
  <div class="info">
    <div class="top"><span class="brand">{html.escape(g['vendor'])}</span><span class="{disp_cls}">{disp_txt}</span></div>
    <h2>{html.escape(short_title)}</h2>
    <div class="pr">{precio} {precio_antes}</div>
    <details><summary>Descripcion</summary><p>{html.escape(g['description'])}</p></details>
    <div class="btns">
      <a href="{g['url']}" target="_blank" class="btn tms">Ver en TMS</a>
      {yt_btn}
    </div>
  </div>
</div>'''
        cards.append(card)

    cards_html = "\n".join(cards)

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Guitarras SSS</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,sans-serif;
  background:#111;color:#e0e0e0;
  padding:12px;
  padding-top:env(safe-area-inset-top,12px);
  -webkit-text-size-adjust:100%;
}}
header{{text-align:center;padding:16px 8px 12px;}}
header h1{{font-size:1.4rem;color:#fff;}}
header p{{color:#777;font-size:.75rem;margin-top:4px;}}
.list{{max-width:500px;margin:0 auto;display:flex;flex-direction:column;}}

.c{{
  display:flex;
  background:#1a1a1a;
  border-radius:10px;
  margin-bottom:10px;
  border:1px solid #252525;
  overflow:hidden;
  min-height:0;
}}
.img{{
  flex:0 0 110px;
  background:#fff;
  display:flex;align-items:center;justify-content:center;
  padding:8px;
}}
.img img{{
  width:100%;height:100%;
  max-height:140px;
  object-fit:contain;
}}
.info{{
  flex:1;
  padding:10px 12px;
  display:flex;flex-direction:column;
  justify-content:center;
  min-width:0;
}}
.top{{
  display:flex;justify-content:space-between;align-items:center;
  margin-bottom:3px;
}}
.brand{{
  font-size:.65rem;text-transform:uppercase;letter-spacing:1.5px;
  color:#f0a500;font-weight:700;
}}
.av,.unav{{font-size:.6rem;padding:2px 6px;border-radius:10px;font-weight:500;}}
.av{{background:#1a3a1a;color:#4caf50;}}
.unav{{background:#3a1a1a;color:#f44336;}}
h2{{
  font-size:.85rem;color:#fff;line-height:1.25;
  margin-bottom:4px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}}
.pr{{margin-bottom:6px;}}
.pr{{font-size:1rem;font-weight:700;color:#4caf50;}}
.old{{font-size:.75rem;color:#666;text-decoration:line-through;margin-left:6px;}}
details{{margin-bottom:6px;}}
summary{{
  cursor:pointer;color:#888;font-size:.7rem;
  padding:2px 0;user-select:none;
}}
details p{{
  color:#999;font-size:.72rem;line-height:1.4;
  margin-top:4px;padding:6px 8px;
  background:#111;border-radius:6px;
}}
.btns{{display:flex;gap:6px;}}
.btn{{
  flex:1;
  display:flex;align-items:center;justify-content:center;
  padding:7px 0;
  text-decoration:none;
  border-radius:6px;
  font-weight:600;font-size:.75rem;
  text-align:center;
  transition:opacity .15s;
}}
.btn:active{{opacity:.7;}}
.tms{{background:#f0a500;color:#000;}}
.yt{{background:#cc0000;color:#fff;}}

@media(min-width:700px){{
  .list{{
    max-width:1100px;
    flex-direction:row;flex-wrap:wrap;gap:10px;
  }}
  .c{{
    width:calc(50% - 5px);
    margin-bottom:0;
  }}
  .img{{flex:0 0 120px;}}
  .img img{{max-height:150px;}}
  h2{{font-size:.88rem;}}
  .pr{{font-size:1rem;}}
}}
@media(min-width:1200px){{
  .list{{max-width:1500px;gap:12px;}}
  .c{{width:calc(33.333% - 8px);}}
  .img{{flex:0 0 130px;}}
}}
</style>
</head>
<body>
<header>
  <h1>Guitarras SSS</h1>
  <p>{len(guitars)} guitarras &middot; TMS Music &middot; mas cara a mas barata</p>
</header>
<div class="list">
{cards_html}
</div>
</body>
</html>'''


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Obteniendo catalogo...", file=sys.stderr)
    raw = fetch_all_raw()
    print(f"Total: {len(raw)} productos", file=sys.stderr)

    # Filter SSS
    sss_raw = [p for p in raw if is_sss(p)]
    print(f"SSS encontradas: {len(sss_raw)}", file=sys.stderr)

    # Build guitar data
    guitars = []
    for p in sss_raw:
        variants = p.get("variants", [])
        prices = [float(v["price"]) for v in variants if v.get("price")]
        compare_prices = [
            float(v["compare_at_price"])
            for v in variants
            if v.get("compare_at_price")
        ]
        images = p.get("images", [])

        guitars.append({
            "title": p.get("title", "").strip(),
            "vendor": p.get("vendor", "").strip(),
            "price": min(prices) if prices else 0,
            "compare_price": min(compare_prices) if compare_prices else None,
            "available": any(v.get("available", False) for v in variants),
            "url": PRODUCT_URL + p.get("handle", ""),
            "image": images[0].get("src", "") if images else "",
            "description": clean_description(p.get("body_html", "")),
            "youtube_url": "",
        })

    # Sort most expensive first
    guitars.sort(key=lambda g: g["price"], reverse=True)

    # Search YouTube videos
    print("Buscando videos en YouTube...", file=sys.stderr)
    for g in guitars:
        g["youtube_url"] = get_youtube_embed(g["title"], g["vendor"])
        time.sleep(1)  # rate limit

    # Generate HTML
    page = generate_html(guitars)
    out_file = "guitarras_sss.html"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"\nGenerado: {out_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
