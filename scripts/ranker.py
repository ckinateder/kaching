"""
Kaching Strategy — Stock Scoring & Tiering
==========================================
Ranks stocks using a weighted composite score and assigns A/B/C tiers.

Scoring signals:
  - best_bucket_avg_pnl_pct  (50%) — primary quality signal
  - n_quotes                 (30%) — liquidity proxy
  - best_bucket_avg_spread_pct (20%) — inverted (lower = better)

Hard filters applied before scoring:
  - best_bucket_count >= 10  (minimum statistical reliability)
  - latest_price <= 300      (assignment affordability)
  - best_bucket_avg_pnl_pct > 0  (must have positive expected value)

Tier cuts (by rank percentile of filtered universe):
  - A: top 15%
  - B: next 35% (top 50% overall)
  - C: bottom 50%
"""

import pandas as pd
import numpy as np
import sys
import os

# ── Config ────────────────────────────────────────────────────────────────────

INPUT_CSV  = os.path.join("outputs", "macro_summary.csv")
OUTPUT_CSV = os.path.join("outputs", "kaching_scored_stocks.csv")

HARD_FILTERS = {
    "min_bucket_count": 10,
    "min_price":        3,
    "max_price":        300,
    "min_pnl_pct":      0.0,   # strictly positive EV
    "max_spread_pct":   20.0,
}

WEIGHTS = {
    "pnl_pct":  0.50,
    "liquidity": 0.30,
    "spread":    0.20,
}

TIER_CUTS = {
    "A": 0.85,   # top 15%
    "B": 0.50,   # next 35%
    # below 50th percentile → C
}

# ── Load & clean ───────────────────────────────────────────────────────────────

def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    dollar_cols = ["best_bucket_avg_pnl", "best_bucket_avg_spread", "latest_price"]
    pct_cols    = ["avg_iv", "best_bucket_avg_iv",
                   "best_bucket_avg_pnl_pct", "best_bucket_avg_spread_pct"]

    for col in dollar_cols:
        df[col] = df[col].str.replace(r"[$,]", "", regex=True).astype(float)
    for col in pct_cols:
        df[col] = df[col].str.replace("%", "", regex=True).astype(float)

    return df

# ── Filter ────────────────────────────────────────────────────────────────────

def apply_hard_filters(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df[df["best_bucket_count"] >= HARD_FILTERS["min_bucket_count"]]
    df = df[df["latest_price"]      >= HARD_FILTERS["min_price"]]
    df = df[df["latest_price"]      <= HARD_FILTERS["max_price"]]
    df = df[df["best_bucket_avg_pnl_pct"] > HARD_FILTERS["min_pnl_pct"]]
    df = df[df["best_bucket_avg_spread_pct"] <= HARD_FILTERS["max_spread_pct"]]
    print(f"Hard filters: {before} → {len(df)} stocks")
    return df.copy()

# ── Score ─────────────────────────────────────────────────────────────────────

def score(df: pd.DataFrame) -> pd.DataFrame:
    df["_score_pnl"]      = df["best_bucket_avg_pnl_pct"].rank(pct=True)
    df["_score_liquidity"] = df["n_quotes"].rank(pct=True)
    df["_score_spread"]   = 1 - df["best_bucket_avg_spread_pct"].rank(pct=True)

    df["composite_score"] = (
        WEIGHTS["pnl_pct"]   * df["_score_pnl"] +
        WEIGHTS["liquidity"] * df["_score_liquidity"] +
        WEIGHTS["spread"]    * df["_score_spread"]
    )

    df["score_rank_pct"] = df["composite_score"].rank(pct=True)

    df["tier"] = "C"
    df.loc[df["score_rank_pct"] >= TIER_CUTS["B"], "tier"] = "B"
    df.loc[df["score_rank_pct"] >= TIER_CUTS["A"], "tier"] = "A"

    return df

# ── Output ────────────────────────────────────────────────────────────────────

OUTPUT_COLS = [
    "tier", "ticker", "composite_score",
    "best_bucket", "best_bucket_count",
    "best_bucket_avg_pnl_pct", "n_quotes",
    "best_bucket_avg_spread_pct", "latest_price",
]

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else INPUT_CSV
    df = load_and_clean(path)
    df = apply_hard_filters(df)
    df = score(df)

    df_out = (
        df[OUTPUT_COLS]
        .sort_values("composite_score", ascending=False)
        .reset_index(drop=True)
    )

    # Summary
    print("\nTier breakdown:")
    print(df_out["tier"].value_counts().sort_index().to_string())
    print("\nTop 20 stocks:")
    print(df_out.head(20).to_string(index=False))

    df_out.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved → {OUTPUT_CSV}")

if __name__ == "__main__":
    main()