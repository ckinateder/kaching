#!/usr/bin/env python3
"""
Example: Download stock price data using YFinanceDownloader

This script demonstrates how to download daily stock prices for use in
options analysis (calculating OTM% and P&L).
"""

from pathlib import Path
from src.stock_downloader import YFinanceDownloader


def main():
    """Download stock prices for example tickers."""

    # Initialize downloader
    downloader = YFinanceDownloader()

    # Create output directory if it doesn't exist
    output_dir = Path('data/raw')
    output_dir.mkdir(parents=True, exist_ok=True)

    # Example 1: Download 1 month of AAPL stock prices
    print("=" * 60)
    print("Example 1: Download AAPL stock prices (1 month)")
    print("=" * 60)

    df_aapl = downloader.download_stock_prices(
        ticker='AAPL',
        start_date='2024-01-01',
        end_date='2024-01-31',
        output_dir=str(output_dir),
        check_existing=True
    )

    # Save to CSV
    output_path = output_dir / 'AAPL_stock_prices.csv'
    df_aapl.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    print(f"Columns: {list(df_aapl.columns)}")
    print(f"\nFirst few rows:")
    print(df_aapl.head())

    # Example 2: Download full year of SCHW stock prices
    print("\n" + "=" * 60)
    print("Example 2: Download SCHW stock prices (full year)")
    print("=" * 60)

    df_schw = downloader.download_stock_prices(
        ticker='SCHW',
        start_date='2024-01-01',
        end_date='2024-12-31',
        output_dir=str(output_dir),
        check_existing=True
    )

    # Save to CSV
    output_path = output_dir / 'SCHW_stock_prices.csv'
    df_schw.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    print(f"\nSummary statistics:")
    print(df_schw[['close']].describe())

    # Example 3: Incremental download (extend existing data)
    print("\n" + "=" * 60)
    print("Example 3: Incremental download (extend AAPL to Feb)")
    print("=" * 60)

    df_aapl_extended = downloader.download_stock_prices(
        ticker='AAPL',
        start_date='2024-01-01',
        end_date='2024-02-29',  # Extend into February
        output_dir=str(output_dir),
        check_existing=True  # Will only download missing dates
    )

    # Save updated data
    output_path = output_dir / 'AAPL_stock_prices.csv'
    df_aapl_extended.to_csv(output_path, index=False)
    print(f"\nSaved extended data to: {output_path}")
    print(f"Total trading days: {len(df_aapl_extended)}")

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == '__main__':
    main()
