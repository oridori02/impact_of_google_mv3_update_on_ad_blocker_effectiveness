"""
Python version of the paper's main comparisons (Figures 4 and 5), using the
output of process_trackers.py.

For each page type (homepage, subpage, and both together) it:
  1. compares all MV2 vs all MV3 blockers (like Figure 4)
  2. compares MV2 vs MV3 within each ad blocker (like Figure 5, left column)
using Welch's t-test, which is what R's t.test() does by default.

Output: comparison_stats.csv and one bar chart per page type (PNG + PDF).

Usage:
    python3 analyze_blockers.py
    python3 analyze_blockers.py --input /path/to/python_analysis --metric blocked_domains
"""

import argparse
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DEFAULT_DIR = os.path.join(REPO_ROOT, "03_results", "python_analysis")

BLOCKER_ORDER = ["Adblock Plus", "AdGuard", "Stands", "uBlock"]
COLORS = {"MV2": "#D5E8D4", "MV3": "#DAE8FC"}  # same colours as the paper
METRIC_LABELS = {
    "blocked_trackers": "Blocked Trackers",
    "blocked_domains": "Blocked Third-Party Domains",
    "blocked_third_party_requests": "Blocked Third-Party Requests",
}


def welch(a, b):
    """Welch t-test (R's t.test default). Returns (t, p), or NaN when it can't be computed."""
    a, b = pd.Series(a).dropna(), pd.Series(b).dropna()
    if len(a) < 2 or len(b) < 2 or (a.var() == 0 and b.var() == 0):
        return np.nan, np.nan
    with warnings.catch_warnings():
        # scipy warns when samples are tiny and nearly identical; the result is still returned
        warnings.simplefilter("ignore", RuntimeWarning)
        t, p = stats.ttest_ind(b, a, equal_var=False)  # MV3 vs MV2, same sign as the paper
    return t, p


def compare(df, metric, page_label):
    """Group-level and per-blocker MV2 vs MV3 comparisons for one page type."""
    out = []
    data = df.dropna(subset=[metric])
    mv2 = data[data["instance_group_blocker"] == "MV2"]
    mv3 = data[data["instance_group_blocker"] == "MV3"]

    # Group level (Figure 4): delta is the mean of per-site (MV3 avg - MV2 avg)
    per_site = data.groupby(["domain", "instance_group_blocker"])[metric].mean().unstack()
    delta = (per_site.get("MV3") - per_site.get("MV2")).mean() if {"MV2", "MV3"} <= set(per_site.columns) else np.nan
    t, p = welch(mv2[metric], mv3[metric])
    out.append({
        "page_type": page_label, "comparison": "All MV3 vs all MV2", "metric": metric,
        "n_MV2": len(mv2), "n_MV3": len(mv3),
        "mean_MV2": mv2[metric].mean(), "mean_MV3": mv3[metric].mean(),
        "delta_MV3_minus_MV2": delta, "t_stat": t, "p_value": p,
    })

    # Per blocker (Figure 5)
    for name in BLOCKER_ORDER:
        b = data[data["ad_blocker_name"] == name]
        b2 = b[b["instance_group_blocker"] == "MV2"][metric]
        b3 = b[b["instance_group_blocker"] == "MV3"][metric]
        if b2.empty and b3.empty:
            continue
        t, p = welch(b2, b3)
        out.append({
            "page_type": page_label, "comparison": f"{name} MV3 vs MV2", "metric": metric,
            "n_MV2": len(b2), "n_MV3": len(b3),
            "mean_MV2": b2.mean(), "mean_MV3": b3.mean(),
            "delta_MV3_minus_MV2": b3.mean() - b2.mean(), "t_stat": t, "p_value": p,
        })
    return out


