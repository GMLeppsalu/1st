#!/usr/bin/env python3
"""
German Tax Revenue Scraper
Fetches monthly tax revenue data from BMF and quarterly data from Destatis GENESIS API.
"""

import json
import os
import sys
from datetime import datetime, date
from io import StringIO

import requests
from bs4 import BeautifulSoup
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BMF_URL_TEMPLATE = (
    "https://www.bundesfinanzministerium.de/Content/EN/Standardartikel/"
    "Press_Room/Publications/Monthly_Report/Key_Figures/"
    "{year}/tables/{year}-{month:02d}-tax-revenue-trends.html"
)

GENESIS_URL = "https://www-genesis.destatis.de/genesisWS/rest/2020/data/table"
GENESIS_PARAMS = {
    "username": "GAST",
    "password": "GAST",
    "name": "71211-0003",
    "area": "all",
    "format": "ffcsv",
}

# Tax categories we look for in the BMF table
TAX_CATEGORIES = [
    "total tax revenue",
    "joint taxes",
    "wages tax",
    "assessed income tax",
    "corporation tax",
    "turnover tax (vat)",
    "federal taxes",
    "länder taxes",
]

# Aliases to normalise category names from varying BMF table headers
CATEGORY_ALIASES = {
    "tax revenue, total": "total tax revenue",
    "tax revenue total": "total tax revenue",
    "total": "total tax revenue",
    "wage tax": "wages tax",
    "vat": "turnover tax (vat)",
    "turnover tax": "turnover tax (vat)",
    "sales tax": "turnover tax (vat)",
    "value added tax": "turnover tax (vat)",
    "assessed income tax (ait)": "assessed income tax",
    "corporate tax": "corporation tax",
    "corporation tax (ct)": "corporation tax",
    "lander taxes": "länder taxes",
    "laender taxes": "länder taxes",
}


def normalise_category(raw: str) -> str | None:
    """Return a normalised category name or None if not relevant."""
    cleaned = raw.strip().lower()
    # Direct match
    if cleaned in TAX_CATEGORIES:
        return cleaned
    # Alias match
    if cleaned in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[cleaned]
    # Substring match as fallback
    for cat in TAX_CATEGORIES:
        if cat in cleaned or cleaned in cat:
            return cat
    return None


def fetch_bmf_month(year: int, month: int) -> dict | None:
    """Fetch and parse a single BMF monthly tax revenue page.

    Returns a dict like:
        {"year": 2025, "month": 1, "categories": {"total tax revenue": 12345.6, ...}}
    or None if the page doesn't exist / can't be parsed.
    """
    url = BMF_URL_TEMPLATE.format(year=year, month=month)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  BMF {year}-{month:02d}: HTTP {resp.status_code}, skipping")
            return None
    except requests.RequestException as exc:
        print(f"  BMF {year}-{month:02d}: request error ({exc}), skipping")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        print(f"  BMF {year}-{month:02d}: no table found, skipping")
        return None

    categories: dict[str, float | None] = {}
    rows = table.find_all("tr")

    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        label = cells[0].get_text(strip=True)
        norm = normalise_category(label)
        if norm is None:
            continue

        # Take the last numeric cell (usually the most recent month's absolute value)
        value = None
        for cell in reversed(cells[1:]):
            text = cell.get_text(strip=True).replace(",", "").replace("−", "-").replace("–", "-")
            try:
                value = float(text)
                break
            except ValueError:
                continue

        categories[norm] = value

    if not categories:
        print(f"  BMF {year}-{month:02d}: could not parse any categories, skipping")
        return None

    print(f"  BMF {year}-{month:02d}: parsed {len(categories)} categories")
    return {"year": year, "month": month, "categories": categories}


def fetch_bmf_data() -> list[dict]:
    """Fetch BMF monthly data for the current and previous year."""
    today = date.today()
    current_year = today.year
    previous_year = current_year - 1

    records: list[dict] = []

    for year in [previous_year, current_year]:
        print(f"Fetching BMF data for {year}...")
        for month in range(1, 13):
            # Don't try future months
            if year == current_year and month > today.month:
                break
            result = fetch_bmf_month(year, month)
            if result is not None:
                records.append(result)

    return records


