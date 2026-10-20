import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Determinar la raíz del repositorio basándose en la ubicación del script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

INPUT_CSV = os.path.join(REPO_ROOT, "01_data", "top_1000_websites_tranco.csv")
OUTPUT_CSV = os.path.join(REPO_ROOT, "01_data", "websites_subpages_20.csv")
TARGET_COUNT = 20

# Cargar el dataset de 1000 sitios
df = pd.read_csv(INPUT_CSV)

# Detectar columna del dominio
col_domain = next((c for c in df.columns if c.lower() in ["domain", "url", "site", "website"]), df.columns[0])

# Estratificación: muestreo espaciado a lo largo de la lista
step = max(1, len(df) // (TARGET_COUNT * 3))
candidatos = df.iloc[::step].to_dict('records')

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

extensiones_estaticas = (".jpg", ".jpeg", ".png", ".gif", ".pdf", ".zip", ".css", ".js", ".svg", ".webp", ".mp4")
validados = []

print(f"Buscando {TARGET_COUNT} sitios con subpágina válida a partir de:\n{INPUT_CSV}\n")

for row in candidatos:
    if len(validados) >= TARGET_COUNT:
        break

    dominio_raw = str(row[col_domain]).strip()
    if not dominio_raw or dominio_raw == "nan":
        continue

    url_base = dominio_raw if dominio_raw.startswith("http") else f"https://{dominio_raw}"

    try:
        # 1. Probar conectividad con la portada
        res = requests.get(url_base, headers=headers, timeout=8, allow_redirects=True)
        if res.status_code != 200:
            continue

        contenido = res.text.lower()
        if "cf-browser-verification" in contenido or "just a moment..." in contenido or "captcha" in contenido:
            continue

        # 2. Parsear el DOM buscando una subpágina interna
        soup = BeautifulSoup(res.text, "html.parser")
        dominio_final = urlparse(res.url).netloc
        subpagina_elegida = None

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
                continue

            url_completa = urljoin(res.url, href)
            parsed_url = urlparse(url_completa)

            # Validar que sea del mismo dominio y ruta interna no estática
            if (parsed_url.netloc == dominio_final and 
                len(parsed_url.path) > 1 and 
                parsed_url.scheme in ["http", "https"] and 
                not any(url_completa.lower().endswith(ext) for ext in extensiones_estaticas)):

                # Comprobar que la subpágina responde 200
                res_sub = requests.get(url_completa, headers=headers, timeout=8, allow_redirects=True)
                if res_sub.status_code == 200:
                    subpagina_elegida = url_completa
                    break

        if subpagina_elegida:
            registro = {
                "domain": dominio_final,
                "homepage_url": res.url,
                "subpage_url": subpagina_elegida
            }
            for rank_col in ["rank", "tranco_rank", "Tranco_Rank"]:
                if rank_col in row:
                    registro["tranco_rank"] = row[rank_col]
                    break

            validados.append(registro)
            print(f"[{len(validados)}/{TARGET_COUNT}] {dominio_final} -> {subpagina_elegida}")

    except Exception:
        continue

# Guardar el dataset resultante en 01_data/
df_salida = pd.DataFrame(validados)
df_salida.to_csv(OUTPUT_CSV, index=False)
print(f"\nDataset completado con éxito en:\n{OUTPUT_CSV}")