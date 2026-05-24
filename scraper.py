import json, time, os, re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE = "https://nbl1.com.au"
CONFERENCES = ["north", "east", "south", "west", "central"]
SEASON = 2026
MAX_ROUNDS = 25   # NBL1 seasons are ~14-22 rounds; we'll try up to 25 to be safe

os.makedirs("data", exist_ok=True)

def harvest_game_ids(page):
    """Extract every /games/{id} link visible in the current page."""
    html = page.content()
    return set(re.findall(r'/games/([a-zA-Z0-9\-]+)', html))

def scrape():
    dataset = {"season": SEASON, "summary": {}, "games": []}
    all_game_ids = {}   # game_id -> conference

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        page = ctx.new_page()

        for conf in CONFERENCES:
            url = f"{BASE}/fixtures/{conf}"
            print(f"\n=== Loading {url} ===")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"  goto failed: {e}")
                dataset["summary"][conf] = 0
                continue

            # Give the JS app time to mount and fetch fixtures
            page.wait_for_timeout(8000)

            # Scroll to trigger any lazy-loading
            for _ in range(6):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(800)

            ids_here = harvest_game_ids(page)
            print(f"  Round 1 visible: {len(ids_here)} game links")

            # Try clicking through rounds by manipulating the round dropdown / buttons
            # Many NBL1 pages have round selectors; we click each and harvest
            for rnd in range(1, MAX_ROUNDS + 1):
                try:
                    # Try multiple selectors that might match a round button
                    selectors = [
                        f'button:has-text("Round {rnd}")',
                        f'text="Round {rnd}"',
                        f'[data-round="{rnd}"]',
                    ]
                    clicked = False
                    for sel in selectors:
                        try:
                            el = page.locator(sel).first
                            if el.count() > 0:
                                el.click(timeout=3000)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if clicked:
                        page.wait_for_timeout(2500)
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(800)
                        new_ids = harvest_game_ids(page)
                        added = new_ids - ids_here
                        if added:
                            print(f"  Round {rnd}: +{len(added)} games")
                        ids_here |= new_ids
                except Exception:
                    pass

            for gid in ids_here:
                all_game_ids[gid] = conf
            dataset["summary"][conf] = len(ids_here)
            print(f"  TOTAL {conf}: {len(ids_here)} unique games")

        # Now visit each game page
        print(f"\n=== Scraping {len(all_game_ids)} game pages ===")
        for i, (gid, conf) in enumerate(all_game_ids.items(), 1):
            url = f"{BASE}/games/{gid}"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(6000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)
                soup = BeautifulSoup(page.content(), "lxml")

                title = soup.title.get_text(strip=True) if soup.title else ""
                tables = []
                for tbl in soup.select("table"):
                    headers = [th.get_text(strip=True) for th in tbl.select("th")]
                    rows = []
                    for tr in tbl.select("tbody tr, tr"):
                        cells = [td.get_text(strip=True) for td in tr.select("td")]
                        if cells and any(c.strip() for c in cells):
                            rows.append(cells)
                    if rows:
                        tables.append({"headers": headers, "rows": rows})

                dataset["games"].append({
                    "game_id": gid,
                    "conference": conf,
                    "url": url,
                    "title": title,
                    "tables": tables
                })
                if i % 10 == 0 or i <= 5:
                    print(f"  [{i}/{len(all_game_ids)}] {gid} - {len(tables)} tables")
            except Exception as e:
                print(f"  ERR game {gid}: {e}")

        browser.close()

    dataset["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("data/boxscores.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"\nSaved {len(dataset['games'])} games to data/boxscores.json")

if __name__ == "__main__":
    scrape()
