"""
Holm-corrected MV2 vs MV3 comparisons, as paired tests.

Why this script exists
----------------------
The paper compares MV2 and MV3 ad blockers with many separate significance tests
(per ad blocker, per metric, per robustness sample) and reads each p-value against
0.05 on its own. The more tests you run, the more likely it is that at least one
crosses 0.05 by chance. The Holm (1979) step-down correction controls that
"family-wise" error rate: the chance of even one false positive across the whole
set of tests stays at or below 5%. Holm is uniformly more powerful than the
Bonferroni correction and needs no assumptions about how the tests are related.

The tests are also paired: every website is visited with both the MV2 and the MV3
version of a blocker, so we compare the two on the same site (per-site difference)
instead of treating them as two independent groups. A Wilcoxon signed-rank test is
reported next to the paired t-test because blocked counts are skewed.

Inputs (pick one)
-----------------
1. Your own crawl (default): blocked_trackers.csv from process_trackers.py
       python3 holm_analysis.py
       python3 holm_analysis.py --input ../../03_results/python_analysis/blocked_trackers.csv
2. The paper's processed data:
       python3 holm_analysis.py --rds ../../01_data/blocker_effectiveness_df.rds
   (needs:  python -m pip install pyreadr)

Options
-------
    --exclude uBlock        leave a blocker out (e.g. one that did not run)
    --family all|metric     what counts as one family of tests (default: all)

Outputs (in the output folder)
------------------------------
    holm_results.csv        every test with raw and Holm-adjusted p-values
    holm_pvalues.png/.pdf   chart: raw vs adjusted p-value per comparison
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
DEFAULT_INPUT = os.path.join(REPO_ROOT, "03_results", "python_analysis", "blocked_trackers.csv")
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "03_results", "python_analysis")

BLOCKER_ORDER = ["Adblock Plus", "AdGuard", "Stands", "uBlock"]
ALPHA = 0.05


# ----------------------------------------------------------------------------
# Loading: both inputs end up in one long format
#   unit | page_type | ad_blocker_name | mv | metric | value
# "unit" is what gets paired: a website (paper) or a website page (your crawl).
# ----------------------------------------------------------------------------

def load_own_crawl(path):
    df = pd.read_csv(path)
    metrics = [m for m in ["blocked_trackers", "blocked_domains", "blocked_third_party_requests"]
               if m in df.columns and df[m].notna().any()]
    df = df[df["instance_group_blocker"].isin(["MV2", "MV3"])]
    long = df.melt(id_vars=["domain", "page_type", "ad_blocker_name", "instance_group_blocker"],
                   value_vars=metrics, var_name="metric", value_name="value")
    long["unit"] = long["page_type"] + ":" + long["domain"]
    return long.rename(columns={"instance_group_blocker": "mv"})


def load_paper_rds(path):
    try:
        import pyreadr
    except ImportError:
        sys.exit("[ERROR] Reading .rds files needs pyreadr:  python -m pip install pyreadr")
    df = next(iter(pyreadr.read_r(path).values()))

    needed = {"cleaned_domain", "instance_blocker", "instance_group_blocker"}
    if not needed.issubset(df.columns):
        sys.exit(f"[ERROR] {path} is missing columns {needed - set(df.columns)}. "
                 f"Columns found: {list(df.columns)}")
    metrics = [m for m in ["avg_blocked_ads", "avg_blocked_trackers", "avg_blocked_domains"]
               if m in df.columns]

    df = df[df["instance_group_blocker"].astype(str).isin(["MV2", "MV3"])].copy()  # drops MV3+
    df["ad_blocker_name"] = df["instance_blocker"].astype(str).str.replace(r"\s+MV[23]\+?$", "", regex=True)
    df["page_type"] = "homepage"
    long = df.melt(id_vars=["cleaned_domain", "page_type", "ad_blocker_name", "instance_group_blocker"],
                   value_vars=metrics, var_name="metric", value_name="value")
    long = long.rename(columns={"cleaned_domain": "unit", "instance_group_blocker": "mv"})
    long["mv"] = long["mv"].astype(str)
    return long


# ----------------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------------

def paired_tests(diff):
    """Paired t-test and Wilcoxon signed-rank on per-unit differences (MV3 - MV2)."""
    diff = pd.Series(diff).dropna()
    n = len(diff)
    p_t = p_w = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if n >= 2 and diff.std(ddof=1) > 0:
            p_t = stats.ttest_1samp(diff, 0).pvalue
        if (diff != 0).sum() >= 1:
            # 'pratt' keeps zero differences in the ranking, which matters here:
            # many sites have identical counts under MV2 and MV3
            p_w = stats.wilcoxon(diff, zero_method="pratt").pvalue
    return n, p_t, p_w


def holm(pvalues):
    """Holm step-down adjustment. NaN p-values are ignored and stay NaN.

    Sort the m p-values ascending, multiply the i-th smallest by (m - i + 1),
    then make the sequence non-decreasing and cap it at 1.
    """
    p = np.asarray(pvalues, dtype=float)
    adjusted = np.full_like(p, np.nan)
    valid = ~np.isnan(p)
    m = valid.sum()
    if m == 0:
        return adjusted
    order = np.argsort(p[valid])
    ranked = p[valid][order] * (m - np.arange(m))
    ranked = np.minimum(np.maximum.accumulate(ranked), 1.0)
    out = np.empty(m)
    out[order] = ranked
    adjusted[valid] = out
    return adjusted


def run_comparisons(long):
    """One row per (metric, page type, comparison)."""
    rows = []
    for (metric, page_type), d in long.groupby(["metric", "page_type"]):
        # One value per unit, blocker and MV (averages repeated runs if there are any)
        wide = d.pivot_table(index="unit", columns=["ad_blocker_name", "mv"],
                             values="value", aggfunc="mean")

        comparisons = []
        # Per ad blocker: same blocker, MV3 vs MV2, on the same site
        for name in [b for b in BLOCKER_ORDER if b in wide.columns.get_level_values(0)] + \
                    sorted(set(wide.columns.get_level_values(0)) - set(BLOCKER_ORDER)):
            if (name, "MV2") in wide.columns and (name, "MV3") in wide.columns:
                comparisons.append((f"{name}: MV3 vs MV2", wide[(name, "MV3")] - wide[(name, "MV2")],
                                    wide[(name, "MV2")], wide[(name, "MV3")]))

        # All blockers together: per site, average of the MV3 blockers vs the MV2 blockers.
        # Only blockers present in both versions, so both sides contain the same blockers.
        both = [n for n in wide.columns.get_level_values(0).unique()
                if (n, "MV2") in wide.columns and (n, "MV3") in wide.columns]
        if both:
            mv2 = wide[[(n, "MV2") for n in both]].mean(axis=1, skipna=False)
            mv3 = wide[[(n, "MV3") for n in both]].mean(axis=1, skipna=False)
            comparisons.append(("All blockers: MV3 vs MV2", mv3 - mv2, mv2, mv3))

        for label, diff, a, b in comparisons:
            n, p_t, p_w = paired_tests(diff)
            rows.append({
                "metric": metric, "page_type": page_type, "comparison": label, "n_pairs": n,
                "mean_MV2": a.mean(), "mean_MV3": b.mean(), "mean_diff_MV3_minus_MV2": diff.mean(),
                "p_paired_t": p_t, "p_wilcoxon": p_w,
            })
    return pd.DataFrame(rows)


def add_holm(res, family):
    """Holm-adjust each test type separately, within the chosen family."""
    groups = [res.index] if family == "all" else [g.index for _, g in res.groupby("metric")]
    for test in ["p_paired_t", "p_wilcoxon"]:
        adj_col = test + "_holm"
        res[adj_col] = np.nan
        for idx in groups:
            res.loc[idx, adj_col] = holm(res.loc[idx, test].values)
        res[test.replace("p_", "sig_") + "_raw"] = res[test] < ALPHA
        res[test.replace("p_", "sig_") + "_holm"] = res[adj_col] < ALPHA
    return res


# ----------------------------------------------------------------------------
# Chart: raw vs Holm-adjusted p-value per comparison (paired t-test)
# ----------------------------------------------------------------------------

INK = "#1F1F1F"
MUTED = "#6B6B6B"
GRID = "#E3E3E3"
RAW_COLOR = "#8C8C8C"      # neutral: the uncorrected value
HOLM_COLOR = "#2A5DB0"     # accent: the value to read


def plot(res, out_dir):
    data = res.dropna(subset=["p_paired_t"]).copy()
    if data.empty:
        return None
    data["label"] = data["comparison"] + "  (" + data["metric"].str.replace("_", " ") + \
        (", " + data["page_type"] if data["page_type"].nunique() > 1 else "") + ")"
    data = data.sort_values("p_paired_t", ascending=False)

    fig_h = max(2.5, 0.32 * len(data) + 1.4)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    y = np.arange(len(data))
    floor = 1e-6  # keep p = 0 visible on the log axis
    raw = np.maximum(data["p_paired_t"].values, floor)
    adj = np.maximum(data["p_paired_t_holm"].values, floor)

    ax.hlines(y, raw, adj, color=GRID, linewidth=2, zorder=1)
    ax.scatter(raw, y, s=40, facecolors="white", edgecolors=RAW_COLOR, linewidths=1.5,
               label="Uncorrected p", zorder=2)
    ax.scatter(adj, y, s=40, color=HOLM_COLOR, edgecolors="white", linewidths=1,
               label="Holm-adjusted p", zorder=3)
    ax.axvline(ALPHA, color=INK, linestyle="--", linewidth=1)
    ax.text(ALPHA, len(data) - 0.4, " α = 0.05", color=INK, fontsize=9, va="bottom")

    ax.set_xscale("log")
    ax.set_xlim(min(raw.min(), adj.min(), 1e-3) / 2, 1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(data["label"], fontsize=9, color=INK)
    ax.set_xlabel("p-value (paired t-test, log scale) - left of the dashed line = significant",
                  color=MUTED, fontsize=9)
    ax.set_title("Which MV2 vs MV3 differences survive the Holm correction?", color=INK, fontsize=11, pad=28)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=9)
    fig.tight_layout()

    base = os.path.join(out_dir, "holm_pvalues")
    # bbox_inches="tight" keeps long titles and labels from being cut off at the edge
    fig.savefig(base + ".png", dpi=200, bbox_inches="tight")
    fig.savefig(base + ".pdf", bbox_inches="tight")
    plt.close(fig)
    return base + ".png"


# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="blocked_trackers.csv from process_trackers.py")
    parser.add_argument("--rds", help="the paper's blocker_effectiveness_df.rds (instead of --input)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="folder for results")
    parser.add_argument("--exclude", nargs="*", default=[], help="ad blocker names to leave out, e.g. uBlock")
    parser.add_argument("--family", choices=["all", "metric"], default="all",
                        help="all = correct across every test in the run (default); "
                             "metric = correct separately for each metric")
    args = parser.parse_args()

    if args.rds:
        long = load_paper_rds(args.rds)
        source = os.path.basename(args.rds)
    else:
        if not os.path.exists(args.input):
            sys.exit(f"[ERROR] {args.input} not found. Run process_trackers.py first, or pass --rds.")
        long = load_own_crawl(args.input)
        source = os.path.basename(args.input)

    if args.exclude:
        long = long[~long["ad_blocker_name"].isin(args.exclude)]
        print(f"[INFO] Excluded: {', '.join(args.exclude)}")

    os.makedirs(args.output, exist_ok=True)
    res = add_holm(run_comparisons(long), args.family)

    out_csv = os.path.join(args.output, "holm_results.csv")
    res.to_csv(out_csv, index=False)

    m = res["p_paired_t"].notna().sum()
    lost = res[res["sig_paired_t_raw"] & ~res["sig_paired_t_holm"]]
    kept = res[res["sig_paired_t_holm"]]

    print(f"\nData: {source}   |   tests in the Holm family: {m} ({args.family})\n")
    cols = ["metric", "page_type", "comparison", "n_pairs", "mean_diff_MV3_minus_MV2",
            "p_paired_t", "p_paired_t_holm", "p_wilcoxon", "p_wilcoxon_holm"]
    with pd.option_context("display.width", 200, "display.max_columns", 20,
                           "display.float_format", "{:.3f}".format):
        print(res[cols].to_string(index=False))

    print(f"\nSignificant before correction (paired t): {int(res['sig_paired_t_raw'].sum())}")
    print(f"Significant after Holm correction:        {len(kept)}")
    for _, r in lost.iterrows():
        print(f"  no longer significant: {r['comparison']} ({r['metric']}, {r['page_type']}) "
              f"p = {r['p_paired_t']:.3f} -> {r['p_paired_t_holm']:.3f}")

    png = plot(res, args.output)
    print(f"\n[SAVED] {out_csv}")
    if png:
        print(f"[SAVED] {png}")


if __name__ == "__main__":
    main()