"""
Key Injection Script (Forced RSA 2048-bit Regeneration)
Sobrescribe incondicionalmente el campo 'key' con claves RSA DER validas
para asegurar que Chrome reconozca las IDs calculadas.
"""

import os
import json
import base64
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
EXTENSIONS_DIR = os.path.join(REPO_ROOT, "01_data", "extensions")

print(f"Buscando extensiones en: {EXTENSIONS_DIR}\n")

manifests_encontrados = []
for root, dirs, files in os.walk(EXTENSIONS_DIR):
    if "manifest.json" in files:
        manifests_encontrados.append(os.path.join(root, "manifest.json"))

print(f"Se encontraron {len(manifests_encontrados)} extensiones.\n")

for manifest_path in manifests_encontrados:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        ext_name = manifest.get("name", "Unknown Extension")
        rel_path = os.path.relpath(manifest_path, EXTENSIONS_DIR)

        # 1. Generar nueva clave RSA de 2048 bits valida
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # 2. Extraer clave publica en formato estandar DER SubjectPublicKeyInfo
        public_key_der = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # 3. Codificar en Base64 sin saltos de linea
        public_key_b64 = base64.b64encode(public_key_der).decode("utf-8")

        # 4. Sobrescribir siempre el campo 'key'
        manifest["key"] = public_key_b64

        # Si es http-recorder, garantizar web_accessible_resources
        if "http-recorder" in manifest_path:
            manifest["web_accessible_resources"] = [
                "popup.html",
                "popup.js",
                "jquery-3.7.1.min.js",
                "jquery.csv.min.js",
                "*"
            ]

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print(f"[REGENERATED] Clave RSA valida inyectada: {ext_name} ({rel_path})")

    except Exception as e:
        print(f"[ERROR] Error procesando {manifest_path}: {e}")

print("\nRegeneracion completa con exito.")