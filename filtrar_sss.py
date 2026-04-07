"""
Filtra guitarras eléctricas SSS del catálogo de TMS Music.

Estrategia en 3 capas:
  1. Extrae configuración del body_html del JSON de colección (rápido)
  2. Para las desconocidas, scrape la página individual del producto
  3. Fallback: heurística por nombre de modelo

Uso:
    python filtrar_sss.py               # Ejecuta todo y muestra resultados
    python filtrar_sss.py --csv         # Exporta las SSS a guitarras_sss.csv
    python filtrar_sss.py --solo-fase1  # Solo usa body_html (sin scraping individual)
"""

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

BASE_URL = "https://tmsmusic.co/collections/guitarras-electricas/products.json"
PRODUCT_URL = "https://tmsmusic.co/products/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ── Fase 1: Extraer configuración del body_html ──────────────────────────────

VALID_CONFIGS = {"SSS", "HSS", "HSH", "HH", "SS", "SSH", "HHH", "HS"}

CONFIG_PATTERN = re.compile(
    r"[Cc]onfigurac[ií][oó]n\s*:?\s*(?:</strong>)?\s*([SHsh]{2,3})\b",
)
DIRECT_PATTERN = re.compile(r"\b(SSS|HSS|HSH|HH|SS|SSH)\b")


def extract_config_from_body(body_html: str) -> str | None:
    if not body_html:
        return None
    m = CONFIG_PATTERN.search(body_html)
    if m and m.group(1).upper() in VALID_CONFIGS:
        return m.group(1).upper()
    m = DIRECT_PATTERN.search(body_html)
    if m and m.group(1).upper() in VALID_CONFIGS:
        return m.group(1).upper()
    return None


# ── Fase 2: Scraping individual de la página del producto ────────────────────

PICKUP_KEYWORDS = re.compile(
    r"(SSS|HSS|HSH|HH|SS|SSH|"
    r"[Ss]ingle.?[Cc]oil|[Hh]umbucker|P[\-\s]?90|"
    r"bobina\s+simple|bobina\s+doble)",
)


def fetch_product_page(handle: str) -> str | None:
    safe_handle = urllib.parse.quote(handle, safe="/-_~")
    url = PRODUCT_URL + safe_handle
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


def extract_config_from_page(html: str) -> str | None:
    if not html:
        return None

    # Look for explicit config patterns
    m = CONFIG_PATTERN.search(html)
    if m:
        return m.group(1).upper()

    m = re.search(r"\b(SSS|HSS|HSH|SSH)\b", html)
    if m:
        return m.group(1).upper()

    # Count pickup types from specs
    single_coils = len(re.findall(
        r"(?:single.?coil|bobina\s+simple|single-coil)",
        html, re.IGNORECASE,
    ))
    humbuckers = len(re.findall(
        r"(?:humbucker|bobina\s+doble|double.?coil|humbucking)",
        html, re.IGNORECASE,
    ))
    p90s = len(re.findall(r"P[\-\s]?90", html, re.IGNORECASE))

    # Check for three single-coil pickup descriptions
    # Fender pages list Bridge/Middle/Neck pickups
    bridge = re.search(
        r"(?:bridge|puente)\s*(?:pickup|pastilla)[^<]{0,100}(?:single|simple)",
        html, re.IGNORECASE,
    )
    middle = re.search(
        r"(?:middle|medio|central)\s*(?:pickup|pastilla)[^<]{0,100}(?:single|simple)",
        html, re.IGNORECASE,
    )
    neck = re.search(
        r"(?:neck|mástil|cuello)\s*(?:pickup|pastilla)[^<]{0,100}(?:single|simple)",
        html, re.IGNORECASE,
    )

    if bridge and middle and neck:
        return "SSS"

    # Also check reverse order: "single coil ... bridge"
    sc_mentions = re.findall(
        r"(?:single.?coil|bobina\s+simple)[^<]{0,200}(?:bridge|middle|neck|puente|medio|mástil)",
        html, re.IGNORECASE,
    )
    if len(sc_mentions) >= 3:
        return "SSS"

    # If page lists 3 pickups all described as "bobina simple" style
    pickup_sections = re.findall(
        r"(?:Pastilla|Pickup)\s+(?:del?\s+)?(?:puente|bridge|medio|middle|mástil|neck|central)"
        r"[^<]{0,150}",
        html, re.IGNORECASE,
    )
    if len(pickup_sections) >= 3:
        all_single = all(
            re.search(r"(?:single|simple|bobina simple)", sec, re.IGNORECASE)
            for sec in pickup_sections
        )
        if all_single:
            return "SSS"

    if single_coils >= 3 and humbuckers == 0:
        return "SSS"
    if humbuckers >= 2 and single_coils == 0:
        return "HH"
    if humbuckers >= 1 and single_coils >= 2:
        return "HSS"

    return None


# ── Fase 3: Heurística por nombre de modelo ──────────────────────────────────

# Models known to be SSS
SSS_MODELS = [
    r"stratocaster(?!.*\b(?:hss|hsh|hh)\b)",
    r"strat(?:o)?(?!.*\b(?:hss|hsh|hh)\b)",
    r"\bstrato\b(?!.*\b(?:hss|hsh|hh)\b)",
]

