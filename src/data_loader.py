# src/data_loader.py
"""
Data loading and cleaning utilities for NYISO LBMP (Locational-Based Marginal Pricing) data.
"""
import os
import pandas as pd
import pytz
from src.config_loader import load_config
cfg = load_config()
root = cfg["paths"]["project_root"]
solar_path = os.path.join(root, cfg["paths"]["solar_output"])
cfg = load_config()

def load_and_clean_lbmp(file_path: str, time_col: str, price_col: str, tz: str = "America/New_York") -> pd.DataFrame:
    """
    Loads and cleans NYISO LBMP data.
    - Converts timestamps
    - Removes duplicates
    - Interpolates missing hourly data
    """
    # Load CSV
    df = pd.read_csv(file_path)
    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col)

    # Localize to NY timezone
    df = df.tz_localize(tz, ambiguous='NaT', nonexistent='shift_forward')

    # Keep numeric columns only
    numeric_cols = df.select_dtypes(include='number').columns
    df = df[numeric_cols]

    # Average duplicates
    df = df.groupby(df.index).mean()

    # Create continuous hourly index for 2024
    full_index = pd.date_range("2024-01-01 00:00", "2024-12-31 23:00", freq="h", tz=tz)
    df = df.reindex(full_index).interpolate()

    # Rename price column for consistency
    df.rename(columns={price_col: 'LBMP_$'}, inplace=True)

    return df


def combine_price_series(dam_df: pd.DataFrame, rtd_df: pd.DataFrame) -> pd.DataFrame:
    """Combine DAM and RTD price series into one DataFrame."""
    combined = pd.concat(
        [dam_df.rename(columns={'LBMP_$': 'DAM_LBMP'}),
         rtd_df.rename(columns={'LBMP_$': 'RTD_LBMP'})],
        axis=1
    )
    return combined


def summarize_prices(prices: pd.DataFrame) -> dict:
    """Compute basic statistics for LBMP data."""
    stats = {
        "annual_summary": prices.describe(),
        "monthly_mean": prices.resample("ME").mean(),
        "hourly_mean": prices.groupby(prices.index.hour).mean(),
        "monthly_volatility": prices.resample("ME").std(),
        "correlation": prices["DAM_LBMP"].corr(prices["RTD_LBMP"]),
    }
    return stats

# Time Zone Help: Force NY timezone → UTC → aligned hourly index
def fix_and_align_timezone(df, name, tz="America/New_York"):
    """
    Safely convert the index to a timezone-aware DateTimeIndex,
    handling mixed formats and missing tz info.
    """
    df = df.copy()

    # Step 1: Force full datetime parsing with UTC normalization
    df.index = pd.to_datetime(df.index, errors="coerce", utc=True)

    # Drop rows that still failed to parse
    df = df[~df.index.isna()]

    # Step 2: Convert UTC → local → UTC to normalize
    try:
        df.index = df.index.tz_convert(tz).tz_convert("UTC")
    except Exception:
        # If already localized incorrectly, fallback to forcing the localization
        df.index = df.index.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT").tz_convert("UTC")

    # Step 3: Full-year 2024 hourly index
    full_index = pd.date_range(
        "2024-01-01 00:00",
        "2024-12-31 23:00",
        freq="h",
        tz="UTC"
    )

    # Step 4: Align to 2024 hours
    df = df.reindex(full_index)

    return df

# Solar Loader for Master Notebook
def load_solar_data(cfg):
    solar_path = cfg.get("paths", {}).get("solar_output", "outputs/solar_hourly_2024.csv")
    df = pd.read_csv(solar_path, index_col=0)
    df = fix_and_align_timezone(df, "Solar")
    return df

# Price Loader for Master Notebook
def load_price_data(cfg):
    price_path = cfg.get("paths", {}).get("price_output", "outputs/lbmp_zoneA_cleaned.csv")
    df = pd.read_csv(price_path, index_col=0)
    df = fix_and_align_timezone(df, "Prices")
    return df

# BESS Loader for Master Notebook
def load_bess_data(cfg):
    bess_path = cfg.get("paths", {}).get("bess_output", "outputs/bess_dispatch_results.csv")
    df = pd.read_csv(bess_path, index_col=0)
    df = fix_and_align_timezone(df, "BESS")

    # Fill missing arbitrage revenue with zero
    if "net_revenue_$" in df.columns:
        df["net_revenue_$"] = df["net_revenue_$"].fillna(0)

    return df
