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
from datetime import datetime, date, timezone
from collections import Counter
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


def normalize_route(field_data):
    """Extract and normalize route from fieldData using label matching."""
    reg_option = None
    route_label = None

    for field in field_data:
        if field.get("path") == "registrationOptions":
            reg_option = field.get("value", "")
        if field.get("path", "").startswith("registrationOptions.") and field.get("label"):
            route_label = field.get("label", "").strip()

    # Match by label — ORDER MATTERS (specific before generic)
    if route_label:
        lu = route_label.upper()
        if "DOUBLE METRIC" in lu:
            return "Double Metric 127"
        if "METRIC CENTURY" in lu:
            return "Metric Century 64"
        if "COMPACT CLASSIC" in lu:
            return "Metric Century 64"
        if "MOUNT TAM" in lu or "MT TAM" in lu or "MT. TAM" in lu:
            return "Mt Tam 93"
        if "GERONIMO" in lu:
            return "Geronimo 37"
        if "CLASSIC CENTURY" in lu:
            return "Century 100"
        if "CENTURY" in lu:
            return "Century 100"
        if "METRIC" in lu:
            return "Metric Century 64"
        if "CLOTHING" in lu:
            return "Clothing Only"

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
        time.sleep(0.2)

    return all_registrants


def compute_metrics(riders, all_completed, year):
    """Compute all metrics for a list of riders. Used for both full-year and YTD."""
    total_riders = len(riders)
    if total_riders == 0:
        return {
            "totalRiders": 0, "totalRevenue": 0, "avgOrder": 0,
            "routes": {}, "coupons": {"totalUsed": 0, "codes": {}},
            "gender": {"male": 0, "female": 0, "other": 0, "pctMale": 0},
            "avgAge": None,
            "food": {"noPreference": 0, "vegetarian": 0, "vegan": 0, "glutenFree": 0},
            "clothing": {"jersey": {"units": 0}, "bibs": {"units": 0}, "shorts": {"units": 0}, "socks": {"units": 0}, "totalExSocks": 0},
            "membership": {"newMembers": 0},
            "geography": {"topCities": [], "otherCA": 0, "nonCAStates": {}, "totalCA": 0},
            "ebike": 0,
        }

    # Routes
    route_counts = Counter()
    for r in riders:
        route = normalize_route(r.get("fieldData", []))
        route_counts[route] += 1

    # Revenue
    total_revenue = sum(float(r.get("amount", 0)) for r in riders)
    avg_order = round(total_revenue / total_riders, 2)

    # Coupons
    coupon_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        code = get_field(fd, "couponCode", "")
        if code and code.strip():
            coupon_counts[code.strip().upper()] += 1

    # Gender
    gender_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        gender = get_field(fd, "gender2", "unknown")
        if gender:
            gender_counts[gender.lower()] += 1
    gender_total = sum(gender_counts.values())

    # Age
    ages = []
    event_date = date(int(year), 8, 1)
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

    # Food
    food_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        food = get_field(fd, "afterRideFoodPreference", "unknown")
        if food:
            food_counts[food.lower()] += 1
    food_total = sum(food_counts.values())

    # Clothing (from all_completed, filtered to same date range)
    jersey_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "tshirtSize2"))
    bibs_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "marinCenturyBibs"))
    shorts_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "marinCenturyShorts"))
    socks_count = sum(1 for r in all_completed if has_field_selection(r.get("fieldData", []), "socks"))
    clothing_units = jersey_count + bibs_count + shorts_count

    # Membership
    membership_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        mem = get_field(fd, "membership", "unknown")
        if mem:
            membership_counts[mem.lower()] += 1
    new_members = sum(v for k, v in membership_counts.items()
                      if "nothank" not in k.replace(" ", "").replace("_", "")
                      and "already" not in k.lower())

    # Geography
    city_counts = Counter()
    state_counts = Counter()
    for r in riders:
        fd = r.get("fieldData", [])
        city = get_field(fd, "address.city", "")
        state = get_field(fd, "address.state", "")
        if city and state:
            city_clean = city.strip().title()
            state_clean = state.strip().upper()
            city_counts[f"{city_clean}, {state_clean}"] += 1
            state_counts[state_clean] += 1

    top_cities = city_counts.most_common(20)
    ca_total = sum(v for k, v in city_counts.items() if k.endswith(", CA"))
    top_ca = sum(v for k, v in top_cities if k.endswith(", CA"))
    other_ca = ca_total - top_ca
    non_ca_states = Counter()
    for k, v in state_counts.items():
        if k != "CA":
            non_ca_states[k] += v

    # Ebike
    ebike_count = sum(1 for r in riders if has_field_selection(r.get("fieldData", []), "willYouBeRiding2"))

    return {
        "totalRiders": total_riders,
        "totalRevenue": round(total_revenue, 2),
        "avgOrder": avg_order,
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
        },
        "clothing": {
            "jersey": {"units": jersey_count},
            "bibs": {"units": bibs_count},
            "shorts": {"units": shorts_count},
            "socks": {"units": socks_count},
            "totalExSocks": clothing_units,
        },
        "membership": {"newMembers": new_members},
        "geography": {
            "topCities": [{"city": k, "riders": v} for k, v in top_cities],
            "otherCA": other_ca,
            "nonCAStates": {k: v for k, v in non_ca_states.most_common()},
            "totalCA": ca_total,
        },
        "ebike": ebike_count,
    }


