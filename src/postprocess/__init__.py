"""
Moneyness calculation utilities for options data analysis.

This module provides functions to calculate moneyness metrics for options contracts,
which help determine whether an option is in-the-money (ITM), at-the-money (ATM),
or out-of-the-money (OTM).

Moneyness Classification:
- Call Option:
  - ITM: S > K (Underlying Price > Strike Price)
  - ATM: S = K (Underlying Price = Strike Price)
  - OTM: S < K (Underlying Price < Strike Price)
  - Intrinsic Value: max(0, S - K)

- Put Option:
  - ITM: K > S (Strike Price > Underlying Price)
  - ATM: K = S (Strike Price = Underlying Price)
  - OTM: K < S (Strike Price < Underlying Price)
  - Intrinsic Value: max(0, K - S)
"""

import pandas as pd
import numpy as np


def add_moneyness(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add moneyness classification and intrinsic value columns to options DataFrame.
    
    Calculates moneyness status (ITM/ATM/OTM) and intrinsic value based on option type:
    - For CALL options: ITM when S > K, ATM when S = K, OTM when S < K
    - For PUT options: ITM when K > S, ATM when K = S, OTM when K < S
    
    Args:
        df: DataFrame with 'strike', 'underlying_price', and 'right' columns.
            'right' column should contain 'CALL' or 'PUT' values.
        
    Returns:
        New DataFrame with 'moneyness_status', 'intrinsic_value', and 'moneyness' columns added.
        - 'moneyness_status': Categorical classification ('ITM', 'ATM', or 'OTM')
        - 'intrinsic_value': Intrinsic value of the option (max(0, S-K) for calls, max(0, K-S) for puts)
        - 'moneyness': Numeric moneyness ratio (strike - underlying_price) / underlying_price
                       (negative for OTM puts, positive for ITM puts)
        Original DataFrame is not modified.
        
    Raises:
        ValueError: If required columns are missing
        
    Examples:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'strike': [100, 105, 95, 100, 105, 95],
        ...     'underlying_price': [100, 100, 100, 100, 100, 100],
        ...     'right': ['CALL', 'CALL', 'CALL', 'PUT', 'PUT', 'PUT']
        ... })
        >>> result = add_moneyness(df)
        >>> result[['right', 'moneyness_status', 'intrinsic_value']]
           right moneyness_status  intrinsic_value
        0  CALL              ATM             0.0
        1  CALL              OTM             0.0
        2  CALL              ITM             5.0
        3   PUT              ATM             0.0
        4   PUT              ITM             5.0
        5   PUT              OTM             0.0
    """
    # Validate required columns exist
    required_cols = ['strike', 'underlying_price', 'right']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. "
            f"DataFrame must contain 'strike', 'underlying_price', and 'right' columns."
        )
    
    # Create a copy to avoid modifying the original DataFrame
    result_df = df.copy()
    
    # Handle missing values and zero prices
    strike = result_df['strike'].astype(float)
    underlying_price_clean = result_df['underlying_price'].replace(0, np.nan).astype(float)
    right = result_df['right'].str.upper()
    
    # Initialize columns with proper dtypes
    result_df['moneyness_status'] = pd.Series([None] * len(result_df), dtype='object')
    result_df['intrinsic_value'] = np.nan
    
    # Calculate numeric moneyness: (strike - underlying_price) / underlying_price
    # This provides backward compatibility and is useful for filtering
    # For puts: negative = OTM, positive = ITM
    # For calls: negative = ITM, positive = OTM
    result_df['moneyness'] = (strike - underlying_price_clean) / underlying_price_clean
    
    # Tolerance for floating-point comparison (for ATM detection)
    tolerance = 1e-6
    
    # Calculate for CALL options
    call_mask = right == 'CALL'
    if call_mask.any():
        call_strike = strike[call_mask]
        call_underlying = underlying_price_clean[call_mask]
        
        # Call: ITM when S > K, ATM when S = K, OTM when S < K
        # Intrinsic value: max(0, S - K)
        call_intrinsic = np.maximum(0, call_underlying - call_strike)
        result_df.loc[call_mask, 'intrinsic_value'] = call_intrinsic
        
        # Classify moneyness for calls (using tolerance for ATM)
        call_diff = call_underlying - call_strike
        call_itm = call_diff > tolerance
        call_atm = np.abs(call_diff) <= tolerance
        call_otm = call_diff < -tolerance
        
        result_df.loc[call_mask & call_itm, 'moneyness_status'] = 'ITM'
        result_df.loc[call_mask & call_atm, 'moneyness_status'] = 'ATM'
        result_df.loc[call_mask & call_otm, 'moneyness_status'] = 'OTM'
    
    # Calculate for PUT options
    put_mask = right == 'PUT'
    if put_mask.any():
        put_strike = strike[put_mask]
        put_underlying = underlying_price_clean[put_mask]
        
        # Put: ITM when K > S, ATM when K = S, OTM when K < S
        # Intrinsic value: max(0, K - S)
        put_intrinsic = np.maximum(0, put_strike - put_underlying)
        result_df.loc[put_mask, 'intrinsic_value'] = put_intrinsic
        
        # Classify moneyness for puts (using tolerance for ATM)
        put_diff = put_strike - put_underlying
        put_itm = put_diff > tolerance
        put_atm = np.abs(put_diff) <= tolerance
        put_otm = put_diff < -tolerance
        
        result_df.loc[put_mask & put_itm, 'moneyness_status'] = 'ITM'
        result_df.loc[put_mask & put_atm, 'moneyness_status'] = 'ATM'
        result_df.loc[put_mask & put_otm, 'moneyness_status'] = 'OTM'
    
    return result_df


def add_price_at_expiry(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add close_at_expiry column with stock price on expiration date.

    Args:
        df: DataFrame with 'expiration' and stock price columns
            ('underlying_date', 'underlying_close').

    Returns:
        DataFrame with 'close_at_expiry' column added.
    """
    # Convert dates to date objects for matching
    df['expiration_date'] = pd.to_datetime(df['expiration']).dt.date
    df['underlying_date_date'] = pd.to_datetime(df['underlying_date']).dt.date

    # Create lookup DataFrame (date -> close price)
    # Rename columns to avoid conflicts during merge
    stock_lookup = df[['underlying_date_date', 'underlying_close']].drop_duplicates()
    stock_lookup = stock_lookup.rename(columns={
        'underlying_date_date': 'expiration_date_lookup',
        'underlying_close': 'close_at_expiry'
    })

    # Merge to get close price at expiry
    df = df.merge(
        stock_lookup,
        left_on='expiration_date',
        right_on='expiration_date_lookup',
        how='left'
    )

    # Clean up temporary columns
    df = df.drop(columns=['expiration_date', 'expiration_date_lookup', 'underlying_date_date'])

    return df


