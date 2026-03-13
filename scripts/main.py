import sys
from pathlib import Path

import __init__

import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd

from src.postprocess import OTM_BINS, OTM_LABELS, filter_weekly_put_options

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze options data for a given ticker")
    parser.add_argument("--ticker", type=str, help="Stock ticker symbol (e.g., DECK, AAPL)")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    moneyness_threshold = (-0.2, 0)

    raw_df = pd.read_parquet(os.path.join("data", "raw", "dataset", f"{ticker}.parquet"))
    
    # Apply all filters using shared function
    df, funnel = filter_weekly_put_options(raw_df, moneyness_threshold)

    print("=== ROW FUNNEL ===")
    for i, (label, n) in enumerate(funnel):
        if i == 0:
            print(f"  {'raw':<35} {n:>10,}")
        else:
            prev = funnel[i - 1][1]
            drop = n - prev
            pct = drop / prev * 100 if prev else 0
            print(f"  {label:<35} {n:>10,}   {drop:>+10,}  ({pct:+.0f}%)")
    print()

    # save filtered df to csv
    df.to_csv(os.path.join("data", "processed", f"{ticker}_filtered_dataset.csv"), index=False)

    print(f"Date range: {df['quote_date'].min()} to {df['quote_date'].max()}")
    print("\nDTE distribution:")
    print(df["dte"].value_counts().sort_index())

    print("\n=== BUCKET OVERVIEW ===")
    print(f"Total records: {len(df):,}")
    print(f"\nRecords per OTM bucket:")
    print(df["otm_bucket"].value_counts().sort_index())

    print("\n=== BASIC STATS PER BUCKET ===")
    bucket_stats = (
        df.groupby("otm_bucket", observed=True)
        .agg(
            {
                "pnl": [
                    "count",
                    "mean",
                    "std",
                    lambda x: x.quantile(0.05),
                    "median",
                    lambda x: x.quantile(0.95),
                ],
                "win": "mean",
                "bid": "mean",
            }
        )
        .round(3)
    )
    bucket_stats.columns = [
        "count",
        "avg_pnl",
        "std_pnl",
        "p5_pnl",
        "median_pnl",
        "p95_pnl",
        "win_rate",
        "avg_premium",
    ]
    print(bucket_stats)

    print("\n=== SAMPLE TRADES FROM 1.0-1.5% BUCKET ===")
    sample_bucket = df[df["otm_bucket"] == "1.0-1.5%"].head(10)
    print(
        sample_bucket[
            [
                "quote_date",
                "strike",
                "underlying_close",
                "otm_pct",
                "bid",
                "close_at_expiry",
                "pnl",
                "win",
            ]
        ]
    )

    fig, axes = plt.subplots(2, 3, figsize=(21, 10))

    # 2. Win rate by bucket, annotated with avg IV%
    win_by_bucket = df.groupby("otm_bucket", observed=True)["win"].mean()
    iv_by_bucket = df.groupby("otm_bucket", observed=True)["implied_vol"].mean()
    win_by_bucket.plot(kind="bar", ax=axes[0, 0], color="green")
    axes[0, 0].set_title("Win Rate by OTM Bucket")
    axes[0, 0].set_ylabel("Win Rate")
    axes[0, 0].axhline(y=0.5, color="r", linestyle="--", label="50%")
    for i, (bar, iv) in enumerate(zip(axes[0, 0].patches, iv_by_bucket)):
        axes[0, 0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"IV {iv*100:.0f}%",
            ha="center", va="bottom", fontsize=7, color="gray",
        )

    # 1. OTM% distribution
    df["otm_pct"].hist(bins=50, ax=axes[0, 1])
    axes[0, 1].set_title("OTM% Distribution")
    axes[0, 1].set_xlabel("OTM %")
    axes[0, 1].set_ylabel("Count")


    # 3. P&L distribution for one bucket
    bucket_2_2p5 = df[df["otm_bucket"] == "2.0-2.5%"]["pnl"]
    bucket_2_2p5.hist(bins=30, ax=axes[0, 2])
    axes[0, 2].set_title("P&L Distribution: 2.0-2.5% OTM Bucket")
    axes[0, 2].axvline(x=0, color="r", linestyle="--", label="Break-even")
    axes[0, 2].axvline(
        x=bucket_2_2p5.mean(),
        color="g",
        linestyle="--",
        label=f"Mean: ${bucket_2_2p5.mean():.2f}",
    )
    axes[0, 2].legend()

    # 4. Expected value by bucket
    df.groupby("otm_bucket", observed=True)["pnl"].mean().plot(
        kind="bar", ax=axes[1, 0], color="blue"
    )
    axes[1, 0].set_title("Expected P&L by OTM Bucket")
    axes[1, 0].set_ylabel("Expected P&L ($)")
    axes[1, 0].axhline(y=0, color="r", linestyle="--")

    # 5. Quote date histogram
    pd.to_datetime(df["quote_date"]).hist(bins=40, ax=axes[1, 1], color="steelblue")
    axes[1, 1].set_title("Quote Date Distribution")
    axes[1, 1].set_xlabel("Date")
    axes[1, 1].set_ylabel("Count")

    # 6. Stock price over analysis period (quote_date range)
    analysis_start = df["quote_date"].min()
    analysis_end = df["quote_date"].max()
    
    stock_by_date = (
        raw_df.groupby(pd.to_datetime(raw_df["timestamp"]).dt.date)["underlying_close"]
        .first()
        .sort_index()
    )
    # Filter to only dates within the analysis period
    stock_by_date = stock_by_date.loc[analysis_start:analysis_end]
    
    stock_by_date.plot(ax=axes[1, 2], color="black", linewidth=0.8)
    axes[1, 2].set_title(f"Stock Price ({analysis_start} to {analysis_end})")
    axes[1, 2].set_ylabel("Price ($)")

    date_range = f"{df['quote_date'].min()} to {df['quote_date'].max()}"
    fig.suptitle(f"{ticker}  |  {date_range}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join("img", f"{ticker}_bucket_analysis.png"), dpi=150)
