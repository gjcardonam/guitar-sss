"""
Scraper de guitarras eléctricas de TMS Music (tmsmusic.co)
Usa la API JSON de Shopify para obtener todos los productos de forma determinista.

Uso:
    python scrape_tms.py              # Imprime la lista en consola
    python scrape_tms.py --csv        # Exporta a guitarras_electricas.csv
    python scrape_tms.py --json       # Exporta a guitarras_electricas.json
"""

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "https://tmsmusic.co/collections/guitarras-electricas/products.json"
PRODUCTS_PER_PAGE = 250  # Shopify max per page
SITE_URL = "https://tmsmusic.co/products/"


def fetch_page(page: int) -> list[dict]:
    url = f"{BASE_URL}?limit={PRODUCTS_PER_PAGE}&page={page}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get("products", [])
    except urllib.error.HTTPError as e:
        print(f"Error HTTP {e.code} en página {page}", file=sys.stderr)
        return []
    except urllib.error.URLError as e:
        print(f"Error de conexión en página {page}: {e.reason}", file=sys.stderr)
        return []


def fetch_all_products() -> list[dict]:
    all_products = []
    page = 1
    while True:
        print(f"Obteniendo página {page}...", file=sys.stderr)
        products = fetch_page(page)
        if not products:
            break
        all_products.extend(products)
        page += 1
        time.sleep(0.5)  # ser amable con el servidor
    return all_products


def parse_product(p: dict) -> dict:
    variants = p.get("variants", [])
    prices = [float(v["price"]) for v in variants if v.get("price")]
    compare_prices = [
        float(v["compare_at_price"])
        for v in variants
        if v.get("compare_at_price")
    ]

    image_url = ""
    images = p.get("images", [])
    if images:
        image_url = images[0].get("src", "")

    return {
        "id": p.get("id"),
        "titulo": p.get("title", "").strip(),
        "marca": p.get("vendor", "").strip(),
        "tipo": p.get("product_type", "").strip(),
        "precio": min(prices) if prices else 0,
        "precio_antes": min(compare_prices) if compare_prices else None,
        "disponible": any(v.get("available", False) for v in variants),
        "sku": variants[0].get("sku", "") if variants else "",
        "url": SITE_URL + p.get("handle", ""),
        "imagen": image_url,
        "tags": ", ".join(p.get("tags", [])),
        "created_at": p.get("created_at", ""),
        "updated_at": p.get("updated_at", ""),
    }


def print_table(guitars: list[dict]):
    print(f"\n{'#':>3}  {'Marca':<15} {'Título':<65} {'Precio COP':>14} {'Disp.':>5}")
    print("-" * 108)
    for i, g in enumerate(guitars, 1):
        precio_str = f"${g['precio']:,.0f}" if g["precio"] else "N/A"
        disp = "Sí" if g["disponible"] else "No"
        titulo = g["titulo"][:63] + ".." if len(g["titulo"]) > 65 else g["titulo"]
        print(f"{i:>3}  {g['marca']:<15} {titulo:<65} {precio_str:>14} {disp:>5}")
    print(f"\nTotal: {len(guitars)} productos")


def export_csv(guitars: list[dict], filename: str = "guitarras_electricas.csv"):
    if not guitars:
        return
    keys = guitars[0].keys()
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(guitars)
    print(f"Exportado a {filename} ({len(guitars)} productos)", file=sys.stderr)


def export_json(guitars: list[dict], filename: str = "guitarras_electricas.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(guitars, f, ensure_ascii=False, indent=2)
    print(f"Exportado a {filename} ({len(guitars)} productos)", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Scraper de guitarras TMS Music")
    parser.add_argument("--csv", action="store_true", help="Exportar a CSV")
    parser.add_argument("--json", action="store_true", help="Exportar a JSON")
    args = parser.parse_args()

    raw_products = fetch_all_products()
    guitars = [parse_product(p) for p in raw_products]

    # Ordenar por fecha de creación (más reciente primero)
    guitars.sort(key=lambda g: g["created_at"], reverse=True)

    print_table(guitars)

    if args.csv:
        export_csv(guitars)
    if args.json:
        export_json(guitars)


if __name__ == "__main__":
    main()
