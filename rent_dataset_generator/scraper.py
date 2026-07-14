"""
AQI Sentinel – Citizen Mode
Bengaluru rental housing dataset generator (one-time).

Primary source: MagicBricks propertySearch JSON (via Playwright session).
Housing.com / 99acres often block automation; we degrade gracefully.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

CITY_ID = "3327"  # Bangalore on MagicBricks
PROPERTY_TYPES = "10002,10003,10021,10022,10020,10001,10017"
PAGE_SIZE = 30
API = "https://www.magicbricks.com/mbsrp/propertySearch.html"
CITY_PAGE = (
    "https://www.magicbricks.com/property-for-rent/"
    "residential-real-estate?cityName=Bangalore"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Target localities for deep scrape (canonical display names).
# MagicBricks URL slugs used to open the locality SRP when id is unknown.
TARGET_LOCALITIES: list[dict[str, str]] = [
    {"name": "HSR Layout", "slug": "HSR-Layout"},
    {"name": "Koramangala", "slug": "Koramangala"},
    {"name": "Whitefield", "slug": "Whitefield"},
    {"name": "Bellandur", "slug": "Bellandur"},
    {"name": "Marathahalli", "slug": "Marathahalli"},
    {"name": "Indiranagar", "slug": "Indiranagar"},
    {"name": "Electronic City", "slug": "Electronic-City"},
    {"name": "JP Nagar", "slug": "JP-Nagar"},
    {"name": "Jayanagar", "slug": "Jayanagar"},
    {"name": "BTM Layout", "slug": "BTM-Layout"},
    {"name": "Hebbal", "slug": "Hebbal"},
    {"name": "Yelahanka", "slug": "Yelahanka"},
    {"name": "Sarjapur Road", "slug": "Sarjapur-Road"},
    {"name": "Mahadevapura", "slug": "Mahadevapura"},
    {"name": "Brookefield", "slug": "Brookefield"},
    {"name": "CV Raman Nagar", "slug": "CV-Raman-Nagar"},
    {"name": "Kalyan Nagar", "slug": "Kalyan-Nagar"},
    {"name": "Yeshwanthpur", "slug": "Yeshwanthpur"},
    {"name": "Banashankari", "slug": "Banashankari"},
    {"name": "RR Nagar", "slug": "RR-Nagar"},
    {"name": "Malleshwaram", "slug": "Malleshwaram"},
    {"name": "Rajajinagar", "slug": "Rajajinagar"},
    {"name": "Bannerghatta Road", "slug": "Bannerghatta-Road"},
    {"name": "Hennur", "slug": "Hennur"},
    {"name": "Thanisandra", "slug": "Thanisandra"},
    {"name": "Varthur", "slug": "Varthur"},
    {"name": "KR Puram", "slug": "KR-Puram"},
    {"name": "Domlur", "slug": "Domlur"},
    {"name": "Ulsoor", "slug": "Ulsoor"},
    {"name": "Richmond Town", "slug": "Richmond-Town"},
    {"name": "Frazer Town", "slug": "Frazer-Town"},
    {"name": "Basavanagudi", "slug": "Basavanagudi"},
    {"name": "Vijayanagar", "slug": "Vijayanagar"},
    {"name": "Nagarbhavi", "slug": "Nagarbhavi"},
    {"name": "Kanakapura Road", "slug": "Kanakapura-Road"},
    {"name": "Hoodi", "slug": "Hoodi"},
    {"name": "Kadubeesanahalli", "slug": "Kadubeesanahalli"},
    {"name": "Bommanahalli", "slug": "Bommanahalli"},
    {"name": "Kundalahalli", "slug": "Kundalahalli"},
    {"name": "Doddanekundi", "slug": "Doddanekundi"},
    {"name": "Sahakar Nagar", "slug": "Sahakar-Nagar"},
    {"name": "RT Nagar", "slug": "RT-Nagar"},
    {"name": "Banaswadi", "slug": "Banaswadi"},
    {"name": "Horamavu", "slug": "Horamavu"},
    {"name": "Kammanahalli", "slug": "Kammanahalli"},
    {"name": "Begur", "slug": "Begur"},
    {"name": "Kengeri", "slug": "Kengeri"},
    {"name": "Peenya", "slug": "Peenya"},
    {"name": "Arekere", "slug": "Arekere"},
    {"name": "Gottigere", "slug": "Gottigere"},
    {"name": "Singasandra", "slug": "Singasandra"},
    {"name": "Kadugodi", "slug": "Kadugodi"},
    {"name": "Haralur", "slug": "Haralur"},
    {"name": "Kasavanahalli", "slug": "Kasavanahalli"},
    {"name": "Ejipura", "slug": "Ejipura"},
    {"name": "Padmanabhanagar", "slug": "Padmanabhanagar"},
    {"name": "Kumaraswamy Layout", "slug": "Kumaraswamy-Layout"},
    {"name": "Hulimavu", "slug": "Hulimavu"},
    {"name": "Jigani", "slug": "Jigani"},
    {"name": "Chandapura", "slug": "Chandapura"},
    {"name": "Devanahalli", "slug": "Devanahalli"},
    {"name": "Mysore Road", "slug": "Mysore-Road"},
    {"name": "Hosa Road", "slug": "Hosa-Road"},
    {"name": "Panathur", "slug": "Panathur"},
    {"name": "Ramamurthy Nagar", "slug": "Ramamurthy-Nagar"},
]

CSV_FIELDS = [
    "listing_id",
    "source",
    "locality",
    "rent",
    "bhk",
    "area_sqft",
    "property_type",
    "furnishing",
    "listing_url",
    "maintenance",
    "deposit",
    "brokerage",
    "bathrooms",
    "balconies",
    "parking",
    "verified",
    "posted_date",
    "latitude",
    "longitude",
    "owner_broker",
    "available_from",
    "city",
    "address_hint",
    "title",
]

# Locality name aliases → canonical
LOCALITY_ALIASES = {
    "hsr layout": "HSR Layout",
    "hsr": "HSR Layout",
    "indira nagar": "Indiranagar",
    "indiranagar": "Indiranagar",
    "jp nagar": "JP Nagar",
    "j p nagar": "JP Nagar",
    "btm layout": "BTM Layout",
    "btm": "BTM Layout",
    "electronic city": "Electronic City",
    "electronics city phase 1": "Electronic City",
    "electronics city phase 2": "Electronic City",
    "rajaji nagar": "Rajajinagar",
    "rajajinagar": "Rajajinagar",
    "r r nagar": "RR Nagar",
    "rr nagar": "RR Nagar",
    "rajarajeshwari nagar": "RR Nagar",
    "sahakara nagar": "Sahakar Nagar",
    "sahakar nagar": "Sahakar Nagar",
    "kr puram": "KR Puram",
    "k r puram": "KR Puram",
    "cv raman nagar": "CV Raman Nagar",
    "c v raman nagar": "CV Raman Nagar",
    "brookfield": "Brookefield",
    "brookefield": "Brookefield",
    "yeshwantpur": "Yeshwanthpur",
    "yeshwanthpur": "Yeshwanthpur",
    "ulsoor": "Ulsoor",
    "halasuru": "Ulsoor",
    "fraser town": "Frazer Town",
    "frazer town": "Frazer Town",
    "sarjapur road": "Sarjapur Road",
    "sarjapura road": "Sarjapur Road",
    "bannerghatta road": "Bannerghatta Road",
    "bannerghatta main road": "Bannerghatta Road",
    "kanakapura road": "Kanakapura Road",
    "thanisandra main road": "Thanisandra",
    "haralur main road": "Haralur",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def normalize_locality(name: str | None) -> str | None:
    if not name:
        return None
    raw = clean_text(name)
    if not raw:
        return None
    key = raw.lower()
    if key in LOCALITY_ALIASES:
        return LOCALITY_ALIASES[key]
    # strip ", Bangalore" suffixes
    key2 = re.sub(r",?\s*(bangalore|bengaluru).*$", "", key).strip()
    if key2 in LOCALITY_ALIASES:
        return LOCALITY_ALIASES[key2]
    # title-case leftover
    return re.sub(r",?\s*(Bangalore|Bengaluru).*$", "", raw).strip()


def normalize_furnishing(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if "semi" in v:
        return "Semi-Furnished"
    if v in {"furnished", "full", "fully furnished"} or "fully" in v:
        return "Furnished"
    if "unfurn" in v or v in {"none", "bare"}:
        return "Unfurnished"
    return clean_text(value)


def normalize_property_type(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if "studio" in v:
        return "Studio"
    if "villa" in v:
        return "Villa"
    if "independent" in v or "house" in v or "builder floor" in v:
        return "House"
    if "apartment" in v or "flat" in v or "multistorey" in v:
        return "Apartment"
    if "service" in v:
        return "Service Apartment"
    if "penthouse" in v:
        return "Penthouse"
    return clean_text(value)


def parse_lat_lon(item: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = item.get("ltcoordGeo") or ""
    if isinstance(coords, str) and "," in coords:
        try:
            a, b = coords.split(",", 1)
            lat, lon = float(a.strip()), float(b.strip())
            if abs(lat) > 1 and abs(lon) > 1:
                return lat, lon
        except ValueError:
            pass
    try:
        lat = float(item.get("pmtLat") or 0)
        lon = float(item.get("pmtLong") or 0)
        if abs(lat) > 1 and abs(lon) > 1:
            return lat, lon
    except (TypeError, ValueError):
        pass
    return None, None


def listing_url_mb(item: dict[str, Any]) -> str | None:
    seo = item.get("seoURL")
    if seo:
        return "https://www.magicbricks.com/" + str(seo).lstrip("/")
    raw = item.get("url")
    if raw:
        return f"https://www.magicbricks.com/propertyDetails/{raw}"
    return None


# ---------------------------------------------------------------------------
# MagicBricks client
# ---------------------------------------------------------------------------

class MagicBricksClient:
    def __init__(self, page, pause: float = 0.35):
        self.page = page
        self.pause = pause

    def fetch(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        base = {
            "editSearch": "Y",
            "category": "R",
            "propertyType": PROPERTY_TYPES,
            "city": CITY_ID,
            "offset": "0",
            "maxOffset": "0",
            "sortBy": "premiumRecent",
            "postedSince": "-1",
            "pType": PROPERTY_TYPES,
            "isNRI": "N",
            "multiLang": "en",
        }
        base.update({k: str(v) for k, v in params.items() if v is not None})
        qs = "&".join(f"{k}={v}" for k, v in base.items())
        url = f"{API}?{qs}"
        data = self.page.evaluate(
            """async (url) => {
                try {
                    const r = await fetch(url, {
                        credentials: 'include',
                        headers: {
                            'x-requested-with': 'XMLHttpRequest',
                            'accept': 'application/json, text/javascript, */*; q=0.01',
                        },
                    });
                    if (!r.ok) return { _error: r.status };
                    return await r.json();
                } catch (e) {
                    return { _error: String(e) };
                }
            }""",
            url,
        )
        time.sleep(self.pause)
        if not isinstance(data, dict) or data.get("_error"):
            return []
        rows = data.get("resultList") or []
        return rows if isinstance(rows, list) else []

    def paginate(
        self,
        *,
        label: str,
        extra: dict[str, Any] | None = None,
        max_pages: int,
        sink: list[dict[str, Any]],
        seen_ids: set[str],
    ) -> int:
        """Fetch up to max_pages; append raw items; return new unique count."""
        extra = extra or {}
        empty_streak = 0
        new_total = 0
        for page_num in range(1, max_pages + 1):
            groupstart = (page_num - 1) * PAGE_SIZE
            rows = self.fetch(
                {
                    "page": page_num,
                    "groupstart": groupstart,
                    **extra,
                }
            )
            if not rows:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                continue

            new_here = 0
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                lid = str(raw.get("id") or "").strip()
                if not lid or lid in seen_ids:
                    continue
                seen_ids.add(lid)
                raw["_source"] = "magicbricks"
                sink.append(raw)
                new_here += 1
                new_total += 1

            print(
                f"    [{label}] page {page_num}: "
                f"{len(rows)} rows, {new_here} new (unique {len(seen_ids)})"
            )
            if new_here == 0:
                empty_streak += 1
                if empty_streak >= 2:
                    break
            else:
                empty_streak = 0
        return new_total


def resolve_locality_id_from_page(page, slug: str) -> str | None:
    """Open locality SRP and capture localityName from network or listing ids."""
    url = (
        "https://www.magicbricks.com/property-for-rent/residential-real-estate"
        f"?cityName=Bangalore&Locality={slug}"
    )
    found: list[str] = []

    def on_request(req):
        if "propertySearch.html" in req.url and "localityName=" in req.url:
            m = re.search(r"localityName=(\d+)", req.url)
            if m:
                found.append(m.group(1))

    page.on("request", on_request)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2000)
        # Trigger lazy search requests
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(2000)
    except Exception as exc:
        print(f"      resolve {slug}: navigation error {exc}")
    finally:
        try:
            page.remove_listener("request", on_request)
        except Exception:
            pass

    if found:
        return found[0]

    # Fallback: call city API is useless; try extract from first card via API
    # using title-only approach – scrape first page HTML listing ids then
    # city-wide map. Return None if unknown.
    return None


def normalize_magicbricks_item(item: dict[str, Any]) -> dict[str, Any] | None:
    rent = to_int(item.get("price"))
    lid = str(item.get("id") or "").strip()
    if not lid or not rent:
        return None

    # Drop obvious sale-price / corrupt rent outliers for rentals
    if rent < 2000 or rent > 1_000_000:
        return None

    lat, lon = parse_lat_lon(item)
    locality = normalize_locality(
        item.get("locSeoName") or item.get("lmtDName") or item.get("urlLocName")
    )
    area = to_int(item.get("carpetArea")) or to_int(
        item.get("coveredArea") or item.get("ca")
    )
    bhk = clean_text(item.get("bedroomD"))
    # Studio sometimes has empty bedroom
    if not bhk and item.get("propTypeD") and "studio" in str(item.get("propTypeD")).lower():
        bhk = "0"

    advertiser = clean_text(item.get("userType"))
    name = clean_text(item.get("oname") or item.get("contName"))
    owner_broker = None
    if advertiser and name:
        owner_broker = f"{advertiser}: {name}"
    elif advertiser:
        owner_broker = advertiser
    elif name:
        owner_broker = name

    verified = None
    if item.get("ctVerifd") is not None:
        verified = str(item.get("ctVerifd")).upper() in {"Y", "TRUE", "1"}

    url = listing_url_mb(item)
    if not url:
        return None

    return {
        "listing_id": lid,
        "source": "magicbricks",
        "locality": locality or "Unknown",
        "rent": rent,
        "bhk": bhk,
        "area_sqft": area,
        "property_type": normalize_property_type(item.get("propTypeD")),
        "furnishing": normalize_furnishing(item.get("furnishedD")),
        "listing_url": url,
        "maintenance": to_int(item.get("maintenanceCharges")),
        "deposit": to_int(item.get("bookingAmtExact")),
        "brokerage": None,
        "bathrooms": clean_text(item.get("bathD")),
        "balconies": clean_text(item.get("balconiesD")),
        "parking": clean_text(item.get("parkingD")),
        "verified": verified,
        "posted_date": clean_text(item.get("postDateT") or item.get("postedLabelD")),
        "latitude": lat,
        "longitude": lon,
        "owner_broker": owner_broker,
        "available_from": clean_text(item.get("possStatusD")),
        "city": "Bengaluru",
        "address_hint": clean_text(item.get("catAdd1") or item.get("ltOther")),
        "title": clean_text(item.get("propertyTitle")),
        "_loc_id": str(item.get("lt") or item.get("loc") or "") or None,
        "_raw_locality": clean_text(
            item.get("locSeoName") or item.get("lmtDName")
        ),
    }


# ---------------------------------------------------------------------------
# Cleaning / export
# ---------------------------------------------------------------------------

def clean_dataset(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Normalize, validate, dedupe. Returns (clean_rows, stats)."""
    stats = {
        "raw_count": len(rows),
        "dropped_invalid_rent": 0,
        "dropped_missing_required": 0,
        "duplicates_removed": 0,
    }

    cleaned: list[dict[str, Any]] = []
    for r in rows:
        if r.get("source") == "magicbricks" and "_source" in r:
            # still raw
            n = normalize_magicbricks_item(r)
        elif "listing_id" in r and "rent" in r and "source" in r:
            n = r
        else:
            n = normalize_magicbricks_item(r)

        if n is None:
            stats["dropped_invalid_rent"] += 1
            continue

        required_ok = all(
            n.get(k) not in (None, "")
            for k in ("listing_id", "source", "locality", "rent", "listing_url")
        )
        if not required_ok:
            stats["dropped_missing_required"] += 1
            continue
        cleaned.append(n)

    # Dedupe: prefer same source+listing_id; also fuzzy rent+locality+bhk+area
    by_id: dict[str, dict[str, Any]] = {}
    for n in cleaned:
        key = f"{n['source']}:{n['listing_id']}"
        if key not in by_id:
            by_id[key] = n
        else:
            stats["duplicates_removed"] += 1

    unique = list(by_id.values())

    # Secondary fuzzy dedupe across near-identical listings
    fuzzy_seen: set[str] = set()
    final: list[dict[str, Any]] = []
    for n in unique:
        fkey = "|".join(
            [
                str(n.get("locality")),
                str(n.get("rent")),
                str(n.get("bhk")),
                str(n.get("area_sqft")),
                str(n.get("furnishing")),
            ]
        )
        if fkey in fuzzy_seen:
            stats["duplicates_removed"] += 1
            continue
        fuzzy_seen.add(fkey)
        # strip internal keys
        out = {k: v for k, v in n.items() if not k.startswith("_")}
        final.append(out)

    stats["final_count"] = len(final)
    return final, stats


