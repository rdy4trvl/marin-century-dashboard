#!/usr/bin/env python3
"""
Marin Century Registration Dashboard — Data Aggregation Script

Calls the Webconnex/RedPodium API for 2024, 2025, and 2026 registration data,
aggregates into summary statistics, and outputs a clean JSON file with NO PII.

Usage:
    python aggregate.py                    # Uses REDPODIUM_API_KEY env variable
    python aggregate.py --api-key YOUR_KEY # Or pass key directly

Output: data/summary.json
"""

import json
import os
import sys
import argparse
import time
from datetime import datetime, date
from collections import defaultdict, Counter
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# --- CONFIGURATION ---
API_BASE = "https://api.webconnex.com/v2/public"
PRODUCT = "redpodium.com"
PAGE_LIMIT = 100

FORMS = {
    "2024": {"formId": 703821, "formName": "2024 Marin Century"},
    "2025": {"formId": 819622, "formName": "2025 Marin Century"},
    "2026": {"formId": 962178, "formName": "2026 Marin Century"},
}

# Route mapping: normalize the registrationOptions path values to display names
ROUTE_MAP = {
    # 2026 routes (from field path values)
    "traditionalCentury": None,       # need to read sub-label
    "metricCentury": None,            # need to read sub-label
    "mountTamChallenge": None,
    "doubleMetricCentury": None,
    "clothingPurchaseOnly": "CLOTHING_ONLY",
}

# Canonical route names from sub-labels
ROUTE_LABEL_MAP = {
    # 2025/2026 route labels
    "CENTURY": "Century 100",
    "METRIC CENTURY": "Metric Century 64",
    "METRIC": "Metric Century 64",
    "GERONIMO": "Geronimo 37",
    "MOUNT TAM": "Mt Tam 93",
    "MT. TAM": "Mt Tam 93",
    "DOUBLE METRIC": "Double Metric 127",
    "CLOTHING ONLY": "Clothing Only",
    # 2024 route labels (only 3 routes existed)
    "COMPACT CLASSIC": "Metric Century 64",
    "CLASSIC CENTURY": "Century 100",
    "MT TAM CENTURY": "Mt Tam 93",
    "MT. TAM CENTURY": "Mt Tam 93",
}

def normalize_route(field_data):
    """Extract and normalize route from fieldData."""
    reg_option = None
    route_label = None

    for field in field_data:
        if field.get("path") == "registrationOptions":
            reg_option = field.get("value", "")
        if field.get("path", "").startswith("registrationOptions.") and field.get("label"):
            route_label = field.get("label", "").strip()

    if reg_option == "clothingPurchaseOnly":
        return "Clothing Only"

    if route_label:
        label_upper = route_label.upper()
        for key, name in ROUTE_LABEL_MAP.items():
            if key in label_upper:
                return name

    return "Unknown"


def get_field(field_data, path, default=None):
    """Get a field value from fieldData by path."""
    for field in field_data:
        if field.get("path") == path:
            return field.get("value", default)
    return default


def get_field_amount(field_data, path_prefix):
    """Get the amount from a sub-field (e.g., clothing item selected)."""
    for field in field_data:
        p = field.get("path", "")
        if p.startswith(path_prefix + ".") and field.get("amount"):
            try:
                return float(field["amount"])
            except (ValueError, TypeError):
                return 0
    return 0


def has_field_selection(field_data, path):
    """Check if a field has any selection (non-empty sub-value)."""
    for field in field_data:
        if field.get("path", "").startswith(path + ".") and field.get("value") == "true":
            return True
    return False


def get_clothing_label(field_data, path):
    """Get the selected label for a clothing item."""
    for field in field_data:
        if field.get("path", "").startswith(path + ".") and field.get("value") == "true":
            return field.get("label", "")
    return None


def fetch_registrants(api_key, form_id, limit=PAGE_LIMIT):
    """Fetch all registrants for a form, handling pagination."""
    all_registrants = []
    starting_after = 0
    page = 0

    while True:
        url = (
            f"{API_BASE}/search/registrants"
            f"?product={PRODUCT}"
            f"&formId={form_id}"
            f"&limit={limit}"
        )
        if starting_after > 0:
            url += f"&startingAfter={starting_after}"
        
        req = Request(url, headers={"apiKey": api_key, "User-Agent": "Mozilla/5.0"})

        try:
            with urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except HTTPError as e:
            print(f"  HTTP Error {e.code}: {e.reason}")
            break
        except URLError as e:
            print(f"  URL Error: {e.reason}")
            break

        results = data.get("data", [])
        all_registrants.extend(results)
        page += 1

        total = data.get("totalResults", 0)
        has_more = data.get("hasMore", False)
        sa = data.get("startingAfter", 0)

        print(f"  Page {page}: got {len(results)} registrants (total so far: {len(all_registrants)}/{total})")

        if not has_more or not results:
            break

        starting_after = sa
        time.sleep(0.2)  # Be respectful of rate limits

    return all_registrants