# Models known to NOT be SSS (exclude them)
NON_SSS_MODELS = [
    r"les\s*paul", r"\blp\b", r"\bsg\b", r"explorer", r"flying\s*v",
    r"telecaster", r"tele\b", r"jazzmaster", r"jaguar", r"mustang",
    r"semi.?hollow", r"hollow", r"es[\-\s]?335", r"es[\-\s]?339",
    r"casino", r"archtop", r"sheraton", r"dot", r"riviera",
    r"jet\b", r"dinky", r"soloist", r"kelly", r"king\s*v", r"rhoads",
    r"meteora", r"cabronita", r"special\s*ii",
    r"ukulele", r"encordado", r"microfono", r"cuerdas", r"strings",
    r"kit\b.*(?:les\s*paul|lp)",
]


def heuristic_config(title: str) -> str | None:
    t = title.lower()

    # Skip non-guitar products
    for pat in NON_SSS_MODELS:
        if re.search(pat, t):
            return None  # Not SSS (or not determinable)

    for pat in SSS_MODELS:
        if re.search(pat, t):
            return "SSS"

    return None


# ── Pipeline principal ────────────────────────────────────────────────────────

def fetch_all_raw_products() -> list[dict]:
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


def classify_guitars(raw_products: list[dict], scrape_individual: bool = True):
    results = []

    for p in raw_products:
        title = p.get("title", "").strip()
        handle = p.get("handle", "")
        body = p.get("body_html", "") or ""
        vendor = p.get("vendor", "")

        variants = p.get("variants", [])
        prices = [float(v["price"]) for v in variants if v.get("price")]
        price = min(prices) if prices else 0
        available = any(v.get("available", False) for v in variants)

        images = p.get("images", [])
        image_url = images[0].get("src", "") if images else ""

        entry = {
            "titulo": title,
            "marca": vendor,
            "precio": price,
            "disponible": available,
            "url": PRODUCT_URL + handle,
            "imagen": image_url,
            "config": None,
            "config_fuente": None,
        }

        # Fase 1: body_html
        config = extract_config_from_body(body)
        if config:
            entry["config"] = config
            entry["config_fuente"] = "body_html"
            results.append(entry)
            continue

        # Fase 3 (quick check before slow scrape): heurística
        config = heuristic_config(title)
        if config:
            entry["config"] = config
            entry["config_fuente"] = "heurística"
            results.append(entry)
            continue

        # Fase 2: scraping individual (solo si no se determinó arriba)
        if scrape_individual:
            print(f"  Consultando: {title[:60]}...", file=sys.stderr)
            html = fetch_product_page(handle)
            config = extract_config_from_page(html) if html else None
            if config:
                entry["config"] = config
                entry["config_fuente"] = "página_individual"
            time.sleep(0.4)

        results.append(entry)

    return results


def main():
    parser = argparse.ArgumentParser(description="Filtrar guitarras SSS de TMS Music")
    parser.add_argument("--csv", action="store_true", help="Exportar SSS a CSV")
    parser.add_argument(
        "--solo-fase1",
        action="store_true",
        help="Solo usar body_html (sin scraping individual)",
    )
    args = parser.parse_args()

    print("Obteniendo catálogo completo...", file=sys.stderr)
    raw = fetch_all_raw_products()
    print(f"Total productos: {len(raw)}", file=sys.stderr)

    print("Clasificando configuración de pickups...", file=sys.stderr)
    classified = classify_guitars(raw, scrape_individual=not args.solo_fase1)

    # Resumen de configuraciones
    config_counts: dict[str, int] = {}
    unknown = 0
    for g in classified:
        c = g["config"]
        if c:
            config_counts[c] = config_counts.get(c, 0) + 1
        else:
            unknown += 1

    print("\n== Resumen de configuraciones ==", file=sys.stderr)
    for cfg, count in sorted(config_counts.items(), key=lambda x: -x[1]):
        print(f"  {cfg}: {count}", file=sys.stderr)
    print(f"  Sin determinar: {unknown}", file=sys.stderr)

    # Filtrar SSS
    sss = [g for g in classified if g["config"] == "SSS"]
    sss.sort(key=lambda g: g["precio"])

    print(f"\n== Guitarras SSS encontradas: {len(sss)} ==\n")
    print(f"{'#':>3}  {'Marca':<12} {'Titulo':<62} {'Precio COP':>14} {'Fuente':<18}")
    print("-" * 115)
    for i, g in enumerate(sss, 1):
        precio_str = f"${g['precio']:,.0f}" if g["precio"] else "N/A"
        titulo = g["titulo"][:60] + ".." if len(g["titulo"]) > 62 else g["titulo"]
        print(f"{i:>3}  {g['marca']:<12} {titulo:<62} {precio_str:>14} {g['config_fuente']:<18}")

    if args.csv:
        filename = "guitarras_sss.csv"
        keys = ["titulo", "marca", "precio", "disponible", "url", "imagen", "config_fuente"]
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(sss)
        print(f"\nExportado a {filename}", file=sys.stderr)


if __name__ == "__main__":
    main()
