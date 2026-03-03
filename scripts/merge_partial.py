#!/usr/bin/env python3
"""
Merge partial refresh data into existing summary.json.

When the daily Action only refreshes 2026, we need to preserve the existing
2024 and 2025 data. This script merges the fresh output into the existing file.
"""

import json
import os
import sys

SUMMARY_PATH = "data/summary.json"
BACKUP_PATH = "data/summary.backup.json"

def main():
    if not os.path.exists(SUMMARY_PATH):
        print("No summary.json found — nothing to merge.")
        return

    # Read current (just-written) data
    with open(SUMMARY_PATH) as f:
        new_data = json.load(f)

    # Check if backup exists (previous full data)
    if not os.path.exists(BACKUP_PATH):
        # First run or full refresh — save as backup and exit
        with open(BACKUP_PATH, "w") as f:
            json.dump(new_data, f, indent=2)
        print("Saved backup. No merge needed.")
        return

    # Read previous full data
    with open(BACKUP_PATH) as f:
        old_data = json.load(f)

    new_years = new_data.get("years", {})
    old_years = old_data.get("years", {})

    # Merge: new data takes precedence, fill in missing years from old
    merged_years = {}
    all_year_keys = set(list(new_years.keys()) + list(old_years.keys()))

    for year in sorted(all_year_keys):
        if year in new_years:
            merged_years[year] = new_years[year]
        elif year in old_years:
            merged_years[year] = old_years[year]
            print(f"  Preserved existing {year} data from backup")

    # Write merged result
    merged = {
        "generatedAt": new_data["generatedAt"],
        "years": merged_years,
    }

    with open(SUMMARY_PATH, "w") as f:
        json.dump(merged, f, indent=2)

    # Update backup
    with open(BACKUP_PATH, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"Merged data: {', '.join(sorted(merged_years.keys()))}")


if __name__ == "__main__":
    main()
