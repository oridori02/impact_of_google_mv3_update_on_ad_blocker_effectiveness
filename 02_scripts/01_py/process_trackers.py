"""
Python port of process_trackers_file() from 02_scripts/02_R/helper_functions.R,
plus the "blocked = baseline - blocker" step used in the paper.

Input:  the crawler CSVs (homepage-...-ads.csv / subpage-...-ads.csv)
Output: page_tracker_counts.csv  (one row per page x extension group)
        blocked_trackers.csv     (one row per page x ad blocker, with blocked counts)

Usage (from anywhere):
    python3 process_trackers.py
    python3 process_trackers.py --input /path/to/new_csvs_ana --output /path/to/output_folder
"""

import argparse
import os
import re
import sys

import pandas as pd

# --- DEFAULT PATHS (same repo layout as the other scripts) ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DEFAULT_INPUT_DIR = os.path.join(REPO_ROOT, "03_results", "new_check_csvs")
DEFAULT_OUTPUT_DIR = os.path.join(REPO_ROOT, "03_results", "python_analysis")
WHOTRACKS_DIR = os.path.join(REPO_ROOT, "01_data", "06_whotracks.me-data")

# --- EXTENSION GROUPS ---
BASELINE_GROUP = "super_agent-azerion"

# Folder-based group names -> labels used in the paper.
# Note: the paper relabels "Fair Adblocker MV3" as "Stands MV3".
GROUP_LABELS = {
    "super_agent-azerion": "Baseline",
    "super_agent-azerion-adblock_plus_free_ad_blocker_3.25.1_MV2": "Adblock Plus MV2",
    "super_agent-azerion-adblock_plus_free_ad_blocker_4.5.1_MV3": "Adblock Plus MV3",
    "super_agent-azerion-adguard_adblocker_MV2": "AdGuard MV2",
    "super_agent-azerion-adguard_adblocker_mv3_beta_MV3": "AdGuard MV3",
    "super_agent-azerion-stands_adblocker_MV2": "Stands MV2",
    "super_agent-azerion-fair_adblocker_mv3_beta_MV3": "Stands MV3",
    "super_agent-azerion-ublock_origin_MV2": "uBlock MV2",
    "super_agent-azerion-ublock_origin_lite_MV3": "uBlock MV3",
}

# homepage-<domain>-<group>-ads.csv  (domain may contain hyphens, so anchor on the group)
FILENAME_RE = re.compile(r"^(homepage|subpage)-(.+?)-(super_agent-azerion.*)-ads\.csv$")


def get_domain(x):
    """Same logic as get_domain() in helper_functions.R: strip scheme and 'www.',
    take the host, keep the last two labels (e.g. 'ads.example.com' -> 'example.com')."""
    url = re.sub(r"http://|https://|www\.", "", str(x))
    host = url.split("/")[0]
    labels = host.split(".")
    return ".".join(labels[-2:])


def load_whotracks():
    """Load the WhoTracks.me domain -> tracker name lookup, or None if the files are missing."""
    domains_path = os.path.join(WHOTRACKS_DIR, "tracker_domains.csv")
    trackers_path = os.path.join(WHOTRACKS_DIR, "trackers.csv")
    if not (os.path.exists(domains_path) and os.path.exists(trackers_path)):
        print(f"[WARN] WhoTracks.me files not found in {WHOTRACKS_DIR}")
        print("       Tracker counts (n_whotracksme_trackers) will be empty.")
        print("       Third-party domain counts are still computed.\n")
        return None

    domains = pd.read_csv(domains_path, usecols=["domain", "tracker"])
    trackers = pd.read_csv(trackers_path, usecols=["id", "name"])
    merged = domains.merge(trackers, left_on="tracker", right_on="id", how="left")
    # One domain can appear more than once; keep the first match like a left join would
    merged = merged.drop_duplicates(subset="domain")
    return dict(zip(merged["domain"], merged["name"]))