def aggregate_year(registrants, year):
    """Aggregate registrant data into full-year + YTD summary stats."""
    # Filter to completed/pending, split riders vs clothing-only
    completed = [r for r in registrants if r.get("status") in ("completed", "pending")]
    riders = [r for r in completed if normalize_route(r.get("fieldData", [])) != "Clothing Only"]
    clothing_only = [r for r in completed if normalize_route(r.get("fieldData", [])) == "Clothing Only"]

    # --- Daily cumulative (riders only) ---
    daily_counts = Counter()
    daily_revenue = Counter()
    for r in riders:
        dt = r.get("dateCreated", "")[:10]
        if dt:
            daily_counts[dt] += 1
            try:
                daily_revenue[dt] += float(r.get("amount", 0))
            except (ValueError, TypeError):
                pass

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

    # --- Full-year metrics ---
    full_metrics = compute_metrics(riders, completed, year)

    # --- YTD snapshot (registrants created on or before today's MM-DD in that year) ---
    today_mmdd = datetime.now(timezone.utc).strftime("%m-%d")
    ytd_cutoff = f"{year}-{today_mmdd}"
    ytd_riders = [r for r in riders if (r.get("dateCreated", "") or "")[:10] <= ytd_cutoff]
    ytd_completed = [r for r in completed if (r.get("dateCreated", "") or "")[:10] <= ytd_cutoff]
    ytd_metrics = compute_metrics(ytd_riders, ytd_completed, year)

    # --- Build output ---
    result = {
        "year": year,
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "totalRiders": full_metrics["totalRiders"],
        "totalRevenue": full_metrics["totalRevenue"],
        "avgOrder": full_metrics["avgOrder"],
        "totalCanceled": sum(1 for r in registrants if r.get("status") == "canceled"),
        "clothingOnlyPurchases": len(clothing_only),
        "cumulative": cumulative,
        "routes": full_metrics["routes"],
        "coupons": full_metrics["coupons"],
        "gender": full_metrics["gender"],
        "avgAge": full_metrics["avgAge"],
        "food": full_metrics["food"],
        "clothing": full_metrics["clothing"],
        "membership": full_metrics["membership"],
        "geography": full_metrics["geography"],
        "ebike": full_metrics["ebike"],
        # YTD snapshot — same metrics computed for registrants through today's date
        "ytd": ytd_metrics,
    }
    return result


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
        ytd = summary[year]['ytd']
        print(f"  YTD riders: {ytd['totalRiders']}, YTD revenue: ${ytd['totalRevenue']:,.2f}")

    # Write output
    output = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "years": summary,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Summary written to {args.output}")
    print(f"   Generated at: {output['generatedAt']}")
    for year, data in summary.items():
        print(f"   {year}: {data['totalRiders']} riders (YTD: {data['ytd']['totalRiders']}), ${data['totalRevenue']:,.2f} revenue")


if __name__ == "__main__":
    main()
