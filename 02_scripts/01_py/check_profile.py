import os
import json
import time
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from subpages_crawler_LP_2026_PoPETS import extensions

temp_dir = os.path.join(tempfile.gettempdir(), 'chrome_test_profile')
rec_path = [p for p in extensions[0] if 'http-recorder' in p][0].replace('\\', '/')

print(f"Probando extension en: {rec_path}")
print(f"Directorio de perfil temporal: {temp_dir}\n")

opts = Options()
opts.add_argument(f"--user-data-dir={temp_dir}")
opts.add_argument(f"--load-extension={rec_path}")
opts.add_argument(f"--disable-extensions-except={rec_path}")

driver = webdriver.Chrome(options=opts)
time.sleep(3)
driver.quit()

pref_file = os.path.join(temp_dir, 'Default', 'Preferences')
if not os.path.exists(pref_file):
    print("No se encontro archivo Preferences.")
else:
    with open(pref_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    installed = data.get('extensions', {}).get('settings', {})
    print("=== EXTENSIONES REGISTRADAS EN PERFIL ===")
    found = False
    for ext_id, ext_info in installed.items():
        manifest = ext_info.get('manifest', {})
        name = manifest.get('name')
        if name:
            found = True
            print(f"ID: {ext_id} --> {name}")
    
    if not found:
        print("No se encontraron extensiones registradas en Preferences.")