def plot(df, metric, page_label, out_dir):
    """Bar chart of mean +/- SE per blocker and manifest version, annotated with delta and p."""
    data = df.dropna(subset=[metric])
    names = [n for n in BLOCKER_ORDER if n in set(data["ad_blocker_name"])]
    if not names:
        return None

    x = np.arange(len(names))
    width = 0.38
    fig, ax = plt.subplots(figsize=(8, 4.5))

    tops, bottoms = [], []
    for offset, mv in [(-width / 2, "MV2"), (width / 2, "MV3")]:
        means, ses = [], []
        for n in names:
            vals = data[(data["ad_blocker_name"] == n) & (data["instance_group_blocker"] == mv)][metric]
            means.append(vals.mean() if len(vals) else np.nan)
            ses.append(vals.std(ddof=1) / np.sqrt(len(vals)) if len(vals) > 1 else 0)
        ax.bar(x + offset, means, width, yerr=ses, capsize=3, label=mv,
               color=COLORS[mv], edgecolor="black", linewidth=0.6)
        tops.extend(np.nan_to_num(np.array(means) + np.array(ses)))
        bottoms.extend(np.nan_to_num(np.array(means) - np.array(ses)))

    # Place labels relative to the whole axis range (works with negative values too)
    ymax = max(max(tops), 0)
    ymin = min(min(bottoms), 0)
    span = (ymax - ymin) or 1
    delta_y = ymax + 0.24 * span  # delta on top
    p_y = ymax + 0.12 * span      # p-value below it, with a clear gap
    for i, n in enumerate(names):
        b = data[data["ad_blocker_name"] == n]
        b2 = b[b["instance_group_blocker"] == "MV2"][metric]
        b3 = b[b["instance_group_blocker"] == "MV3"][metric]
        _, p = welch(b2, b3)
        delta = b3.mean() - b2.mean()
        p_txt = "p = n/a" if np.isnan(p) else f"p = {p:.2f}"
        d_txt = "Δ = n/a" if np.isnan(delta) else f"Δ = {delta:.2f}"
        ax.text(i, delta_y, d_txt, ha="center", va="bottom", fontsize=9, family="serif")
        ax.text(i, p_y, p_txt, ha="center", va="bottom", fontsize=9, family="serif")

    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_ylim(ymin - 0.05 * span, ymax + 0.34 * span)
    ax.set_xticks(x)
    ax.set_xticklabels(names, family="serif")
    ax.set_xlabel("Ad Blocker", family="serif")
    ax.set_ylabel(f"Average Number of {METRIC_LABELS.get(metric, metric)}", family="serif")
    ax.set_title(f"MV3 vs. MV2 ({page_label})", family="serif")
    ax.legend(title="Ad Blocker\nGroup", frameon=False, loc="center left", bbox_to_anchor=(1.01, 0.5))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    base = os.path.join(out_dir, f"mv3_vs_mv2_{metric}_{page_label}")
    fig.savefig(base + ".png", dpi=200)
    fig.savefig(base + ".pdf")
    plt.close(fig)
    return base + ".png"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=DEFAULT_DIR,
                        help="folder containing blocked_trackers.csv (from process_trackers.py)")
    parser.add_argument("--metric", default=None, choices=list(METRIC_LABELS),
                        help="which blocked count to analyse (default: trackers if available, else domains)")
    args = parser.parse_args()

    path = os.path.join(args.input, "blocked_trackers.csv")
    if not os.path.exists(path):
        sys.exit(f"[ERROR] {path} not found. Run process_trackers.py first.")
    df = pd.read_csv(path)

    metric = args.metric
    if metric is None:
        metric = "blocked_trackers" if df["blocked_trackers"].notna().any() else "blocked_domains"
        if metric == "blocked_domains":
            print("[INFO] No WhoTracks.me tracker counts available; analysing blocked third-party domains instead.")

    df = df[df["instance_group_blocker"].isin(["MV2", "MV3"])]

    results = []
    for page_label, subset in [("homepage", df[df["page_type"] == "homepage"]),
                               ("subpage", df[df["page_type"] == "subpage"]),
                               ("all_pages", df)]:
        if subset.empty:
            continue
        results.extend(compare(subset, metric, page_label))
        png = plot(subset, metric, page_label, args.input)
        if png:
            print(f"[SAVED] {png}")

    stats_df = pd.DataFrame(results)
    stats_path = os.path.join(args.input, f"comparison_stats_{metric}.csv")
    stats_df.to_csv(stats_path, index=False)
    print(f"[SAVED] {stats_path}\n")

    with pd.option_context("display.width", 140, "display.max_columns", 20,
                           "display.float_format", "{:.2f}".format):
        print(stats_df[["page_type", "comparison", "n_MV2", "n_MV3", "mean_MV2", "mean_MV3",
                        "delta_MV3_minus_MV2", "p_value"]].to_string(index=False))


if __name__ == "__main__":
    main()