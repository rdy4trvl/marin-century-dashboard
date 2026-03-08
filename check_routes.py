from urllib.request import Request, urlopen
import json
from collections import Counter

API_KEY = "5a9a057a8353407d9efce1cadf7aa8b1"
BASE = "https://api.webconnex.com/v2/public/search/registrants?product=redpodium.com"
headers = {"apiKey": API_KEY, "User-Agent": "Mozilla/5.0"}

for year, fid in [("2026", 962178)]:
    print(f"\n=== {year} (form {fid}) ===")
    all_regs = []
    sa = 0
    for _ in range(25):
        url = f"{BASE}&formId={fid}&limit=100"
        if sa > 0:
            url += f"&startingAfter={sa}"
        req = Request(url, headers=headers)
        data = json.loads(urlopen(req).read())
        all_regs.extend(data["data"])
        sa = data.get("startingAfter", 0)
        if not data.get("hasMore", False):
            break

    pairs = Counter()
    for r in all_regs:
        fd = r.get("fieldData", [])
        path_val = ""
        label = ""
        for f in fd:
            if f.get("path") == "registrationOptions":
                path_val = f.get("value", "")
            if f.get("path", "").startswith("registrationOptions.") and f.get("label"):
                label = f.get("label", "")
        pairs[(path_val, label)] += 1

    for (pv, lb), count in pairs.most_common():
        print(f"  {count:4d}  path={pv}  label={lb}")
