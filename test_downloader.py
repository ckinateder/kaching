"""
Quick test script to verify ThetaDataDownloader works correctly.

Tests with a single day of data for fast verification.
"""

from src.data_downloader import ThetaDataDownloader
import pandas as pd


def test_single_day():
    """Test downloading a single day of data."""
    print("=" * 60)
    print("Test: Download single day of AAPL options data")
    print("=" * 60)

    downloader = ThetaDataDownloader()

    # Download just one day for quick test
    df = downloader.download_options_eod_data(
        ticker='AAPL',
        start_date='2024-11-04',  # Date from API spec example
        end_date='2024-11-04',
        output_dir='data/raw',
        check_existing=False  # Don't check existing for test
    )

    # Verify results
    print("\n" + "=" * 60)
    print("Test Results:")
    print("=" * 60)

    if df.empty:
        print("✗ FAILED: DataFrame is empty")
        return False

    print(f"✓ Downloaded {len(df)} contracts")
    print(f"✓ Columns: {len(df.columns)}")
    print(f"\nColumn names:")
    for col in df.columns:
        print(f"  - {col}")

    # Check for required columns
    required = ['symbol', 'expiration', 'strike', 'right', 'timestamp', 'bid', 'ask']
    missing = [col for col in required if col not in df.columns]

    if missing:
        print(f"\n✗ FAILED: Missing required columns: {missing}")
        return False

    print(f"\n✓ All required columns present")

    # Show sample data
    print(f"\nSample data (first 5 rows):")
    print(df.head())

    # Show data types
    print(f"\nData types:")
    print(df.dtypes)

    # Show basic stats
    print(f"\nBasic statistics:")
    print(f"  Unique expirations: {df['expiration'].nunique()}")
    print(f"  Strike range: ${df['strike'].min():.2f} - ${df['strike'].max():.2f}")
    if 'right' in df.columns:
        print(f"  Calls: {(df['right'] == 'CALL').sum()}, Puts: {(df['right'] == 'PUT').sum()}")

    print("\n✓ Test PASSED!")
    return True


def test_incremental_download():
    """Test incremental download functionality."""
    print("\n" + "=" * 60)
    print("Test: Incremental download")
    print("=" * 60)

    downloader = ThetaDataDownloader()

    # First download
    print("\nStep 1: Initial download (2 days)")
    df1 = downloader.download_options_eod_data(
        ticker='TEST_TICKER',
        start_date='2024-11-04',
        end_date='2024-11-05',
        output_dir='data/raw',
        check_existing=False
    )

    # Save to CSV
    csv_path = 'data/raw/TEST_TICKER_options_eod.csv'
    df1.to_csv(csv_path, index=False)
    print(f"✓ Saved {len(df1)} contracts to {csv_path}")

    # Second download with overlapping dates
    print("\nStep 2: Extended download (should only fetch new dates)")
    df2 = downloader.download_options_eod_data(
        ticker='TEST_TICKER',
        start_date='2024-11-04',
        end_date='2024-11-06',
        output_dir='data/raw',
        check_existing=True  # Should detect existing data
    )

    print(f"\n✓ Incremental download test completed")
    print(f"  Initial: {len(df1)} contracts")
    print(f"  After update: {len(df2)} contracts")

    # Cleanup test file
    import os
    if os.path.exists(csv_path):
        os.remove(csv_path)
        print(f"\n✓ Cleaned up test file")

    return True


def main():
    """Run all tests."""
    print("\nThetaDataDownloader Test Suite")
    print("=" * 60)

    try:
        # Test 1: Single day download
        if not test_single_day():
            print("\n✗ Single day test failed!")
            return

        # Test 2: Incremental download (commented out by default)
        # Uncomment to test incremental download functionality
        # if not test_incremental_download():
        #     print("\n✗ Incremental download test failed!")
        #     return

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