def missing_value_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    total = len(rows)
    out: dict[str, Any] = {}
    for field in CSV_FIELDS:
        missing = sum(1 for r in rows if r.get(field) in (None, ""))
        out[field] = {
            "missing": missing,
            "missing_pct": round(100.0 * missing / total, 2),
        }
    return out


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "rentals.csv"
    json_path = OUTPUT_DIR / "rentals.json"
    summary_path = OUTPUT_DIR / "scrape_summary.json"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\nWrote:")
    print(f"  {csv_path}  ({len(rows)} rows)")
    print(f"  {json_path}")
    print(f"  {summary_path}")


# ---------------------------------------------------------------------------
# Main scrape orchestration
# ---------------------------------------------------------------------------

def scrape_magicbricks(args: argparse.Namespace) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    seen: set[str] = set()
    locality_ids: dict[str, str] = {}  # normalized name -> mb id

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=USER_AGENT,
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        print("Opening MagicBricks Bengaluru rent search…")
        page.goto(CITY_PAGE, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(3500)
        title = page.title()
        print(f"  title: {title}")
        if "Security Alert" in title or "Access Denied" in title:
            browser.close()
            raise RuntimeError("MagicBricks blocked this session.")

        client = MagicBricksClient(page, pause=args.pause)

        # 1) City-wide
        print("\n[1/4] City-wide listings…")
        client.paginate(
            label="city",
            max_pages=args.max_city_pages,
            sink=raw,
            seen_ids=seen,
        )

        # Learn locality IDs from raw rows
        for item in raw:
            loc_name = normalize_locality(
                item.get("locSeoName") or item.get("lmtDName")
            )
            loc_id = str(item.get("lt") or item.get("loc") or "").strip()
            if loc_name and loc_id and loc_name not in locality_ids:
                locality_ids[loc_name] = loc_id

        # 2) BHK slices
        if not args.skip_slices:
            print("\n[2/4] BHK slices…")
            for bed in ["1", "2", "3", "4", "5"]:
                client.paginate(
                    label=f"bhk={bed}",
                    extra={"bedroom": bed},
                    max_pages=args.max_slice_pages,
                    sink=raw,
                    seen_ids=seen,
                )

            print("\n[2b/4] Budget slices…")
            budgets = [
                (0, 15000),
                (15000, 25000),
                (25000, 40000),
                (40000, 60000),
                (60000, 100000),
                (100000, 300000),
            ]
            for lo, hi in budgets:
                client.paginate(
                    label=f"budget={lo}-{hi}",
                    extra={"budgetMin": lo, "budgetMax": hi},
                    max_pages=args.max_slice_pages,
                    sink=raw,
                    seen_ids=seen,
                )

            # Alternate sorts open different windows of the 3k hard-cap
            for sort in ("price_l", "price_h"):
                client.paginate(
                    label=f"sort={sort}",
                    extra={"sortBy": sort},
                    max_pages=min(40, args.max_slice_pages),
                    sink=raw,
                    seen_ids=seen,
                )

        # Refresh locality id map
        for item in raw:
            loc_name = normalize_locality(
                item.get("locSeoName") or item.get("lmtDName")
            )
            loc_id = str(item.get("lt") or item.get("loc") or "").strip()
            if loc_name and loc_id:
                locality_ids[loc_name] = loc_id

        # 3) Deep scrape target localities
        if not args.skip_locality_deep:
            print("\n[3/4] Per-locality deep scrape…")
            for i, loc in enumerate(TARGET_LOCALITIES, 1):
                name = loc["name"]
                slug = loc["slug"]
                loc_id = locality_ids.get(name)

                # Try alias keys
                if not loc_id:
                    for k, v in locality_ids.items():
                        if k.lower() == name.lower():
                            loc_id = v
                            break

                if not loc_id:
                    print(f"  ({i}/{len(TARGET_LOCALITIES)}) {name}: resolving id…")
                    loc_id = resolve_locality_id_from_page(page, slug)
                    # Return to city page after navigation
                    try:
                        page.goto(CITY_PAGE, wait_until="domcontentloaded", timeout=60_000)
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass

                if not loc_id:
                    print(f"  ({i}/{len(TARGET_LOCALITIES)}) {name}: no id, skip")
                    continue

                locality_ids[name] = loc_id
                print(
                    f"  ({i}/{len(TARGET_LOCALITIES)}) {name} "
                    f"(id={loc_id})…"
                )
                client.paginate(
                    label=name,
                    extra={"localityName": loc_id},
                    max_pages=args.max_locality_pages,
                    sink=raw,
                    seen_ids=seen,
                )
        else:
            print("\n[3/4] Skipping locality deep scrape.")

        print(f"\n[4/4] Raw unique MagicBricks listings: {len(seen)}")
        browser.close()

    # stash locality map for summary
    scrape_magicbricks.locality_ids = locality_ids  # type: ignore[attr-defined]
    return raw


def build_summary(
    rows: list[dict[str, Any]],
    clean_stats: dict[str, Any],
    started: datetime,
    ended: datetime,
    notes: list[str],
) -> dict[str, Any]:
    by_locality = Counter(r.get("locality") or "Unknown" for r in rows)
    by_source = Counter(r.get("source") or "?" for r in rows)
    by_bhk = Counter(str(r.get("bhk") or "?") for r in rows)

    duration_sec = (ended - started).total_seconds()
    return {
        "generated_at": ended.isoformat(),
        "scrape_started_at": started.isoformat(),
        "scrape_duration_seconds": round(duration_sec, 1),
        "total_listings": len(rows),
        "final_dataset_size": len(rows),
        "listings_per_source": dict(by_source.most_common()),
        "listings_per_locality": dict(by_locality.most_common()),
        "locality_count": len(by_locality),
        "bhk_distribution": dict(sorted(by_bhk.items(), key=lambda x: x[0])),
        "duplicate_count_removed": clean_stats.get("duplicates_removed", 0),
        "dropped_invalid_rent": clean_stats.get("dropped_invalid_rent", 0),
        "dropped_missing_required": clean_stats.get("dropped_missing_required", 0),
        "raw_count_before_clean": clean_stats.get("raw_count", 0),
        "missing_value_statistics": missing_value_stats(rows),
        "rent_stats": _rent_stats(rows),
        "notes": notes,
        "target_localities_configured": len(TARGET_LOCALITIES),
    }


def _rent_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rents = sorted(r["rent"] for r in rows if isinstance(r.get("rent"), int))
    if not rents:
        return {}
    n = len(rents)
    return {
        "min": rents[0],
        "max": rents[-1],
        "median": rents[n // 2],
        "p10": rents[n // 10],
        "p90": rents[(9 * n) // 10],
        "mean": int(sum(rents) / n),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bengaluru rental dataset generator")
    p.add_argument("--max-city-pages", type=int, default=120)
    p.add_argument("--max-slice-pages", type=int, default=50)
    p.add_argument("--max-locality-pages", type=int, default=12)
    p.add_argument("--skip-locality-deep", action="store_true")
    p.add_argument("--skip-slices", action="store_true")
    p.add_argument("--pause", type=float, default=0.3, help="Delay between API calls")
    p.add_argument("--headed", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    notes: list[str] = [
        "Primary source: MagicBricks propertySearch JSON.",
        "Housing.com / 99acres skipped when blocked by anti-bot.",
    ]
    started = datetime.now(timezone.utc)
    print("=" * 60)
    print("AQI Sentinel · Citizen Mode · Bengaluru Rent Dataset")
    print("=" * 60)

    try:
        raw = scrape_magicbricks(args)
    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        return 1

    if not raw:
        print("No listings collected.", file=sys.stderr)
        return 2

    print(f"\nCleaning {len(raw)} raw records…")
    rows, clean_stats = clean_dataset(raw)
    ended = datetime.now(timezone.utc)

    summary = build_summary(rows, clean_stats, started, ended, notes)
    # attach learned locality ids if present
    loc_ids = getattr(scrape_magicbricks, "locality_ids", None)
    if loc_ids:
        summary["magicbricks_locality_ids_learned"] = len(loc_ids)

    write_outputs(rows, summary)

    print("\nSummary")
    print(f"  Final listings : {summary['total_listings']}")
    print(f"  Localities     : {summary['locality_count']}")
    print(f"  Sources        : {summary['listings_per_source']}")
    print(f"  Duration       : {summary['scrape_duration_seconds']}s")
    if summary.get("rent_stats"):
        rs = summary["rent_stats"]
        print(
            f"  Rent INR       : min {rs['min']:,} · median {rs['median']:,} "
            f"· max {rs['max']:,}"
        )
    print(f"  Top localities : {list(summary['listings_per_locality'].items())[:12]}")

    if summary["total_listings"] < 3000:
        print(
            "\nWARNING: under 3000 listings. Re-run without --skip flags "
            "or increase page limits.",
            file=sys.stderr,
        )
        return 3

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
