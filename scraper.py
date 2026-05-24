import json, time, os, re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

BASE = "https://nbl1.com.au"
CONFERENCES = ["north", "east", "south", "west", "central"]
SEASON = 2026

os.makedirs("data", exist_ok=True)

def scrape():
    dataset = {"season": SEASON, "summary": {}, "games": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (compatible; NBL1Research/1.0)"
        )
        page = ctx.new_page()

        # 1) Collect game URLs from each conference fixtures page
        game_urls = []
        for conf in CONFERENCES:
            url = f"{BASE}/fixtures/{conf}"
            print(f"Loading {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)
                html = page.content()
                links = set(re.findall(r'/games/(\d+)', html))
                dataset["summary"][conf] = len(links)
                for gid in links:
                    game_urls.append({"id": gid, "conf": conf})
                print(f"  {conf}: {len(links)} games")
            except Exception as e:
                print(f"  ERR {conf}: {e}")
                dataset["summary"][conf] = 0

        # 2) Visit each game page and grab box score tables
        for i, g in enumerate(game_urls, 1):
            url = f"{BASE}/games/{g['id']}"
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(2)
                soup = BeautifulSoup(page.content(), "lxml")

                title = soup.title.get_text(strip=True) if soup.title else ""
                tables = []
                for tbl in soup.select("table"):
                    headers = [th.get_text(strip=True) for th in tbl.select("th")]
                    rows = []
                    for tr in tbl.select("tbody tr, tr"):
                        cells = [td.get_text(strip=True) for td in tr.select("td")]
                        if cells:
                            rows.append(cells)
                    if rows:
                        tables.append({"headers": headers, "rows": rows})

                dataset["games"].append({
                    "game_id": g["id"],
                    "conference": g["conf"],
                    "title": title,
                    "tables": tables
                })
                print(f"  [{i}/{len(game_urls)}] {g['id']} - {len(tables)} tables")
            except Exception as e:
                print(f"  ERR game {g['id']}: {e}")

        browser.close()

    dataset["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("data/boxscores.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    print(f"Saved {len(dataset['games'])} games to data/boxscores.json")

if __name__ == "__main__":
    scrape()
