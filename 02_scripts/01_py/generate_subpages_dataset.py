import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Determine the repository root based on the script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

INPUT_CSV = os.path.join(REPO_ROOT, "01_data", "top_1000_websites_tranco.csv")
OUTPUT_CSV = os.path.join(REPO_ROOT, "01_data", "websites_subpages.csv")
TARGET_COUNT = 20

# Load the dataset of 1000 sites
df = pd.read_csv(INPUT_CSV)

# Detect the domain column
col_domain = next((c for c in df.columns if c.lower() in ["domain", "url", "site", "website"]), df.columns[0])

# Stratification: evenly spaced sampling across the list
step = max(1, len(df) // (TARGET_COUNT * 3))
candidates = df.iloc[::step].to_dict('records')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

static_extensions = (".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".css", ".js", ".svg", ".webp", ".mp4")
validated = []

print(f"Looking for {TARGET_COUNT} sites with a valid subpage starting from:\n{INPUT_CSV}\n")

for row in candidates:
    if len(validated) >= TARGET_COUNT:
        break

    raw_domain = str(row[col_domain]).strip()
    if not raw_domain or raw_domain == "nan":
        continue

    base_url = raw_domain if raw_domain.startswith("http") else f"https://{raw_domain}"

    try:
        # 1. Test connectivity with the homepage
        res = requests.get(base_url, headers=headers, timeout=8, allow_redirects=True)
        if res.status_code != 200:
            continue

        content = res.text.lower()
        if "cf-browser-verification" in content or "just a moment..." in content or "captcha" in content:
            continue

        # 2. Parse the DOM looking for an internal subpage
        soup = BeautifulSoup(res.text, "html.parser")
        final_domain = urlparse(res.url).netloc
        chosen_subpage = None

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
                continue

            full_url = urljoin(res.url, href)
            parsed_url = urlparse(full_url)

            # Validate that it belongs to the same domain and is a non-static internal path
            if (parsed_url.netloc == final_domain and 
                len(parsed_url.path) > 1 and 
                parsed_url.scheme in ["http", "https"] and 
                not any(full_url.lower().endswith(ext) for ext in static_extensions)):

                # Check that the subpage responds with 200
                res_sub = requests.get(full_url, headers=headers, timeout=8, allow_redirects=True)
                if res_sub.status_code == 200:
                    chosen_subpage = full_url
                    break

        if chosen_subpage:
            record = {
                "domain": final_domain,
                "homepage_url": res.url,
                "subpage_url": chosen_subpage
            }
            for rank_col in ["rank", "tranco_rank", "Tranco_Rank"]:
                if rank_col in row:
                    record["tranco_rank"] = row[rank_col]
                    break

            validated.append(record)
            print(f"[{len(validated)}/{TARGET_COUNT}] {final_domain} -> {chosen_subpage}")

    except Exception:
        continue

# Save the resulting dataset in 01_data/
output_df = pd.DataFrame(validated)
output_df.to_csv(OUTPUT_CSV, index=False)
print(f"\nDataset completed successfully at:\n{OUTPUT_CSV}")
