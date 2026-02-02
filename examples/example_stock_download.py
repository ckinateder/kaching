#!/usr/bin/env python3
"""
Example: Download stock price data using YFinanceDownloader

This script demonstrates how to:
1. Download stock prices with automatic save (simple workflow)
2. Perform incremental updates
3. Use download-only for quick analysis (no save)
4. Use manual control with helper methods (advanced)
"""

from pathlib import Path
from src.downloaders.stock_downloader import YFinanceDownloader
from src.downloaders import find_missing_dates


def main():
    """Download stock prices for example tickers."""

    # Initialize downloader
    downloader = YFinanceDownloader()

    # Example 1: Simple download with auto-save
    print("=" * 60)
    print("Example 1: Download AAPL stock prices (1 month)")
    print("=" * 60)

    df_aapl = downloader.download(
        ticker='AAPL',
        start_date='2024-01-01',
        end_date='2024-01-31',
        save=True,
        csv_filepath='data/raw/AAPL_stock_prices.csv',
        incremental=True
    )

    print(f"\nDataFrame shape: {df_aapl.shape}")
    print(f"Columns: {list(df_aapl.columns)}")
    print(f"\nFirst few rows:")
    print(df_aapl.head())

    # Example 2: Download full year with auto-save
    print("\n" + "=" * 60)
    print("Example 2: Download SCHW stock prices (full year)")
    print("=" * 60)

    df_schw = downloader.download(
        ticker='SCHW',
        start_date='2024-01-01',
        end_date='2024-12-31',
        save=True,
        csv_filepath='data/raw/SCHW_stock_prices.csv',
        incremental=True
    )

    print(f"\nSummary statistics:")
    print(df_schw[['close']].describe())

    # Example 3: Incremental download (extend existing data)
    print("\n" + "=" * 60)
    print("Example 3: Incremental download (extend AAPL to Feb)")
    print("=" * 60)

    df_aapl_extended = downloader.download(
        ticker='AAPL',
        start_date='2024-01-01',
        end_date='2024-02-29',  # Extend into February
        save=True,
        csv_filepath='data/raw/AAPL_stock_prices.csv',
        incremental=True  # Will only download missing dates
    )

    print(f"\nTotal trading days: {len(df_aapl_extended)}")

    # Example 4: Download-only (no save) for quick analysis
    print("\n" + "=" * 60)
    print("Example 4: Download without saving (analysis only)")
    print("=" * 60)

    df_analysis = downloader.download(
        ticker='MSFT',
        start_date='2024-01-01',
        end_date='2024-01-31'
    )

    print(f"\nMSFT January 2024 Analysis:")
    print(f"  Trading days: {len(df_analysis)}")
    print(f"  Average close: ${df_analysis['close'].mean():.2f}")
    print(f"  Price range: ${df_analysis['close'].min():.2f} - ${df_analysis['close'].max():.2f}")
    print(f"  Total volume: {df_analysis['volume'].sum():,}")

    # Example 5: Manual control (advanced usage)
    print("\n" + "=" * 60)
    print("Example 5: Manual control with helper methods")
    print("=" * 60)

    # Check what dates are missing using the utility function directly
    existing_df, missing_dates = find_missing_dates(
        csv_filepath='data/raw/AAPL_stock_prices.csv',
        start_date='2024-01-01',
        end_date='2024-03-31',
        date_column='date',
        parse_timestamp=False
    )

    print(f"Found {len(missing_dates)} missing dates")

    if missing_dates:
        # Download only the missing data
        print(f"Downloading missing dates: {missing_dates[0]} to {missing_dates[-1]}")
        new_df = downloader.download(
            ticker='AAPL',
            start_date=missing_dates[0],
            end_date=missing_dates[-1]
        )

        # Filter to only actually missing dates (removes weekends/holidays)
        new_df = new_df[new_df['date'].isin(missing_dates)]

        # Merge with existing data
        complete_df = YFinanceDownloader.merge_stock_data(existing_df, new_df)

        # Save manually
        complete_df.to_csv('data/raw/AAPL_stock_prices.csv', index=False)
        print(f"✓ Merged and saved {len(complete_df):,} total trading days")
    else:
        print("No missing dates - all data already exists")

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == '__main__':
    main()
