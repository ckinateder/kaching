from src.downloaders.dataset_downloader import download_full_dataset

if __name__ == "__main__":
    options_df, stock_df = download_full_dataset(
        ticker='TTD',
        start_date='2023-01-01',
        end_date='2025-12-31',
        output_dir='data/raw',
        check_existing=True
    )

    # print size of data by row and then by bytes
    options_df.info()
    stock_df.info()