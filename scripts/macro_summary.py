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

if __name__ == "__main__":
    paths = sorted(Path(os.path.join("data", "raw", "dataset")).glob("*.parquet"))
    if not paths:
        print("No *.parquet files found in data/raw/dataset")
    else:
        df = generate_macro_summary(paths)
        df.to_csv(os.path.join("outputs", "macro_summary.csv"), index=False)

        print(df.to_string())
