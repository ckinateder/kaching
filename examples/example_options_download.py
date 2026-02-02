"""
Example script demonstrating how to use the ThetaDataDownloader.

This script shows how to:
1. Download options data with automatic save (simple workflow)
2. Perform incremental updates
3. Use manual control with helper methods (advanced)
"""

from src.downloaders.options_downloader import ThetaDataDownloader
import pandas as pd


def main():
    # Initialize downloader (no API key needed for localhost Theta Terminal)
    downloader = ThetaDataDownloader()

    # Example 1: Simple download with auto-save
    print("=" * 60)
    print("Example 1: Download 1 week of AAPL options data")
    print("=" * 60)

    df = downloader.download(
        ticker='AAPL',
        start_date='2024-01-15',
        end_date='2024-01-19',
        save=True,
        csv_filepath='data/raw/AAPL_options_eod.csv',
        incremental=True
    )

    print(f"\nDataFrame shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")

    # Example 2: Incremental update (download additional dates)
    print("\n" + "=" * 60)
    print("Example 2: Incremental update with new dates")
    print("=" * 60)

    df_updated = downloader.download(
        ticker='AAPL',
        start_date='2024-01-15',
        end_date='2024-02-26',  # Extended range
        save=True,
        csv_filepath='data/raw/AAPL_options_eod.csv',
        incremental=True  # Will only download missing dates
    )

    # Display sample of data
    print("\nSample data:")
    print(df_updated.head(10))

    # Print size info
    df_updated.info()

    # Example 3: Manual control (advanced usage)
    print("\n" + "=" * 60)
    print("Example 3: Manual control with helper methods")
    print("=" * 60)

    # Check what dates are missing
    existing_df, missing_dates = ThetaDataDownloader.find_missing_dates(
        csv_filepath='data/raw/AAPL_options_eod.csv',
        start_date='2024-01-01',
        end_date='2024-01-31'
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

        # Merge with existing data
        complete_df = ThetaDataDownloader.merge_options_data(existing_df, new_df)

        # Save manually
        complete_df.to_csv('data/raw/AAPL_options_eod.csv', index=False)
        print(f"✓ Merged and saved {len(complete_df):,} total contracts")
    else:
        print("No missing dates - all data already exists")

    # Example 4: Download-only (no save) for quick analysis
    print("\n" + "=" * 60)
    print("Example 4: Download without saving (analysis only)")
    print("=" * 60)

    df_analysis = downloader.download(
        ticker='MSFT',
        start_date='2024-01-02',
        end_date='2024-01-02'
    )

    print(f"\nAnalyzing {len(df_analysis):,} MSFT contracts for 2024-01-02:")
    print(f"  Unique expirations: {df_analysis['expiration'].nunique()}")
    print(f"  Strike range: ${df_analysis['strike'].min():.2f} - ${df_analysis['strike'].max():.2f}")
    print(f"  Average implied vol: {df_analysis['implied_vol'].mean():.2%}")


    # Example 5: Full year download (commented out - uncomment to run)
    # print("\n" + "=" * 60)
    # print("Example 5: Download full year of SCHW options data")
    # print("=" * 60)
    #
    # df_full = downloader.download(
    #     ticker='SCHW',
    #     start_date='2024-01-01',
    #     end_date='2024-12-31',
    #     save=True,
    #     csv_filepath='data/raw/SCHW_options_eod.csv',
    #     incremental=True
    # )
    #
    # print(f"\n✓ Saved full year data: {len(df_full):,} contracts")


if __name__ == '__main__':
    main()
