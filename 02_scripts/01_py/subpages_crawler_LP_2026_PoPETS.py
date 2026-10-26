import os
import sys
import time
import json
import csv
import shutil
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# --- BASE DIRECTORIES ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXTENSIONS_DIR = os.path.join(BASE_DIR, "01_data", "extensions")
RESULTS_DIR = os.path.join(BASE_DIR, "03_results")
SITES_FILE = os.path.join(BASE_DIR, "01_data", "websites_subpages_20.csv")

os.makedirs(RESULTS_DIR, exist_ok=True)

# --- EXTENSION CONFIGURATION ---
# Format: list of directory paths per test group
extensions = [
    # 0: Azerion Ad Expert + Super Agent (Baseline/Control)
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
    ],
    # 1: Stands Adblocker MV2
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "stands_adblocker_MV2", "lgblnfidahcdcjddiepkckcfdhpknnjh"),
    ],
    # 2: Fair Adblocker MV3
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "fair_adblocker_mv3_beta_MV3", "dpbilcifapcagighfgooemclcalgdhbh"),
    ],
    # 3: Adblock Plus MV2
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "adblock_plus_free_ad_blocker_3.25.1_MV2", "cfhdojbkjhnklbpkdaibdccddilifddb"),
    ],
    # 4: Adblock Plus MV3
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "adblock_plus_free_ad_blocker_4.5.1_MV3", "cfhdojbkjhnklbpkdaibdccddilifddb"),
    ],
    # 5: Adguard MV2
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "adguard_adblocker_MV2", "bgnkhhnnamicmpeenaelnjfhikgbkllg"),
    ],
    # 6: Adguard MV3
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "adguard_adblocker_mv3_beta_MV3", "apjcbfpjihpedihablmalmbbhjpklbdf"),
    ],
    # 7: uBlock Origin MV2
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "ublock_origin_MV2", "cjpalhdlnbpafiamejdnhcphjbkeiagm"),
    ],
    # 8: uBlock Origin Lite MV3
    [
        os.path.join(EXTENSIONS_DIR, "super_agent", "neooppigbkahgfdhbpbhcccgpimeaafi"),
        os.path.join(EXTENSIONS_DIR, "azerion", "nndadbimjipilgfojofhpjjkhgflkihc"),
        os.path.join(EXTENSIONS_DIR, "ublock_origin_lite_MV3", "ddkjiahejlhfcafbddmgiahcphecmpfh"),
    ],
]


def get_extension_group_label(group_paths):
    """Generates a clean string tag for filenames based on active extensions."""
    names = []
    for path in group_paths:
        norm = path.replace('\\', '/')
        seg = norm.split('/')
        if 'extensions' in seg:
            idx = seg.index('extensions')
            if idx + 1 < len(seg):
                names.append(seg[idx + 1])
    return "-".join(names) if names else "no-extension"


# Only blocks made by extensions (ad blockers) count. Chrome's own blocks
# (CSP, mixed content, CORP, ...) and inline data: URLs are ordinary page behaviour.
BLOCKED_ERRORS = ("ERR_BLOCKED_BY_CLIENT",)
EXTENSION_SCHEMES = ("chrome-extension://",)


def collect_network_requests(driver, page_url=""):
    """Extracts Network.requestWillBeSent records including initiator, plus a 'blocked'
    flag for requests an ad blocker stopped (failed with net::ERR_BLOCKED_BY_CLIENT,
    or redirected to a local extension placeholder), so they can be excluded later."""
    logs = driver.get_log('performance')
    requests = []
    last_hop = {}        # requestId -> index of the latest record for that request
    blocked_ids = set()  # requestIds that failed because a blocker stopped them
    for entry in logs:
        try:
            log_obj = json.loads(entry['message'])
            msg = log_obj.get('message', {})
            params = msg.get('params', {})
            if msg.get('method') == 'Network.loadingFailed':
                error = params.get('errorText', '') or ''
                if any(e in error for e in BLOCKED_ERRORS):
                    blocked_ids.add(params.get('requestId'))
            elif msg.get('method') == 'Network.requestWillBeSent':
                req = params.get('request', {})
                request_id = params.get('requestId')
                url = req.get('url', '')

                # A redirect to an extension placeholder means the previous hop was blocked
                if request_id in last_hop and url.startswith(EXTENSION_SCHEMES):
                    requests[last_hop[request_id]]['blocked'] = True

                # Extract initiator URL for R's first-party vs third-party calculation
                initiator_obj = params.get('initiator', {})
                initiator_url = initiator_obj.get('url', '')
                if not initiator_url:
                    # If initiated by script stack trace
                    stack = initiator_obj.get('stack', {})
                    call_frames = stack.get('callFrames', [])
                    if call_frames and call_frames[0].get('url'):
                        initiator_url = call_frames[0].get('url')
                    else:
                        # Fallback to the main page url
                        initiator_url = page_url

                requests.append({
                    'timestamp': params.get('wallTime', time.time()),
                    'method': req.get('method', ''),
                    'type': params.get('type', 'Other'),
                    'url': url,
                    'initiator': initiator_url,
                    # placeholder hops served by the extension never left the browser
                    'blocked': url.startswith(EXTENSION_SCHEMES),
                })
                last_hop[request_id] = len(requests) - 1
        except Exception:
            continue

    # Only the last hop of a blocked request was stopped; earlier redirect hops went out
    for request_id in blocked_ids:
        if request_id in last_hop:
            requests[last_hop[request_id]]['blocked'] = True
    return requests

