"""
Kaching Strategy — Stock Scoring & Tiering
==========================================
Ranks stocks using a weighted composite score and assigns A/B/C tiers.

Scoring signals:
  - best_bucket_avg_pnl_pct  (50%) — primary quality signal
  - n_quotes                 (30%) — liquidity proxy
  - best_bucket_avg_spread (20%) — inverted (lower = better)

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
def generate_composite_score(input_path: str, output_path: str,
                              hard_filters: dict = {
                                "min_bucket_count": 10,
                                "min_price":        3,
                                "max_price":        300,
                                "min_pnl_pct":      0.0,   # strictly positive EV
                              }, weights: dict = {
                                "pnl_pct":  0.50,
                                "liquidity": 0.30,
                                "spread":    0.20,
                              }, tier_cuts: dict = {
                                "A": 0.85,   # top 15%
                                "B": 0.50,   # next 35%
                                # below 50th percentile → C
                              }) -> pd.DataFrame:

    # ── Load & clean ───────────────────────────────────────────────────────────────
    df = pd.read_csv(input_path)

    dollar_cols = ["best_bucket_avg_pnl", "best_bucket_avg_spread", "latest_price"]
    pct_cols    = ["avg_iv", "best_bucket_avg_iv",
                   "best_bucket_avg_pnl_pct"]

    for col in dollar_cols:
        if col not in df.columns:
            continue
        df[col] = df[col].astype(str).str.replace(r"[$,]", "", regex=True).astype(float)
    for col in pct_cols:
        if col not in df.columns:
            continue
        df[col] = df[col].astype(str).str.replace("%", "", regex=True).astype(float)

    # ── Filter ────────────────────────────────────────────────────────────────────

    before = len(df)
    df = df[df["best_bucket_count"] >= hard_filters["min_bucket_count"]]
    df = df[df["latest_price"]      >= hard_filters["min_price"]]
    df = df[df["latest_price"]      <= hard_filters["max_price"]]
    df = df[df["best_bucket_avg_pnl_pct"] > hard_filters["min_pnl_pct"]]
    print(f"Hard filters: {before} → {len(df)} stocks")

    # ── Score ─────────────────────────────────────────────────────────────────────
    df["_score_pnl"]      = df["best_bucket_avg_pnl_pct"].rank(pct=True)
    df["_score_liquidity"] = df["n_quotes"].rank(pct=True)
    df["_score_spread"]   = 1 - df["best_bucket_avg_spread"].rank(pct=True)

    df["composite_score"] = (
        weights["pnl_pct"]   * df["_score_pnl"] +
        weights["liquidity"] * df["_score_liquidity"] +
        weights["spread"]    * df["_score_spread"]
    )

    df["score_rank_pct"] = df["composite_score"].rank(pct=True)

    df["tier"] = "C"
    df.loc[df["score_rank_pct"] >= tier_cuts["B"], "tier"] = "B"
    df.loc[df["score_rank_pct"] >= tier_cuts["A"], "tier"] = "A"

    # ── Output ────────────────────────────────────────────────────────────────────

    OUTPUT_COLS = [
        "tier", "ticker", "composite_score",
        "best_bucket", "best_bucket_count",
        "best_bucket_avg_pnl_pct", "n_quotes",
        "best_bucket_avg_spread", "latest_price",
    ]
    OUTPUT_DOLLAR_COLS = ["best_bucket_avg_spread", "latest_price"]

    df_out = (
        df[OUTPUT_COLS]
        .sort_values("composite_score", ascending=False)
        .reset_index(drop=True)
    )

    for col in OUTPUT_DOLLAR_COLS:
        if col in df_out.columns:
            df_out[col] = df_out[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "")

    # Summary
    print("\nTier breakdown:")
    print(df_out["tier"].value_counts().sort_index().to_string())
    print("\nTop 20 stocks:")
    print(df_out.head(20).to_string(index=False))

    df_out.to_csv(output_path, index=False)
    print(f"\nSaved scores to {output_path}")

if __name__ == "__main__":
    INPUT_CSV  = os.path.join("outputs", "macro_summary.csv")
    OUTPUT_CSV = os.path.join("outputs", "kaching_scored_stocks.csv")

    generate_composite_score(INPUT_CSV, OUTPUT_CSV)