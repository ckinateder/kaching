from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from src.postprocess import add_moneyness, add_price_at_expiry, add_pnl

def make_bucket_labels(bins: list[float]) -> list[str]:
    """Given a list of monotonically increasing bin edges, return string labels."""
    return [f"{bins[i]:.1f}-{bins[i+1]:.1f}%" for i in range(len(bins) - 1)]

OTM_BINS = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
OTM_LABELS = make_bucket_labels(OTM_BINS)
MONEYNESS_THRESHOLD = (-0.2, 0)


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

    # Split ratio filter
    ratio = raw_df["underlying_price"] / raw_df["underlying_close"]
    raw_df = raw_df[(ratio > 0.9) & (ratio < 1.1)]

    df = add_moneyness(raw_df)
    df = add_price_at_expiry(df)
    df = add_pnl(df)

    # PUT only, OTM filter, bid > 0
    df = df[df["right"] == "PUT"]
    df = df[(df["moneyness"] > MONEYNESS_THRESHOLD[0]) & (df["moneyness"] < MONEYNESS_THRESHOLD[1])]
    df = df[df["bid"] > 0]

    # Thu/Fri only
    df["quote_date"] = pd.to_datetime(df["timestamp"]).dt.date
    df = df[pd.to_datetime(df["timestamp"]).dt.dayofweek.isin([3, 4])]

    # DTE 6-9
    df["dte"] = (pd.to_datetime(df["expiration"]) - pd.to_datetime(df["timestamp"])).dt.days
    df = df[(df["dte"] >= 6) & (df["dte"] <= 9)]

    # OTM bucket
    df["otm_pct"] = df["moneyness"].abs() * 100
    df["otm_bucket"] = pd.cut(df["otm_pct"], bins=OTM_BINS, labels=OTM_LABELS, include_lowest=True)

    # Dedup: one row per (date, strike, expiry)
    df = df.sort_values("timestamp")
    df = df.groupby(["quote_date", "strike", "expiration"]).last().reset_index()

    if df.empty:
        return None

    bucket_pnl = df.groupby("otm_bucket", observed=True)["pnl"].mean().dropna()
    if bucket_pnl.empty:
        return None
    best_bucket = bucket_pnl.idxmax()

    latest_price = (
        raw_df.sort_values("timestamp")["underlying_close"].iloc[-1]
    )

    # best pnl is avg pnl of best bucket
    best_bucket_avg_pnl = df[df["otm_bucket"] == best_bucket]["pnl"].mean()
    best_bucket_avg_pnl_pct = best_bucket_avg_pnl / latest_price * 100

    # avg bid/ask spread in best bucket. highest bid and lowest ask
    best_bucket_avg_spread = df[df["otm_bucket"] == best_bucket]["bid"].max() - df[df["otm_bucket"] == best_bucket]["ask"].min()
    best_bucket_avg_spread_pct = best_bucket_avg_spread / latest_price * 100

    out = {
        "ticker": ticker,
        "n_quotes": len(df),
        "avg_iv": f"{df['implied_vol'].mean() * 100:.0f}%",
        "best_bucket": best_bucket,
        "best_bucket_avg_pnl": f"${best_bucket_avg_pnl:.2f}",
        "best_bucket_avg_pnl_pct": f"{best_bucket_avg_pnl_pct:.2f}%",
        "best_bucket_avg_spread": f"${best_bucket_avg_spread:.2f}",
        "best_bucket_avg_spread_pct": f"{best_bucket_avg_spread_pct:.2f}%",
        "latest_price": f"${latest_price:.2f}",
    }
    return out

if __name__ == "__main__":
    paths = sorted(Path("data/raw/dataset").glob("*.parquet"))
    if not paths:
        print("No *.parquet files found in data/raw/dataset")
    else:
        rows = []
        with ThreadPoolExecutor(max_workers=18) as executor:
            futures = {executor.submit(_process_ticker, p): p for p in paths}
            with tqdm(total=len(paths), desc="Processing tickers") as pbar:
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        rows.append(result)
                    pbar.update(1)

        # save to csv
        df = pd.DataFrame(rows)
        df.to_csv("macro_summary.csv", index=False)

        print(df.to_string())