def add_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add pnl and win columns based on P&L calculation.

    P&L = bid - max(0, strike - close_at_expiry)
    win = pnl > 0

    Args:
        df: DataFrame with 'bid', 'strike', 'close_at_expiry' columns.

    Returns:
        DataFrame with 'pnl' and 'win' columns added.
    """
    df['pnl'] = df['bid'] - np.maximum(0, df['strike'] - df['close_at_expiry'])
    df['win'] = df['pnl'] > 0
    return df

def postprocess_dataset(df: pd.DataFrame, moneyness_threshold: tuple[float, float] = (-0.1, 0)) -> pd.DataFrame:
    """
    Postprocess dataset.

    Args:
        df: DataFrame with 'bid', 'strike', 'close_at_expiry' columns.
        moneyness_threshold: Tuple of (lower, upper) moneyness thresholds.
    """
    df = add_moneyness(df)
    df = add_price_at_expiry(df)
    df = add_pnl(df)
    df = df[df['right'] == 'PUT']
    df = df[(df['moneyness'] < moneyness_threshold[1]) & (df['moneyness'] > moneyness_threshold[0])]
    return df


# OTM bucket constants and utilities
def make_bucket_labels(bins: list[float]) -> list[str]:
    """Given a list of monotonically increasing bin edges, return string labels."""
    return [f"{bins[i]:.1f}-{bins[i+1]:.1f}%" for i in range(len(bins) - 1)]


OTM_BINS = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
OTM_LABELS = make_bucket_labels(OTM_BINS)
MONEYNESS_THRESHOLD = (-0.2, 0)


def filter_weekly_put_options(
    raw_df: pd.DataFrame,
    moneyness_threshold: tuple[float, float] = MONEYNESS_THRESHOLD
) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    """
    Filter raw options data to weekly PUT options matching the strategy criteria.
    
    Applies a series of filters to extract weekly PUT options that match the
    "Weekly Cash KaChing" strategy requirements:
    - Split ratio filter (exclude data where prices are on different scales)
    - PUT options only
    - Moneyness threshold filter (OTM puts within specified range)
    - Bid > 0 (tradeable options only)
    - Thursday/Friday quotes only
    - DTE 6-9 (target next-week expiry)
    - Deduplication (one row per date, strike, expiry)
    
    Args:
        raw_df: Raw DataFrame with options data including columns:
            'underlying_price', 'underlying_close', 'right', 'bid', 'ask',
            'timestamp', 'expiration', 'strike', 'implied_vol'
        moneyness_threshold: Tuple of (lower, upper) moneyness thresholds.
            Defaults to MONEYNESS_THRESHOLD (-0.2, 0).
    
    Returns:
        Tuple of (filtered_df, funnel) where:
        - filtered_df: Fully filtered DataFrame with computed columns:
            'quote_date', 'dte', 'otm_pct', 'otm_bucket', 'moneyness',
            'close_at_expiry', 'pnl', 'win'
        - funnel: List of (label, count) tuples tracking row counts at each filter step
    """
    funnel = [("raw", len(raw_df))]
    
    # Split ratio filter: exclude rows where yfinance (split-adjusted) and Theta prices are on different scales
    ratio = raw_df["underlying_price"] / raw_df["underlying_close"]
    raw_df = raw_df[(ratio > 0.9) & (ratio < 1.1)]
    funnel.append(("split ratio filter", len(raw_df)))
    
    # Add computed columns
    df = add_moneyness(raw_df)
    df = add_price_at_expiry(df)
    df = add_pnl(df)
    
    # PUT only filter
    df = df[df["right"] == "PUT"]
    funnel.append(("PUT only", len(df)))
    
    # Moneyness threshold filter
    df = df[
        (df["moneyness"] < moneyness_threshold[1])
        & (df["moneyness"] > moneyness_threshold[0])
    ]
    funnel.append((f"moneyness {moneyness_threshold[0]*100:.0f}% to 0% OTM", len(df)))
    
    # Bid > 0 filter (no market bid = untradeable)
    df = df[df["bid"] > 0]
    funnel.append(("bid > 0", len(df)))
    
    # Day of week filter: Thu/Fri entries only
    df["quote_date"] = pd.to_datetime(df["timestamp"]).dt.date
    df = df[pd.to_datetime(df["timestamp"]).dt.dayofweek.isin([3, 4])]  # Thursday=3, Friday=4
    funnel.append(("Thu/Fri only", len(df)))
    
    # DTE filter: target next-week expiry (6-9 days out)
    df["dte"] = (pd.to_datetime(df["expiration"]) - pd.to_datetime(df["timestamp"])).dt.days
    df = df[(df["dte"] >= 6) & (df["dte"] <= 9)]
    funnel.append(("DTE 6-9", len(df)))
    
    # OTM bucket calculation
    df["otm_pct"] = df["moneyness"].abs() * 100
    df["otm_bucket"] = pd.cut(df["otm_pct"], bins=OTM_BINS, labels=OTM_LABELS, include_lowest=True)
    
    # Deduplication: one row per (date, strike, expiry) — keep last quote of the day
    df = df.sort_values("timestamp")
    df = df.groupby(["quote_date", "strike", "expiration"]).last().reset_index()
    funnel.append(("dedup", len(df)))
    
    return df, funnel


__all__ = [
    'add_moneyness',
    'add_price_at_expiry',
    'add_pnl',
    'postprocess_dataset',
    'make_bucket_labels',
    'OTM_BINS',
    'OTM_LABELS',
    'MONEYNESS_THRESHOLD',
    'filter_weekly_put_options',
]