def aggregate_year(registrants, year):
    """Aggregate registrant data into summary stats for one year."""
    # Filter to completed, non-clothing-only
    completed = [r for r in registrants if r.get("status") in ("completed", "pending")]
    all_completed = completed  # includes clothing-only for clothing stats

    riders = [r for r in completed if normalize_route(r.get("fieldData", [])) != "Clothing Only"]
    clothing_only = [r for r in completed if normalize_route(r.get("fieldData", [])) == "Clothing Only"]

    # --- Daily registration counts (riders only) ---
    daily_counts = Counter()
    daily_revenue = Counter()
    for r in riders:
        dt = r.get("dateCreated", "")[:10]  # YYYY-MM-DD
        if dt:
            daily_counts[dt] += 1
            try:
                daily_revenue[dt] += float(r.get("amount", 0))
            except (ValueError, TypeError):
                pass

    # Sort by date
    sorted_dates = sorted(daily_counts.keys())
    cumulative = []
    cum_riders = 0
    cum_revenue = 0
    for d in sorted_dates:
        cum_riders += daily_counts[d]
        cum_revenue += daily_revenue[d]
        cumulative.append({
            "date": d,
            "daily": daily_counts[d],
            "cumRiders": cum_riders,
            "dailyRevenue": round(daily_revenue[d], 2),
            "cumRevenue": round(cum_revenue, 2),
        })

    # --- Routes ---
    route_counts = Counter()
    for r in riders:
        route = normalize_route(r.get("fieldData", []))
        route_counts[route] += 1

    # --- Revenue ---
    total_revenue = sum(float(r.get("amount", 0)) for r in riders)
    avg_order = round(total_revenue / len(riders), 2) if riders else 0

    # --- Coupons ---
    coupon_counts = Counter()
    coupon_revenue = 0
    for r in riders:
        fd = r.get("fieldData", [])
        code = get_field(fd, "couponCode", "")
        if code and code.strip():
            coupon_counts[code.strip().upper()] += 1

    # --- Gender ---
    gender_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        gender = get_field(fd, "gender2", "unknown")
        if gender:
            gender_counts[gender.lower()] += 1

    # --- Age ---
    ages = []
    event_date = date(int(year), 8, 1)  # Aug 1 of event year
    for r in riders:
        fd = r.get("fieldData", [])
        dob = get_field(fd, "dateOfBirth")
        if dob:
            try:
                birth = datetime.strptime(dob[:10], "%Y-%m-%d").date()
                age = (event_date - birth).days / 365.25
                if 5 < age < 100:
                    ages.append(int(age))
            except (ValueError, TypeError):
                pass

    avg_age = round(sum(ages) / len(ages), 1) if ages else None

    # --- Food preference ---
    food_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        food = get_field(fd, "afterRideFoodPreference", "unknown")
        if food:
            food_counts[food.lower()] += 1

    # --- Clothing (all completed, including clothing-only) ---
    jersey_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "tshirtSize2"))
    bibs_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "marinCenturyBibs"))
    shorts_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "marinCenturyShorts"))
    socks_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "socks"))

    # Clothing revenue
    jersey_rev = sum(get_field_amount(r.get("fieldData", []), "tshirtSize2") for r in all_completed)
    bibs_rev = sum(get_field_amount(r.get("fieldData", []), "marinCenturyBibs") for r in all_completed)
    shorts_rev = sum(get_field_amount(r.get("fieldData", []), "marinCenturyShorts") for r in all_completed)
    socks_rev = sum(get_field_amount(r.get("fieldData", []), "socks") for r in all_completed)

    clothing_units = jersey_count + bibs_count + shorts_count  # ex-socks per dashboard spec

    # --- Tee shirts ---
    tshirt_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "tshirtSize5"))

    # --- Membership ---
    membership_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        mem = get_field(fd, "membership", "unknown")
        if mem:
            membership_counts[mem.lower()] += 1

    new_members = sum(v for k, v in membership_counts.items() if "nothank" not in k.replace(" ", "").replace("_", "") and "already" not in k.lower())

    # --- Geography (by zip → city, state) ---
    city_counts = Counter()
    state_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        zip_code = get_field(fd, "address.postalCode", "")
        city = get_field(fd, "address.city", "")
        state = get_field(fd, "address.state", "")
        country = get_field(fd, "address.country", "US")

        if city and state:
            city_clean = city.strip().title()
            state_clean = state.strip().upper()
            city_counts[f"{city_clean}, {state_clean}"] += 1
            state_counts[state_clean] += 1

    # Top 20 cities
    top_cities = city_counts.most_common(20)

    # Other CA
    ca_total = sum(v for k, v in city_counts.items() if k.endswith(", CA"))
    top_ca = sum(v for k, v in top_cities if k.endswith(", CA"))
    other_ca = ca_total - top_ca

    # Non-CA states
    non_ca_states = Counter()
    for k, v in state_counts.items():
        if k != "CA":
            non_ca_states[k] += v

    # --- Ebike ---
    ebike_count = sum(1 for r in riders if has_field_selection(r.get("fieldData", []), "willYouBeRiding2"))

    # --- Massage (2026 only) ---
    massage_count = 0
    for r in riders:
        fd = r.get("fieldData", [])
        massage = get_field(fd, "multipleChoice")
        if massage and "nothank" not in massage.replace(" ", "").replace("_", "").lower():
            massage_count += 1

    # --- Build summary ---
    total_riders = len(riders)
    food_total = sum(food_counts.values())
    gender_total = sum(gender_counts.values())

    return {
        "year": year,
        "lastUpdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totalRiders": total_riders,
        "totalRevenue": round(total_revenue, 2),
        "avgOrder": avg_order,
        "totalCanceled": sum(1 for r in registrants if r.get("status") == "canceled"),
        "clothingOnlyPurchases": len(clothing_only),
        "cumulative": cumulative,
        "routes": {k: v for k, v in sorted(route_counts.items(), key=lambda x: -x[1])},
        "coupons": {
            "totalUsed": sum(coupon_counts.values()),
            "codes": {k: v for k, v in coupon_counts.most_common(20)},
        },
        "gender": {
            "male": gender_counts.get("male", 0),
            "female": gender_counts.get("female", 0),
            "other": gender_counts.get("other", 0) + gender_counts.get("prefernottosay", 0) + gender_counts.get("prefer not to say", 0),
            "pctMale": round(gender_counts.get("male", 0) / gender_total * 100, 1) if gender_total else 0,
        },
        "avgAge": avg_age,
        "food": {
            "noPreference": round(food_counts.get("nopreferenceomnivore", 0) / food_total * 100, 1) if food_total else 0,
            "vegetarian": round(food_counts.get("vegetarian", 0) / food_total * 100, 1) if food_total else 0,
            "vegan": round(food_counts.get("vegan", 0) / food_total * 100, 1) if food_total else 0,
            "glutenFree": round(food_counts.get("glutenfree", 0) / food_total * 100, 1) if food_total else 0,
            "raw": dict(food_counts),
        },
        "clothing": {
            "jersey": {"units": jersey_count, "revenue": round(jersey_rev, 2)},
            "bibs": {"units": bibs_count, "revenue": round(bibs_rev, 2)},
            "shorts": {"units": shorts_count, "revenue": round(shorts_rev, 2)},
            "socks": {"units": socks_count, "revenue": round(socks_rev, 2)},
            "totalExSocks": clothing_units,
            "totalRevenue": round(jersey_rev + bibs_rev + shorts_rev + socks_rev, 2),
        },
        "tshirts": tshirt_count,
        "membership": {
            "newMembers": new_members,
            "raw": dict(membership_counts),
        },
        "geography": {
            "topCities": [{"city": k, "riders": v} for k, v in top_cities],
            "otherCA": other_ca,
            "nonCAStates": {k: v for k, v in non_ca_states.most_common()},
            "totalCA": ca_total,
        },
        "ebike": ebike_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Aggregate Marin Century registration data")
    parser.add_argument("--api-key", help="Webconnex API key (or set REDPODIUM_API_KEY env)")
    parser.add_argument("--output", default="data/summary.json", help="Output JSON path")
    parser.add_argument("--years", default="2024,2025,2026", help="Comma-separated years to fetch")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("REDPODIUM_API_KEY")
    if not api_key:
        print("ERROR: No API key provided. Use --api-key or set REDPODIUM_API_KEY env variable.")
        sys.exit(1)

    years = [y.strip() for y in args.years.split(",")]
    summary = {}

    for year in years:
        if year not in FORMS:
            print(f"WARNING: No form config for {year}, skipping.")
            continue

        form = FORMS[year]
        print(f"\n{'='*50}")
        print(f"Fetching {year} — Form ID: {form['formId']} ({form['formName']})")
        print(f"{'='*50}")

        registrants = fetch_registrants(api_key, form["formId"])
        print(f"  Total fetched: {len(registrants)}")

        summary[year] = aggregate_year(registrants, year)
        print(f"  Riders (completed, non-clothing): {summary[year]['totalRiders']}")
        print(f"  Revenue: ${summary[year]['totalRevenue']:,.2f}")
        print(f"  Routes: {summary[year]['routes']}")

    # Write output
    output = {
        "generatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "years": summary,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Summary written to {args.output}")
    print(f"   Generated at: {output['generatedAt']}")
    for year, data in summary.items():
        print(f"   {year}: {data['totalRiders']} riders, ${data['totalRevenue']:,.2f} revenue")


if __name__ == "__main__":
    main()