def process_trackers_file(path, domain_to_tracker):
    """Python version of process_trackers_file() in helper_functions.R."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    expected = {"method", "url", "initiator"}
    if not expected.issubset(df.columns):
        raise ValueError(f"missing columns {expected - set(df.columns)}")

    # Requests the ad blocker stopped never reached the server: count them, then drop them.
    # (Only CSVs from the updated crawler have this column; older ones are used as-is.)
    if "blocked" in df.columns:
        is_blocked = df["blocked"].str.strip().str.lower().isin(["true", "1"])
        n_blocked = int(is_blocked.sum())
        df = df[~is_blocked]
    else:
        n_blocked = pd.NA

    # Remove requests initiated by extensions
    df = df[~df["initiator"].str.contains("chrome-extension://", regex=False)]
    # Keep only GET/POST requests
    df = df[df["method"].str.contains("GET|POST", regex=True)]
    # Drop rows without an initiator (R reads empty strings as NA and drops them)
    df = df[df["initiator"].str.strip() != ""]

    if df.empty:
        return {
            "n_total_requests": 0,
            "n_first_party_requests": 0,
            "n_third_party_requests": 0,
            "n_unique_third_party_domains": 0,
            "n_whotracksme_trackers": 0 if domain_to_tracker is not None else pd.NA,
            "n_blocked_requests": n_blocked,
        }

    initiator_domain = df["initiator"].map(get_domain)
    request_domain = df["url"].map(get_domain)
    third_party = request_domain != initiator_domain

    third_party_domains = request_domain[third_party].dropna()
    third_party_domains = third_party_domains[third_party_domains != ""]

    if domain_to_tracker is not None:
        tracker_names = third_party_domains.map(domain_to_tracker).dropna()
        n_trackers = tracker_names.nunique()
    else:
        n_trackers = pd.NA

    return {
        "n_total_requests": len(df),
        "n_first_party_requests": int((~third_party).sum()),
        "n_third_party_requests": int(third_party.sum()),
        "n_unique_third_party_domains": third_party_domains.nunique(),
        "n_whotracksme_trackers": n_trackers,
        "n_blocked_requests": n_blocked,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=DEFAULT_INPUT_DIR, help="folder with the crawler CSVs")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="folder for the result CSVs")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        sys.exit(f"[ERROR] Input folder not found: {args.input}\n"
                 f"        Pass the right one with --input /path/to/new_csvs_ana")
    os.makedirs(args.output, exist_ok=True)

    domain_to_tracker = load_whotracks()

    rows = []
    skipped = []
    for name in sorted(os.listdir(args.input)):
        match = FILENAME_RE.match(name)
        if not match:
            if name.endswith(".csv"):
                skipped.append(name)
            continue
        page_type, domain, group = match.groups()
        try:
            counts = process_trackers_file(os.path.join(args.input, name), domain_to_tracker)
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
            continue
        rows.append({
            "page_type": page_type,
            "domain": domain,
            "group": group,
            "instance_blocker": GROUP_LABELS.get(group, group),
            **counts,
        })

    if skipped:
        print(f"[INFO] Skipped {len(skipped)} CSV(s) that don't match the crawler naming pattern.")
    if not rows:
        sys.exit("[ERROR] No crawler CSVs found. Check the --input folder.")

    counts_df = pd.DataFrame(rows)
    if counts_df["n_blocked_requests"].isna().any():
        n_old = int(counts_df["n_blocked_requests"].isna().sum())
        print(f"[WARN] {n_old} CSV(s) come from the old crawler (no 'blocked' column). "
              "Blocked requests are still counted in them, so re-crawl for accurate results.")
    unknown = sorted(set(counts_df["group"]) - set(GROUP_LABELS))
    if unknown:
        print(f"[WARN] Unknown extension groups (kept with their folder names): {unknown}")

    counts_path = os.path.join(args.output, "page_tracker_counts.csv")
    counts_df.to_csv(counts_path, index=False)
    print(f"[SAVED] {counts_path} ({len(counts_df)} pages)")

    # --- Blocked = baseline - blocker, per page ---
    baseline = counts_df[counts_df["group"] == BASELINE_GROUP][[
        "page_type", "domain", "n_whotracksme_trackers", "n_unique_third_party_domains",
        "n_third_party_requests",
    ]].rename(columns={
        "n_whotracksme_trackers": "baseline_trackers",
        "n_unique_third_party_domains": "baseline_domains",
        "n_third_party_requests": "baseline_third_party_requests",
    })

    blockers = counts_df[counts_df["group"] != BASELINE_GROUP].merge(
        baseline, on=["page_type", "domain"], how="left"
    )
    blockers["blocked_trackers"] = blockers["baseline_trackers"] - blockers["n_whotracksme_trackers"]
    blockers["blocked_domains"] = blockers["baseline_domains"] - blockers["n_unique_third_party_domains"]
    blockers["blocked_third_party_requests"] = (
        blockers["baseline_third_party_requests"] - blockers["n_third_party_requests"]
    )

    # Manifest version group (MV2 / MV3) and blocker name, as in the paper
    blockers["instance_group_blocker"] = blockers["instance_blocker"].str.extract(r"(MV[23]\+?)$")[0]
    blockers["ad_blocker_name"] = blockers["instance_blocker"].str.replace(r"\s+MV[23]\+?$", "", regex=True)

    missing_baseline = blockers["baseline_domains"].isna()
    if missing_baseline.any():
        pages = blockers.loc[missing_baseline, ["page_type", "domain"]].drop_duplicates()
        print(f"[WARN] {len(pages)} page(s) have no baseline CSV, so blocked counts are empty for them:")
        for _, r in pages.iterrows():
            print(f"         {r['page_type']} {r['domain']}")

    blocked_path = os.path.join(args.output, "blocked_trackers.csv")
    blockers.to_csv(blocked_path, index=False)
    print(f"[SAVED] {blocked_path} ({len(blockers)} page x blocker rows)")


if __name__ == "__main__":
    main()