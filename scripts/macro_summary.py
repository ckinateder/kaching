import sys
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import __init__

import os
import pandas as pd
from tqdm import tqdm

from src.postprocess import (
    OTM_BINS,
    OTM_LABELS,
    MONEYNESS_THRESHOLD,
    filter_weekly_put_options,
)


def _process_ticker(path: Path) -> dict | None:
    """
    Process a single ticker and return a dictionary of summary statistics.

    Args:
        path: Path to the ticker dataset parquet file.

    Returns:
        Dictionary of summary statistics.
        - ticker: Ticker symbol.
        - n_quotes: Number of quotes.
        - avg_iv: Average implied volatility (percent).
        - best_bucket: Best OTM bucket (e.g. "0.0-0.5%").
        - best_bucket_avg_pnl: Average PNL of best bucket (dollars).
        - best_bucket_avg_pnl_pct: Average PNL of best bucket as a percentage of latest price (percent).
        - best_bucket_avg_spread: Average spread of best bucket (dollars).
        - best_bucket_avg_spread_pct: Average spread of best bucket as a percentage of latest price (percent).
        - latest_price: Latest price (dollars).
    """

    ticker = path.stem.replace("_dataset", "")
    raw_df = pd.read_parquet(path)

    # Apply all filters using shared function
    df, _ = filter_weekly_put_options(raw_df, MONEYNESS_THRESHOLD)

    if df.empty:
        return None

    bucket_pnl = df.groupby("otm_bucket", observed=True)["pnl"].mean().dropna()
    if bucket_pnl.empty:
        return None
    best_bucket = bucket_pnl.idxmax()

    # Calculate latest price from raw_df (before filtering)
    latest_price = (
        raw_df.sort_values("timestamp")["underlying_close"].iloc[-1]
    )

    avg_iv = df["implied_vol"].mean() * 100
    best_bucket_avg_iv = df[df["otm_bucket"] == best_bucket]["implied_vol"].mean() * 100
    best_bucket_count = len(df[df["otm_bucket"] == best_bucket])

    # best pnl is avg pnl of best bucket
    best_bucket_avg_pnl = df[df["otm_bucket"] == best_bucket]["pnl"].mean()
    best_bucket_avg_pnl_pct = best_bucket_avg_pnl / latest_price * 100

    # avg bid/ask spread in best bucket: (ask - bid) per quote, then average
    best_bucket_quotes = df[df["otm_bucket"] == best_bucket]
    best_bucket_avg_spread = (best_bucket_quotes["ask"] - best_bucket_quotes["bid"]).mean()
    best_bucket_avg_spread_pct = best_bucket_avg_spread / latest_price * 100

    out = {
        "ticker": ticker,
        "n_quotes": len(df),
        "avg_iv": f"{avg_iv:.2f}%",
        "best_bucket": best_bucket,
        "best_bucket_count": best_bucket_count,
        "best_bucket_avg_iv": f"{best_bucket_avg_iv:.2f}%",
        "best_bucket_avg_pnl": f"${best_bucket_avg_pnl:.2f}",
        "best_bucket_avg_pnl_pct": f"{best_bucket_avg_pnl_pct:.2f}%",
        "best_bucket_avg_spread": f"${best_bucket_avg_spread:.2f}",
        "best_bucket_avg_spread_pct": f"{best_bucket_avg_spread_pct:.2f}%",
        "latest_price": f"${latest_price:.2f}",
    }
    return out

def generate_macro_summary(paths: list[Path]) -> pd.DataFrame:
    rows = []
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = {executor.submit(_process_ticker, p): p for p in paths}
        with tqdm(total=len(paths), desc="Processing tickers") as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    rows.append(result)
                pbar.update(1)
    return pd.DataFrame(rows)


# ── Config ────────────────────────────────────────────────────────────────────
def generate_composite_score(macro_summary_df: pd.DataFrame,
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
    # ── Load & clean ───────────────────────────────────────────────────────────────
    df = macro_summary_df

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

    return df_out
if __name__ == "__main__":
    paths = sorted(Path(os.path.join("data", "raw", "dataset")).glob("*.parquet"))
    if not paths:
        print("No *.parquet files found in data/raw/dataset")
    else:
        df = generate_macro_summary(paths)
        df.to_csv(os.path.join("outputs", "macro_summary.csv"), index=False)
        print(f"Saved macro summary to {os.path.join('outputs', 'macro_summary.csv')}")
        
        df_scored = generate_composite_score(df)
        df_scored.to_csv(os.path.join("outputs", "kaching_scored_stocks.csv"), index=False)
        print(f"Saved kaching scored stocks to {os.path.join('outputs', 'kaching_scored_stocks.csv')}")