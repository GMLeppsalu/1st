# German Tax Revenue Dashboard

A dashboard that visualises year-over-year changes in German tax revenue, combining monthly data from the Federal Ministry of Finance (BMF) with quarterly data from the Federal Statistical Office (Destatis GENESIS API).

## Components

| File | Purpose |
|------|---------|
| `scraper.py` | Fetches BMF monthly HTML tables and Destatis GENESIS quarterly CSV data |
| `index.html` | Dashboard with Chart.js bar charts and data tables |
| `data/bmf_monthly.json` | Scraped BMF monthly tax revenue by category |
| `data/genesis_quarterly.json` | Scraped Destatis quarterly tax revenue |
| `.github/workflows/update-data.yml` | GitHub Actions workflow for automated monthly updates |

## Running the Scraper Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the scraper
python scraper.py
```

The scraper will:

1. Fetch monthly tax revenue pages from the BMF website for the current and previous year (January through the current month)
2. Parse the HTML tables to extract values for: total tax revenue, joint taxes, wages tax, assessed income tax, corporation tax, VAT, federal taxes, and Länder taxes
3. Fetch quarterly data from the Destatis GENESIS API (table 71211-0003) using guest credentials
4. Save results to `data/bmf_monthly.json` and `data/genesis_quarterly.json`

If a month's BMF page doesn't exist yet (e.g., future months), it is skipped without error.

## Viewing the Dashboard

Serve the project directory with any static HTTP server:

```bash
# Python
python -m http.server 8000

# Then open http://localhost:8000 in your browser
```

The dashboard reads from the JSON files in `data/` and renders:

- **Monthly (BMF):** Bar chart of YoY % change in total tax revenue, a grouped bar chart breaking down wages tax / VAT / corporation tax, and a data table with raw figures
- **Quarterly (Destatis):** Bar chart of YoY % change per quarter, and a data table with raw figures

Bars are colour-coded green (positive YoY) and red (negative YoY).

## GitHub Actions Automation

The workflow in `.github/workflows/update-data.yml`:

- **Scheduled run:** Executes on the 20th of every month at 10:00 UTC, which aligns with the BMF's typical publication date
- **Manual trigger:** Can also be run manually via the "Run workflow" button in the Actions tab
- **Auto-commit:** If the scraper produces updated data, the workflow commits and pushes the new JSON files back to the repository

No secrets or tokens are required — the BMF website is public and the GENESIS API uses guest credentials (`GAST`/`GAST`).

## Data Sources

- **BMF Monthly Reports:** [bundesfinanzministerium.de](https://www.bundesfinanzministerium.de/Content/EN/Standardartikel/Press_Room/Publications/Monthly_Report/Key_Figures.html)
- **Destatis GENESIS:** [www-genesis.destatis.de](https://www-genesis.destatis.de/) — Table 71211-0003 (Tax revenue by type of tax, quarterly)
