"""
Test script to demonstrate concurrent downloading.

This script compares sequential vs concurrent download performance.
"""

import time
from src.downloaders import ThetaDataDownloader

def test_concurrent_download():
    """Test concurrent download mode."""

    # Small date range for quick testing
    ticker = 'AAPL'
    start_date = '2024-01-02'  # First trading day of 2024
    end_date = '2024-01-10'    # 10 days (about 7-8 trading days)

    print("=" * 60)
    print("Testing Concurrent Download Performance")
    print("=" * 60)

    # Test 1: Sequential mode (max_workers=1)
    print("\n[Test 1] Sequential mode (max_workers=1)")
    print("-" * 60)
    downloader_seq = ThetaDataDownloader(max_workers=1)

    start_time = time.time()
    df_seq = downloader_seq.download(ticker, start_date, end_date)
    seq_time = time.time() - start_time

    print(f"\nSequential time: {seq_time:.2f}s")

    # Test 2: Concurrent mode (max_workers=8)
    print("\n" + "=" * 60)
    print("[Test 2] Concurrent mode (max_workers=8)")
    print("-" * 60)
    downloader_conc = ThetaDataDownloader(max_workers=8)

    start_time = time.time()
    df_conc = downloader_conc.download(ticker, start_date, end_date)
    conc_time = time.time() - start_time

    print(f"\nConcurrent time: {conc_time:.2f}s")

    # Results
    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)
    print(f"Sequential time:  {seq_time:.2f}s")
    print(f"Concurrent time:  {conc_time:.2f}s")
    if conc_time > 0:
        speedup = seq_time / conc_time
        print(f"Speedup:          {speedup:.1f}x")

    # Verify same data
    print(f"\nSequential rows:  {len(df_seq):,}")
    print(f"Concurrent rows:  {len(df_conc):,}")

    if len(df_seq) == len(df_conc):
        print("✓ Both modes returned same number of rows")
    else:
        print("⚠ Warning: Different row counts")

    print("\n" + "=" * 60)

if __name__ == '__main__':
    test_concurrent_download()
