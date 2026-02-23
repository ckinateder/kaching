import os

import matplotlib.pyplot as plt
import pandas as pd

from src.postprocess import add_moneyness, add_pnl, add_price_at_expiry


if __name__ == "__main__":
    ticker = "TTD"
    moneyness_threshold = (-0.2, 0)

    raw_df = pd.read_parquet(os.path.join("data", "raw", f"{ticker}_dataset.parquet"))
    funnel = [("raw", len(raw_df))]

    # Exclude rows where yfinance (split-adjusted) and Theta prices are on different scales
    ratio = raw_df["underlying_price"] / raw_df["underlying_close"]
    raw_df = raw_df[(ratio > 0.9) & (ratio < 1.1)]
    funnel.append(("split ratio filter", len(raw_df)))

    df = add_moneyness(raw_df)
    df = add_price_at_expiry(df)
    df = add_pnl(df)
    df = df[df["right"] == "PUT"]
    funnel.append(("PUT only", len(df)))

    df = df[
        (df["moneyness"] < moneyness_threshold[1])
        & (df["moneyness"] > moneyness_threshold[0])
    ]
    funnel.append((f"moneyness {moneyness_threshold[0]*100:.0f}% to 0% OTM", len(df)))

    df = df[df["bid"] > 0]  # no market bid = untradeable
    funnel.append(("bid > 0", len(df)))

    df["otm_pct"] = abs(df["moneyness"]) * 100

    # Day of week filter: Thu/Fri entries only
    df["quote_date"] = pd.to_datetime(df["timestamp"]).dt.date
    df["day_of_week"] = pd.to_datetime(df["timestamp"]).dt.dayofweek
    df = df[df["day_of_week"].isin([3, 4])]  # Thursday=3, Friday=4
    funnel.append(("Thu/Fri only", len(df)))

    # DTE filter: target next-week expiry (7-8 days out)
    df["expiration_date"] = pd.to_datetime(df["expiration"])
    df["dte"] = (df["expiration_date"] - pd.to_datetime(df["timestamp"])).dt.days
    df = df[(df["dte"] >= 6) & (df["dte"] <= 9)] # 6-9 days out
    funnel.append(("DTE 6-9", len(df)))

    # OTM buckets in 0.5% increments
    df["otm_bucket"] = pd.cut(
        df["otm_pct"],
        bins=[0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
        labels=[
            "0.0-0.5%",
            "0.5-1.0%",
            "1.0-1.5%",
            "1.5-2.0%",
            "2.0-2.5%",
            "2.5-3.0%",
            "3.0-3.5%",
            "3.5-4.0%",
            "4.0-4.5%",
            "4.5-5.0%",
        ],
        include_lowest=True,
    )

    # Dedup: one row per (date, strike, expiry) — keep last quote of the day
    df = df.sort_values("timestamp")
    df = df.groupby(["quote_date", "strike", "expiration"]).last().reset_index()
    funnel.append(("dedup", len(df)))

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

    # 6. Stock price over full period (one point per calendar date, pre-filter)
    stock_by_date = (
        raw_df.groupby(pd.to_datetime(raw_df["timestamp"]).dt.date)["underlying_close"]
        .first()
        .sort_index()
    )
    stock_by_date.plot(ax=axes[1, 2], color="black", linewidth=0.8)
    axes[1, 2].set_title("Stock Price (Full Period)")
    axes[1, 2].set_ylabel("Price ($)")

    date_range = f"{df['quote_date'].min()} to {df['quote_date'].max()}"
    fig.suptitle(f"{ticker}  |  {date_range}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join("img", f"{ticker}_bucket_analysis.png"), dpi=150)
