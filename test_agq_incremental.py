"""
Quick test of incremental download improvements with AGQ.
"""

from src.downloaders import DatasetDownloader

# Test with AGQ - should use incremental mode
downloader = DatasetDownloader(max_workers=4, rate_limit_delay=0.15)

print("Testing incremental download for AGQ...")
print("This should skip existing data and only download missing ranges.\n")

df = downloader.download(
    ticker='AGQ',
    start_date='2021-01-01',
    end_date='2024-12-31',
    save=True,
    filepath='data/raw/AGQ_dataset.parquet',
    incremental=True  # Will check existing file and only download gaps
)

print(f"\n{'='*60}")
print(f"Final Result:")
print(f"  Total records: {len(df):,}")
if not df.empty:
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Unique expirations: {df['expiration'].nunique()}")
print(f"{'='*60}")
