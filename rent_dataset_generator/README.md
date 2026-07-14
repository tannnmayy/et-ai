# Bengaluru Rental Dataset Generator

One-time dataset generator for **AQI Sentinel – Citizen Mode**.

Scrapes rental listings across Bengaluru localities from public property portals and produces a clean, analysis-ready dataset.

## Goal

Produce thousands of normalized rental listings so Citizen Mode can compute locality-level features such as:

- average / median rent
- rent per sqft
- BHK mix
- furnishing mix
- property-type mix

This is **not** a production crawler. It is a simple, reliable, one-shot extractor.

## Sources

Priority used by the script:

1. **MagicBricks** (primary) – structured `propertySearch` JSON via a browser session  
2. Housing.com / 99acres – often blocked by bot protection from automation IPs  
3. NoBroker – optional secondary (disabled by default if blocked)

If a source fails, the script continues with others.

## Setup

```bash
cd rent_dataset_generator
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
python scraper.py
```

Useful flags:

```bash
python scraper.py --max-city-pages 120
python scraper.py --skip-locality-deep
python scraper.py --headed
```

| Flag | Description |
|------|-------------|
| `--max-city-pages N` | City-wide API pages (default 120, ~30 listings/page, soft-capped by source) |
| `--max-locality-pages N` | Pages per target locality (default 12) |
| `--skip-locality-deep` | Skip per-locality deepening (faster, smaller dataset) |
| `--skip-slices` | Skip BHK / budget slice expansion |
| `--headed` | Show browser window |

Typical full run: **15–40 minutes**, depending on network.

## Output

```
output/
├── rentals.csv            # cleaned normalized dataset
├── rentals.json           # same data as JSON
└── scrape_summary.json    # counts, coverage, missing-value stats
```

### Schema (normalized)

| Field | Required | Notes |
|-------|----------|-------|
| listing_id | yes | Source listing id |
| source | yes | e.g. `magicbricks` |
| locality | yes | Normalized locality name |
| rent | yes | Monthly rent (INR, integer) |
| bhk | yes | Bedroom count (string/int) |
| area_sqft | preferred | Carpet/built-up when available |
| property_type | preferred | Apartment / House / Villa / … |
| furnishing | preferred | Unfurnished / Semi-Furnished / Furnished |
| listing_url | yes | Canonical URL |
| maintenance | optional | |
| deposit | optional | Security deposit |
| brokerage | optional | |
| bathrooms | optional | |
| balconies | optional | |
| parking | optional | |
| verified | optional | |
| posted_date | optional | |
| latitude | optional | |
| longitude | optional | |
| owner_broker | optional | Advertiser type / name |
| available_from | optional | |

## Approach

1. Open a MagicBricks Bengaluru rent session (Playwright).  
2. Pull **city-wide** result pages via the site’s JSON search endpoint.  
3. Expand coverage with **BHK** and **budget** query slices (different result windows).  
4. Learn locality IDs from results, then **deep-scrape** 40–60 known Bengaluru localities.  
5. Normalize fields, drop invalid rents / missing keys, dedupe.  
6. Write CSV + JSON + summary.

## Notes

- Respect site terms; use for research / internal product development.  
- Listings change daily — re-run when you need a fresh snapshot.  
- Some portals block datacenter IPs; MagicBricks has been the most reliable path for bulk structured data.
