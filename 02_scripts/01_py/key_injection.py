"""
Key Injection Script (Forced RSA 2048-bit Regeneration)
Unconditionally overwrites the 'key' field with valid RSA DER keys
to ensure that Chrome recognizes the computed IDs.
"""

import os
import json
import base64
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
EXTENSIONS_DIR = os.path.join(REPO_ROOT, "01_data", "extensions")

print(f"Searching for extensions in: {EXTENSIONS_DIR}\n")

manifests_found = []
for root, dirs, files in os.walk(EXTENSIONS_DIR):
    if "manifest.json" in files:
        manifests_found.append(os.path.join(root, "manifest.json"))

print(f"Found {len(manifests_found)} extensions.\n")

for manifest_path in manifests_found:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        ext_name = manifest.get("name", "Unknown Extension")
        rel_path = os.path.relpath(manifest_path, EXTENSIONS_DIR)

        # 1. Generate a new valid 2048-bit RSA key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )

        # 2. Extract the public key in standard DER SubjectPublicKeyInfo format
        public_key_der = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        # 3. Encode in Base64 without line breaks
        public_key_b64 = base64.b64encode(public_key_der).decode("utf-8")

        # 4. Always overwrite the 'key' field
        manifest["key"] = public_key_b64

        # If it's http-recorder, ensure web_accessible_resources
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

        print(f"[REGENERATED] Valid RSA key injected: {ext_name} ({rel_path})")

    except Exception as e:
        print(f"[ERROR] Error processing {manifest_path}: {e}")

print("\nRegeneration completed successfully.")
