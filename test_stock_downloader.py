#!/usr/bin/env python3
"""
Test script for YFinanceDownloader

Quick manual tests to verify stock price download functionality.
Run this script to validate the implementation.
"""

from pathlib import Path
import sys
from src.stock_downloader import YFinanceDownloader


def test_single_ticker_short_range():
    """Test 1: Single ticker, short date range."""
    print("\n" + "=" * 70)
    print("TEST 1: Single ticker, short range (AAPL, 1 week)")
    print("=" * 70)

    downloader = YFinanceDownloader()

    try:
        df = downloader.download_stock_prices('AAPL', '2024-01-15', '2024-01-19')

        # Validations
        assert len(df) >= 3, f"Expected at least 3 trading days, got {len(df)}"
        assert 'close' in df.columns, "Missing 'close' column"
        assert 'date' in df.columns, "Missing 'date' column"
        assert 'symbol' in df.columns, "Missing 'symbol' column"
        assert (df['symbol'] == 'AAPL').all(), "Incorrect symbol"

        print(f"✓ PASSED: Downloaded {len(df)} trading days")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
        return True

    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False


def test_incremental_download():
    """Test 2: Incremental download (extend existing date range)."""
    print("\n" + "=" * 70)
    print("TEST 2: Incremental download")
    print("=" * 70)

    downloader = YFinanceDownloader()
    output_dir = Path('data/raw')
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # First download: Jan 1-5
        print("\nStep 1: Download Jan 1-5...")
        df1 = downloader.download_stock_prices('AAPL', '2024-01-01', '2024-01-05')
        df1.to_csv(output_dir / 'AAPL_stock_prices.csv', index=False)
        print(f"  Downloaded {len(df1)} days")

        # Second download: Jan 1-10 (should only download 6-10)
        print("\nStep 2: Extend to Jan 1-10 (should only download new dates)...")
        df2 = downloader.download_stock_prices('AAPL', '2024-01-01', '2024-01-10')

        # Validations
        assert len(df2) > len(df1), f"Extended data should be larger: {len(df2)} vs {len(df1)}"

        print(f"✓ PASSED: Extended from {len(df1)} to {len(df2)} trading days")
        return True

    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False


def test_invalid_ticker():
    """Test 3: Invalid ticker (should fail gracefully)."""
    print("\n" + "=" * 70)
    print("TEST 3: Invalid ticker")
    print("=" * 70)

    downloader = YFinanceDownloader()

    try:
        df = downloader.download_stock_prices(
            'INVALID_TICKER_12345',
            '2024-01-01',
            '2024-01-05',
            check_existing=False
        )

        # Should either raise ValueError or return empty DataFrame
        if df.empty:
            print(f"✓ PASSED: Returned empty DataFrame for invalid ticker")
            return True
        else:
            print(f"✗ FAILED: Should have returned empty DataFrame or raised ValueError")
            return False

    except ValueError as e:
        print(f"✓ PASSED: Raised ValueError as expected: {e}")
        return True
    except Exception as e:
        print(f"✗ FAILED: Unexpected error: {e}")
        return False


def test_weekend_dates():
    """Test 4: Weekend/holiday dates (should return only trading days)."""
    print("\n" + "=" * 70)
    print("TEST 4: Weekend dates (should return only trading days)")
    print("=" * 70)

    downloader = YFinanceDownloader()

    try:
        # Jan 1, 2024 is a Monday (New Year's Day - market closed)
        # Jan 6-7 is a weekend
        # Should only get trading days
        df = downloader.download_stock_prices(
            'AAPL',
            '2024-01-01',
            '2024-01-07',
            check_existing=False
        )

        # Should have 3-4 trading days (Mon holiday, Tue-Fri trading, Sat-Sun weekend)
        assert len(df) >= 3, f"Expected at least 3 trading days, got {len(df)}"
        assert len(df) <= 5, f"Expected at most 5 trading days, got {len(df)}"

        print(f"✓ PASSED: Got {len(df)} trading days (filtered out weekends/holidays)")
        print(f"  Dates: {sorted(df['date'].tolist())}")
        return True

    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False


def test_full_year():
    """Test 5: Full year download (performance test)."""
    print("\n" + "=" * 70)
    print("TEST 5: Full year download (SCHW, 2024)")
    print("=" * 70)

    downloader = YFinanceDownloader()

    try:
        import time
        start_time = time.time()

        df = downloader.download_stock_prices(
            'SCHW',
            '2024-01-01',
            '2024-12-31',
            check_existing=False
        )

        elapsed = time.time() - start_time

        # Should have ~252 trading days per year
        assert len(df) >= 250, f"Expected at least 250 trading days, got {len(df)}"
        assert len(df) <= 260, f"Expected at most 260 trading days, got {len(df)}"

        print(f"✓ PASSED: Downloaded {len(df)} trading days in {elapsed:.2f} seconds")
        print(f"  Average: {elapsed/len(df)*1000:.1f} ms per day")
        return True

    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "#" * 70)
    print("# YFinanceDownloader Test Suite")
    print("#" * 70)

    results = []

    # Run all tests
    results.append(("Single ticker short range", test_single_ticker_short_range()))
    results.append(("Incremental download", test_incremental_download()))
    results.append(("Invalid ticker", test_invalid_ticker()))
    results.append(("Weekend dates", test_weekend_dates()))
    results.append(("Full year download", test_full_year()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
