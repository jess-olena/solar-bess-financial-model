# src/solar_model.py
"""
Solar generation retrieval and cleaning utilities using NREL PVWatts API.
"""
import os
api_key = os.getenv("NREL_API_KEY")
import requests
import pandas as pd
import numpy as np
from src.config_loader import load_config
cfg = load_config()

timezone = cfg["project"]["timezone"]
capacity_mw = cfg["project"]["capacity_mw"]
system_capacity_kw = capacity_mw * 1000
lat = cfg["project"]["region_lat"] if "region_lat" in cfg["project"] else 42.8864
lon = cfg["project"]["region_lon"] if "region_lon" in cfg["project"] else -78.8784

tilt = cfg["solar_generation"]["tilt"] if "tilt" in cfg["solar_generation"] else 43
azimuth = cfg["solar_generation"]["azimuth"] if "azimuth" in cfg["solar_generation"] else 180

W_TO_MWH = 1 / 1_000_000.0 # convert to MWh

def get_pvwatts_data(
    api_key,
    lat,
    lon,
    system_capacity_kw,
    tilt,
    azimuth,
    array_type=1,
    module_type=0,
    losses=14,
    timezone="America/New_York"
):
    """
    Retrieve hourly PV generation data from PVWatts and format to MWh output.
    Automatically adjusts for leap years and ensures time alignment.
    """
    url = "https://developer.nrel.gov/api/pvwatts/v8.json"

    params = {
        "api_key": api_key,
        "lat": lat,
        "lon": lon,
        "system_capacity": system_capacity_kw,
        "azimuth": azimuth,
        "tilt": tilt,
        "array_type": array_type,
        "module_type": module_type,
        "losses": losses,
        "timeframe": "hourly",
        "dataset": "tmy3",
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise ValueError(f"PVWatts API error: {response.status_code} — {response.text}")

    data = response.json()["outputs"]
    ac_array = np.array(data["ac"])
    n_hours = len(ac_array)

    # Build time index dynamically
    full_index = pd.date_range(
        "2024-01-01 00:00",
        "2024-12-31 23:00",
        freq="h",
        tz=timezone
    )  # 8784 hours

    full_hours = len(full_index)
    
    # Adjust ac_array to match leap-year length
    if n_hours < full_hours:
        padded = np.full(full_hours, np.nan)
        padded[:n_hours] = ac_array
        ac_array = padded
    elif n_hours > full_hours:
        ac_array = ac_array[:full_hours]

    # Convert W → MWh (hourly)
    ac_mwh = ac_array * W_TO_MWH

    # Build final dataframe using the corrected index
    hourly_df = pd.DataFrame({"AC_MWh": ac_mwh}, index=full_index)

    # Interpolate only gaps, preserve nighttime zeros
    nighttime_mask = hourly_df["AC_MWh"].isna()
    hourly_df["AC_MWh"] = hourly_df["AC_MWh"].interpolate(
        limit_direction="both"
    )
    hourly_df.loc[nighttime_mask & (hourly_df["AC_MWh"] < 0.0001), "AC_MWh"] = 0.0

    print(f"Solar data prepared: {len(hourly_df)} hourly rows.")
    print(f"Total annual generation (MWh): {hourly_df['AC_MWh'].sum():,.2f}")

    return hourly_df

def validate_solar_profile(df):
    """Quick validation and descriptive stats for hourly solar data."""
    daily = df.resample("D").sum()
    monthly = df.resample("ME").sum()
    stats = {
        "annual_MWh_per_MW": df["AC_MWh"].sum(),
        "peak_hour_MWh_per_MW": df["AC_MWh"].max(),
        "capacity_factor": df["AC_MWh"].sum() / 8760
    }
    return daily, monthly, stats

def build_solar_profile(cfg):
    """
    High-level wrapper for generating the solar hourly profile.
    Reads parameters from config.yaml and returns AC_MWh dataframe.
    """

    api_key = os.getenv("NREL_API_KEY")
    if not api_key:
        raise ValueError("Missing NREL_API_KEY environment variable.")

    # Project configuration
    lat = cfg["project"]["region_lat"]
    lon = cfg["project"]["region_lon"]
    capacity_mw = cfg["project"]["capacity_mw"]
    system_capacity_kw = capacity_mw * 1000

    tilt = cfg["solar_generation"]["tilt"]
    azimuth = cfg["solar_generation"]["azimuth"]
    timezone = cfg["project"]["timezone"]

    # Retrieve PVWatts hourly generation
    solar_df = get_pvwatts_data(
        api_key=api_key,
        lat=lat,
        lon=lon,
        system_capacity_kw=system_capacity_kw,
        tilt=tilt,
        azimuth=azimuth,
        timezone=timezone
    )

    # Optional: apply degradation in Year 1
    solar_deg = cfg["solar_generation"]["solar_degradation"]
    if solar_deg > 0:
        solar_df["AC_MWh"] *= (1 - solar_deg)**0  # Year 1 only

    return solar_df