def export_network_csv(filepath, requests_data):
    """Writes captured network requests into a CSV file with headers expected by R."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        # Note the added 'initiator' column:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'method', 'type', 'url', 'initiator', 'blocked'])
        writer.writeheader()
        writer.writerows(requests_data)
    n_blocked = sum(1 for r in requests_data if r.get('blocked'))
    print(f"  [SAVED] {os.path.basename(filepath)} "
          f"({len(requests_data)} requests recorded, {n_blocked} blocked)")
def crawl_site(driver, base_domain, home_url, sub_url, ext_tag):
    """Visits homepage and subpage, capturing and exporting network traffic for each."""
    safe_domain = base_domain.replace('.', '').replace('/', '').replace(':', '')

    # --- 1. HOMEPAGE ---
    home_file = os.path.join(RESULTS_DIR, f"homepage-{safe_domain}-{ext_tag}-ads.csv")
    if not os.path.exists(home_file):
        print(f"\n[HOMEPAGE] Navigating to: {home_url}")
        try:
            # Drain residual logs prior to navigation
            driver.get_log('performance')
            try:
                driver.get(home_url)
            except TimeoutException:
                pass
            time.sleep(6)  # Allow ad scripts to execute and send requests
            home_reqs = collect_network_requests(driver, page_url=home_url)
            export_network_csv(home_file, home_reqs)
        except Exception as e:
            print(f"  [ERROR] Failed to crawl homepage {home_url}: {e}")
    else:
        print(f"  [SKIP] {os.path.basename(home_file)} already exists.")

    # # --- 2. SUBPAGE ---
    if sub_url and sub_url.strip():
         sub_file = os.path.join(RESULTS_DIR, f"subpage-{safe_domain}-{ext_tag}-ads.csv")
         if not os.path.exists(sub_file):
            print(f"\n[SUBPAGE] Navigating to: {sub_url}")
            try:
                 # Drain residual logs prior to subpage navigation
                 driver.get_log('performance')
                 try:
                    driver.get(sub_url)
                 except TimeoutException:
                    pass
                 time.sleep(6)
                 sub_reqs = collect_network_requests(driver, page_url=sub_url)
                 export_network_csv(sub_file, sub_reqs)
            except Exception as e:
                print(f"  [ERROR] Failed to crawl subpage {sub_url}: {e}")
         else:
             print(f"  [SKIP] {os.path.basename(sub_file)} already exists.")


def create_driver(extension_paths):
    """Initializes Chrome with specified extensions and performance logging enabled."""
    opts = Options()
    opts.browser_version = "136"
    opts.add_argument(
    "--disable-features=ExtensionManifestV2Disabled,ExtensionManifestV2Unsupported,"
    "ExtensionManifestV2DeprecationWarning,ExtensionManifestV2DisabledByUserCanReEnable"
    )
    # Filter out http-recorder if present
    active_paths = [p.replace('\\', '/') for p in extension_paths if 'http-recorder' not in p and os.path.exists(p)]
    
    if active_paths:
        ext_arg = ",".join(active_paths)
        opts.add_argument(f"--load-extension={ext_arg}")

    # Standard headless-compatible switches and stability flags
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-features=ExtensionManifestV2Deprecation,ExtensionManifestV2UnsupportedWarning")

    # Native performance logging for HTTP/HTTPS network interception
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(100)
    return driver


def load_sites(file_path):
    """Carga los pares de URLs desde un archivo CSV descartando la cabecera."""
    if not os.path.exists(file_path):
        print(f"[ERROR] Archivo no encontrado: {file_path}")
        return []

    targets = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not any(row):
                continue
            
            # Limpiar espacios en blanco de cada celda
            row = [cell.strip() for cell in row]
            
            # Saltar comentarios o fila de cabecera
            if row[0].startswith('#') or row[0].lower() in ['domain', 'domain_url', 'site']:
                continue
            
            if len(row) >= 3:
                domain = row[0]
                home_url = row[1]
                sub_url = row[2]
                targets.append((domain, home_url, sub_url))
            elif len(row) == 2:
                domain = row[0].replace('https://', '').replace('http://', '').strip('/')
                targets.append((domain, row[0], row[1]))
            elif len(row) == 1:
                targets.append((row[0], row[0], ""))
                
    return targets


def main():
    print("=== STARTING SUBPAGES CRAWLER (CDP PERFORMANCE ENGINE) ===")
    
    targets = load_sites(SITES_FILE)
    targets = targets[:6]
    if not targets:
        # Fallback to test domain if sites file is empty
        print("[INFO] No sites found in file. Using default target for demonstration.")
        targets = [("www.americanthinker.com", "https://www.americanthinker.com/", "https://www.americanthinker.com/search/")]

    for group_idx, ext_group in enumerate(extensions):
        ext_tag = get_extension_group_label(ext_group)
        print(f"\n========================================================")
        print(f"RUNNING EXTENSION GROUP [{group_idx}]: {ext_tag}")
        print(f"========================================================")

        driver = None
        try:
            driver = create_driver(ext_group)
            for domain, home_url, sub_url in targets:
                crawl_site(driver, domain, home_url, sub_url, ext_tag)
        except Exception as e:
            print(f"[FATAL] Error running extension group {ext_tag}: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    print("\n=== ALL CRAWL RUNS COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()