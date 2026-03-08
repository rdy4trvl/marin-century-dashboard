# Marin Century Registration Dashboard

Live dashboard tracking 2024–2026 Marin Century registrations via the Webconnex/RedPodium API. Auto-updates daily at 6 AM PT via GitHub Actions.

## Quick Preview

Open `index.html` in a browser — sample data is pre-loaded in `data/summary.json`.



### Update Index file
2. download Index file to PC
3. on github go to <> Code, open Index file, hit pencil, CTRL A, CTRL X to delete
4. on PC open Notepad and find and open Index (search all file types to display) CTRL A, CTRL C to copy
5. Back on Github, CTRL V to past new code, Commit Changes button
6. ON PC Ctrl+Shift+R to reload dashboard
7. https://rdy4trvl.github.io/marin-century-dashboard/

### Update BAT file
1.Downloads/marin-century-dashboar/marin-century-dashboard/refresh-dashboar.bat
2. double click .bat file

### Update 
1.

---

## Setup (15 minutes)

### 1. Create GitHub Repository

1. Go to https://github.com/new
2. Name: `marin-century-dashboard`
3. Set to **Private** (dashboard has aggregate data only, but no reason to be public)
4. **Do NOT** initialize with README (we'll push our files)

### 2. Push Files

```bash
cd marin-century-dashboard
git init
git add .
git commit -m "Initial dashboard setup"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/marin-century-dashboard.git
git push -u origin main
```

### 3. Add API Key as GitHub Secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `REDPODIUM_API_KEY`
4. Value: Your Webconnex API key
5. Click **Add secret**

### 4. Enable GitHub Pages

1. Go to **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Click **Save**
5. Your dashboard will be at: `https://YOUR_USERNAME.github.io/marin-century-dashboard/`

### 5. Run First Data Refresh

1. Go to **Actions** tab
2. Click **Update Marin Century Dashboard Data**
3. Click **Run workflow**
4. Set years to: `2024,2025,2026`
5. Click **Run workflow** (green button)
6. Wait 2-3 minutes for it to complete
7. Refresh your dashboard — real data!

### 6. Regenerate API Key

Since the key was used in this chat, regenerate it:
1. RedPodium → **Extras** → **Integrations**
2. Revoke old key, generate new one
3. Update the GitHub Secret with the new key

---

## How It Works

```
                    ┌─────────────────┐
  6 AM PT daily     │  GitHub Action   │
  ─────────────────>│  runs Python     │
                    │  aggregate.py    │
                    └────────┬────────┘
                             │ Calls Webconnex API
                             │ for formId 962178 (2026)
                             ▼
                    ┌─────────────────┐
                    │  Aggregates to   │
                    │  summary.json    │──> NO PII
                    │  (counts only)   │    (just totals,
                    └────────┬────────┘     routes, cities)
                             │
                             │ git commit + push
                             ▼
                    ┌─────────────────┐
                    │  GitHub Pages    │
                    │  serves HTML +   │
                    │  summary.json    │
                    └─────────────────┘
```

### Schedule
- **Daily (Tue-Sun)**: Refreshes 2026 only (~30 seconds)
- **Mondays**: Full refresh of 2024 + 2025 + 2026 (~2 minutes)
- **Manual**: Run anytime from Actions tab with custom year selection

### Privacy
- API key stored as encrypted GitHub Secret
- `summary.json` contains ONLY aggregate counts
- No names, emails, phone numbers, or individual data anywhere
- Repository can be private

---

## File Structure

```
marin-century-dashboard/
├── .github/
│   └── workflows/
│       └── update-data.yml    # GitHub Action (daily refresh)
├── scripts/
│   ├── aggregate.py           # API fetcher + data aggregator
│   └── merge_partial.py       # Merges partial refreshes
├── data/
│   └── summary.json           # Aggregated dashboard data (auto-updated)
├── index.html                 # Dashboard (single-file, no build step)
└── README.md
```

---

## Form IDs

| Year | Form ID | Form Name |
|------|---------|-----------|
| 2026 | 962178  | 2026 Marin Century |
| 2025 | 799166  | 2025 Marin Century |
| 2024 | 703821  | 2024 Marin Century |
| 2023 | 555077  | 2023 Marin Century |

---

## Running Locally

```bash
# First run — fetch all years
export REDPODIUM_API_KEY=your_key_here
python scripts/aggregate.py --years 2024,2025,2026

# Quick refresh — 2026 only
python scripts/aggregate.py --years 2026

# Serve dashboard locally
python -m http.server 8000
# Open http://localhost:8000
```

---

## Troubleshooting

**Action fails with "No API key"**
→ Check that the secret is named exactly `REDPODIUM_API_KEY` in repo settings

**Data looks stale**
→ Check Actions tab for failed runs; manually trigger a run

**Rider counts don't match RedPodium dashboard**
→ The script filters to `status: completed` and excludes clothing-only purchases. The RedPodium "Total Registrants" includes cancellations and clothing-only.

**Route shows as "Unknown"**
→ A new route label variant may need to be added to `ROUTE_LABEL_MAP` in aggregate.py
