import os
import sys
import time
import json
import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from subpages_crawler_LP_2026_PoPETS import extensions

# 1. Extension configuration (blockers only, excluding http-recorder)
active_extensions = [p.replace('\\', '/') for p in extensions[7] if 'http-recorder' not in p]

print("=== INICIANDO PRUEBA RÁPIDA (CHROME PERFORMANCE LOGGING) ===")
print(f"Extensiones de bloqueo cargadas: {len(active_extensions)}")

opts = Options()
if active_extensions:
    opts.add_argument(f"--load-extension={','.join(active_extensions)}")

# Enable Performance Logging for Network capture
opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

driver = webdriver.Chrome(options=opts)

def collect_network_requests():
    """Extracts Network.requestWillBeSent events from Chrome's performance log."""
    logs = driver.get_log('performance')
    requests = []
    for entry in logs:
        try:
            log_obj = json.loads(entry['message'])
            message = log_obj.get('message', {})
            method = message.get('method', '')
            
            if method == 'Network.requestWillBeSent':
                params = message.get('params', {})
                req = params.get('request', {})
                requests.append({
                    'timestamp': params.get('wallTime', time.time()),
                    'method': req.get('method', ''),
                    'type': params.get('type', 'Other'),
                    'url': req.get('url', '')
                })
        except Exception:
            continue
    return requests

def export_network_csv(filename, requests_data):
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "03_results"))
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'method', 'type', 'url'])
        writer.writeheader()
        writer.writerows(requests_data)
    
    print(f"[{filename}] Guardado con éxito ({len(requests_data)} peticiones registradas).")

try:
    # Clear initial startup logs
    driver.get_log('performance')

    # --- HOMEPAGE ---
    url_home = "https://www.americanthinker.com/"
    print(f"\n[homepage] Cargando: {url_home}")
    driver.get(url_home)
    time.sleep(6)
    home_reqs = collect_network_requests()
    export_network_csv("homepage-wwwamericanthinkercom-super_agent-azerion-http-recorder-ads.csv", home_reqs)

    # --- SUBPAGE ---
    url_sub = "https://www.americanthinker.com/search/"
    print(f"\n[subpage] Cargando: {url_sub}")
    driver.get(url_sub)
    time.sleep(6)
    sub_reqs = collect_network_requests()
    export_network_csv("subpage-wwwamericanthinkercom-super_agent-azerion-http-recorder-ads.csv", sub_reqs)

finally:
    driver.quit()
    print("\n=== PRUEBA COMPLETADA EXITOSAMENTE ===")