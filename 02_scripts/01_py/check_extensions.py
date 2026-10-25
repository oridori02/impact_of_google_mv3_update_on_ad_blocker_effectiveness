"""
Checks whether the crawler's extensions actually load in Chrome.

For each extension group it starts Chrome exactly like subpages_crawler_LP_2026_PoPETS.py,
opens chrome://extensions and asks Chrome which extensions are installed and enabled.
If an extension is missing or not enabled here, it was not active during the crawl.

Usage (from 02_scripts/01_py):
    python3 check_extensions.py
"""

import json
import os
import time

import subpages_crawler_LP_2026_PoPETS as crawler

# Runs inside chrome://extensions, which has access to Chrome's own extension list
LIST_EXTENSIONS_JS = """
const done = arguments[arguments.length - 1];
try {
  chrome.developerPrivate.getExtensionsInfo(
    {includeDisabled: true, includeTerminated: true},
    infos => done(JSON.stringify(infos.map(i => ({
      id: i.id, name: i.name, state: i.state,
      disableReasons: i.disableReasons, path: i.prettifiedPath || ''
    }))))
  );
} catch (e) {
  done(JSON.stringify({error: String(e)}));
}
"""


def installed_extensions(driver):
    """Return {folder_path_or_id: info} for every extension Chrome knows about."""
    driver.get("chrome://extensions/")
    time.sleep(2)
    driver.set_script_timeout(15)
    raw = driver.execute_async_script(LIST_EXTENSIONS_JS)
    data = json.loads(raw)
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(data["error"])
    return data


def main():
    for idx, group in enumerate(crawler.extensions):
        tag = crawler.get_extension_group_label(group)
        driver = crawler.create_driver(group)
        try:
            if idx == 0:
                print(f"Chrome version: {driver.capabilities.get('browserVersion')}\n")
            time.sleep(5)  # give extensions time to start
            try:
                infos = installed_extensions(driver)
            except Exception as e:
                print(f"[{idx}] {tag}\n      Could not read chrome://extensions: {e}\n")
                continue
        finally:
            driver.quit()

        print(f"[{idx}] {tag}")
        for path in group:
            folder = os.path.basename(os.path.dirname(path.rstrip("/\\")))
            id_folder = os.path.basename(path.rstrip("/\\"))
            # Unpacked extensions get an ID from their path or manifest key, so match on path too
            match = next((i for i in infos
                          if i["id"] == id_folder or id_folder in i.get("path", "")), None)
            if not os.path.exists(path):
                print(f"      FOLDER MISSING  {folder}")
            elif match is None:
                print(f"      NOT LOADED      {folder}")
            elif match["state"] != "ENABLED":
                dr = match.get("disableReasons") or {}
                # Chrome returns this as {reasonName: true/false}
                reasons = ", ".join(k for k, v in dr.items() if v) if isinstance(dr, dict) else str(dr)
                reasons = reasons or "unknown"
                print(f"      {match['state']:15s} {folder}  (reason: {reasons})")
            else:
                print(f"      ENABLED         {folder}  ({match['name']})")
        print()

    print("Every extension should show ENABLED. Anything else was not active during the crawl.")


if __name__ == "__main__":
    main()