def fetch_genesis_data() -> list[dict]:
    """Fetch quarterly tax revenue data from Destatis GENESIS API (table 71211-0003).

    Returns a list of dicts like:
        [{"year": 2023, "quarter": "Q1", "category": "...", "value": 12345.6}, ...]
    """
    print("Fetching GENESIS quarterly data...")
    try:
        resp = requests.get(GENESIS_URL, params=GENESIS_PARAMS, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"  GENESIS: HTTP {resp.status_code}")
            return []
    except requests.RequestException as exc:
        print(f"  GENESIS: request error ({exc})")
        return []

    content = resp.text

    # The ffcsv format from GENESIS has metadata lines before the actual CSV.
    # Find where the CSV data starts (look for the header line).
    lines = content.splitlines()
    csv_start = 0
    for i, line in enumerate(lines):
        # The header line typically contains semicolons and column labels
        if ";" in line and any(
            kw in line.lower() for kw in ["zeit", "time", "statistik", "name"]
        ):
            csv_start = i
            break

    csv_text = "\n".join(lines[csv_start:])
    if not csv_text.strip():
        print("  GENESIS: empty CSV content")
        return []

    try:
        df = pd.read_csv(StringIO(csv_text), sep=";", decimal=",", encoding="utf-8")
    except Exception as exc:
        print(f"  GENESIS: CSV parse error ({exc})")
        return []

    records: list[dict] = []

    # Try to identify time and value columns
    time_col = None
    value_col = None
    cat_col = None

    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("zeit", "time"):
            time_col = col
        elif "wert" in cl or "val" in cl:
            value_col = col
        elif any(k in cl for k in ("steuerart", "tax", "name", "auspraeg")):
            cat_col = col

    # Fallback: use positional columns
    if time_col is None and len(df.columns) >= 1:
        time_col = df.columns[0]
    if value_col is None and len(df.columns) >= 2:
        value_col = df.columns[-1]

    for _, row in df.iterrows():
        try:
            time_raw = str(row[time_col]).strip() if time_col else ""
            # GENESIS quarterly time codes look like "2023Q1" or "VIERJ-2023-Q1"
            year = None
            quarter = None
            for part in time_raw.replace("-", " ").split():
                if len(part) == 4 and part.isdigit():
                    year = int(part)
                elif part.upper().startswith("Q") and len(part) == 2:
                    quarter = part.upper()
                elif len(part) == 6 and part[:4].isdigit() and part[4] == "Q":
                    year = int(part[:4])
                    quarter = part[4:].upper()

            if year is None or quarter is None:
                continue

            val_raw = str(row[value_col]).strip().replace(",", ".") if value_col else ""
            try:
                value = float(val_raw)
            except ValueError:
                value = None

            category = str(row[cat_col]).strip() if cat_col else "total"

            records.append(
                {
                    "year": year,
                    "quarter": quarter,
                    "category": category,
                    "value_meur": value,
                }
            )
        except Exception:
            continue

    print(f"  GENESIS: parsed {len(records)} quarterly records")
    return records


def save_json(data: object, filename: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)
    payload = {
        "last_updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": data,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {filepath}")


def main() -> None:
    print("=" * 60)
    print("German Tax Revenue Scraper")
    print("=" * 60)

    bmf_data = fetch_bmf_data()
    save_json(bmf_data, "bmf_monthly.json")

    genesis_data = fetch_genesis_data()
    save_json(genesis_data, "genesis_quarterly.json")

    print("=" * 60)
    print("Done.")
    total = len(bmf_data) + len(genesis_data)
    if total == 0:
        print("WARNING: No data was fetched. This may be due to network restrictions.")
        print("The scraper will work when run locally or in GitHub Actions.")
    print("=" * 60)


if __name__ == "__main__":
    main()
