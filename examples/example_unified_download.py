#!/usr/bin/env python3
"""
Example: Unified download interface demonstration

This script demonstrates the unified download() method available on all downloaders:
1. Download-only mode (save=False) - returns DataFrame without saving
2. Download-and-save mode (save=True) - downloads and saves to Parquet
3. Incremental downloads - only fetch missing dates
4. Parameter validation - proper error handling
5. DatasetDownloader - combined options + stock data

All downloaders now use the same consistent API.
"""

from pathlib import Path
from src import (
    ThetaDataDownloader,
    YFinanceDownloader,
    DatasetDownloader
)


def main():
    """Demonstrate unified download interface across all downloaders."""

    # Example 1: Download-only mode (no save) - All downloaders
    print("=" * 70)
    print("Example 1: Download-only mode (returns DataFrame, no save)")
    print("=" * 70)

    # Options downloader
    print("\n[Options] Download 1 day of AAPL options data (no save):")
    options_dl = ThetaDataDownloader()
    df_options = options_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-02'
    )
    print(f"✓ Downloaded {len(df_options):,} contracts (not saved)")

    # Stock downloader
    print("\n[Stock] Download 1 week of AAPL stock prices (no save):")
    stock_dl = YFinanceDownloader()
    df_stock = stock_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-05'
    )
    print(f"✓ Downloaded {len(df_stock)} trading days (not saved)")

    # Dataset downloader
    print("\n[Dataset] Download combined data (no save):")
    dataset_dl = DatasetDownloader()
    df_combined = dataset_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-02'
    )
    print(f"✓ Downloaded {len(df_combined):,} combined records (not saved)")

    # Example 2: Download-and-save mode with incremental
    print("\n" + "=" * 70)
    print("Example 2: Download-and-save mode (save=True, incremental=True)")
    print("=" * 70)

    # Create test output directory
    test_dir = Path('data/test')
    test_dir.mkdir(parents=True, exist_ok=True)

    print("\n[Options] Download and save with incremental:")
    df_opt_saved = options_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-05',
        save=True,
        filepath='data/test/AAPL_options_unified.parquet',
        incremental=True
    )
    print(f"✓ Saved {len(df_opt_saved):,} contracts to Parquet")

    print("\n[Stock] Download and save with incremental:")
    df_stock_saved = stock_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-31',
        save=True,
        filepath='data/test/AAPL_stock_unified.parquet',
        incremental=True
    )
    print(f"✓ Saved {len(df_stock_saved)} trading days to Parquet")

    print("\n[Dataset] Download and save combined data:")
    df_dataset_saved = dataset_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-02',
        save=True,
        filepath='data/test/AAPL_dataset_unified.parquet',
        incremental=True
    )
    print(f"✓ Saved {len(df_dataset_saved):,} combined records to Parquet")

    # Example 3: Incremental update demonstration
    print("\n" + "=" * 70)
    print("Example 3: Incremental update (extend existing data)")
    print("=" * 70)

    print("\n[Stock] Extending date range (incremental=True will skip existing):")
    df_extended = stock_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-02-29',  # Extended range
        save=True,
        filepath='data/test/AAPL_stock_unified.parquet',
        incremental=True  # Will only download missing dates
    )
    print(f"✓ Now have {len(df_extended)} total trading days (only new dates downloaded)")

    # Example 4: Non-incremental download (full re-download)
    print("\n" + "=" * 70)
    print("Example 4: Non-incremental download (full re-download)")
    print("=" * 70)

    print("\n[Stock] Re-download entire range (incremental=False):")
    df_full = stock_dl.download(
        ticker='MSFT',
        start_date='2024-01-02',
        end_date='2024-01-31',
        save=True,
        filepath='data/test/MSFT_stock_full.parquet',
        incremental=False  # Re-downloads everything
    )
    print(f"✓ Downloaded and saved {len(df_full)} trading days (full re-download)")

    # Example 5: Parameter validation
    print("\n" + "=" * 70)
    print("Example 5: Parameter validation (error handling)")
    print("=" * 70)

    print("\n[Validation] Trying save=True without filepath:")
    try:
        df_error = stock_dl.download(
            ticker='AAPL',
            start_date='2024-01-02',
            end_date='2024-01-05',
            save=True  # ERROR: filepath required when save=True
        )
        print("✗ ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"✓ Validation works correctly: {e}")

    print("\n[Validation] filepath provided but save=False (should work, filepath ignored):")
    df_ignored = stock_dl.download(
        ticker='AAPL',
        start_date='2024-01-02',
        end_date='2024-01-05',
        save=False,  # filepath will be ignored
        filepath='data/test/ignored.parquet'
    )
    print(f"✓ Works correctly: {len(df_ignored)} days downloaded, filepath ignored")
    print(f"✓ File was NOT created: {not Path('data/test/ignored.parquet').exists()}")

    # Example 6: Quick analysis workflow
    print("\n" + "=" * 70)
    print("Example 6: Quick analysis workflow (download-only)")
    print("=" * 70)

    print("\n[Analysis] Analyze MSFT options for single day:")
    df_analysis = options_dl.download(
        ticker='MSFT',
        start_date='2024-01-02',
        end_date='2024-01-02'
    )

    print(f"\nMSFT Options Analysis (2024-01-02):")
    print(f"  Total contracts: {len(df_analysis):,}")
    print(f"  Unique expirations: {df_analysis['expiration'].nunique()}")
    print(f"  Strike range: ${df_analysis['strike'].min():.2f} - ${df_analysis['strike'].max():.2f}")
    print(f"  Average implied vol: {df_analysis['implied_vol'].mean():.2%}")
    print(f"  Puts vs Calls: {df_analysis['right'].value_counts().to_dict()}")

    # Summary
    print("\n" + "=" * 70)
    print("Summary: Unified Download Interface")
    print("=" * 70)
    print("\nAll downloaders now use the same API:")
    print("  • download(ticker, start_date, end_date) - download-only")
    print("  • download(..., save=True, filepath='...') - download and save")
    print("  • download(..., incremental=True) - only fetch missing dates")
    print("\nConsistent behavior across:")
    print("  • ThetaDataDownloader (options data)")
    print("  • YFinanceDownloader (stock prices)")
    print("  • DatasetDownloader (combined options + stock)")
    print("\n✓ All examples completed successfully!")
    print("=" * 70)


if __name__ == '__main__':
    main()
