"""
Example script demonstrating how to use the ThetaDataDownloader.

This script shows how to:
1. Download options data for a single ticker
2. Save the data to CSV
3. Perform incremental updates
"""

from src.downloaders.options_downloader import ThetaDataDownloader
import pandas as pd


def main():
    # Initialize downloader (no API key needed for localhost Theta Terminal)
    downloader = ThetaDataDownloader()

    # Example 1: Download 1 week of data for testing
    print("=" * 60)
    print("Example 1: Download 1 week of AAPL options data")
    print("=" * 60)

    df = downloader.download_options_eod_data(
        ticker='AAPL',
        start_date='2024-01-15',
        end_date='2024-01-19',
        output_dir='data/raw',
        check_existing=True
    )

    # Save to CSV
    output_path = 'data/raw/AAPL_options_eod.csv'
    df.to_csv(output_path, index=False)
    print(f"\n✓ Saved to {output_path}")

    # Example 2: Incremental update (download additional dates)
    print("\n" + "=" * 60)
    print("Example 2: Incremental update with new dates")
    print("=" * 60)

    df_updated = downloader.download_options_eod_data(
        ticker='AAPL',
        start_date='2024-01-15',
        end_date='2024-02-26',  # Extended range
        output_dir='data/raw',
        check_existing=True  # Will only download missing dates
    )

    # Save updated data
    df_updated.to_csv(output_path, index=False)
    print(f"\n✓ Updated and saved to {output_path}")

    # display sample of data
    data = pd.read_csv(output_path)

    # Display sample of data
    print("\nSample data:")
    print(data.head(10))

    # print size of data by row and then by bytes
    data.info()


    # Example 3: Full year download (commented out - uncomment to run)
    # print("\n" + "=" * 60)
    # print("Example 3: Download full year of SCHW options data")
    # print("=" * 60)
    #
    # df_full = downloader.download_options_eod_data(
    #     ticker='SCHW',
    #     start_date='2024-01-01',
    #     end_date='2024-12-31',
    #     output_dir='data/raw',
    #     check_existing=True
    # )
    #
    # df_full.to_csv('data/raw/SCHW_options_eod.csv', index=False)
    # print(f"\n✓ Saved full year data")


if __name__ == '__main__':
    main()
