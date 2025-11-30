# src/market_analysis.py
"""
Revenue and capture price modeling for solar projects.
"""
import pandas as pd
import matplotlib.pyplot as plt
import os
from src.report_utils import save_figure, save_dataframe
import pytz

def merge_generation_and_prices(price_df, solar_df):
    """
    Aligns hourly NYISO price data with solar generation data.
    Returns a merged DataFrame with revenue calculations.
    """
    # Ensure timezone alignment (converting both to UTC to be safe)
    if price_df.index.tz is None:
        price_df.index = price_df.index.tz_localize("America/New_York")
    if solar_df.index.tz is None:
        solar_df.index = solar_df.index.tz_localize("America/New_York")

    price_df = price_df.tz_convert("UTC")
    solar_df = solar_df.tz_convert("UTC")

    merged = price_df.join(solar_df["AC_MWh"], how="inner")
    merged["revenue_$"] = merged["DAM_LBMP"] * merged["AC_MWh"]

    return merged

def compute_capture_price(merged):
    """
    Compute total generation, revenue, and capture price.
    """
    total_gen = merged["AC_MWh"].sum()
    total_rev = merged["revenue_$"].sum()
    capture_price = total_rev / total_gen if total_gen > 0 else 0

    summary = {
        "Total Generation (MWh/MW)": total_gen,
        "Total Revenue ($/MW)": total_rev,
        "Capture Price ($/MWh)": capture_price,
        "Capacity Factor": total_gen / 8760
    }

    return summary

def visualize_revenue(merged, output_dir="../outputs"):
    """Generate revenue-related plots and save them."""
    os.makedirs(output_dir, exist_ok=True)

    # Daily revenue
    daily = merged["revenue_$"].resample("D").sum()
    fig1, ax1 = plt.subplots(figsize=(12,5))
    ax1.plot(daily.index, daily.values, color="green")
    ax1.set_title("Daily Revenue from 1 MW Solar (Zone A)")
    ax1.set_ylabel("Revenue ($)")
    ax1.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()
    save_figure(fig1, "daily_revenue.png")

    # Monthly revenue
    monthly = merged["revenue_$"].resample("ME").sum()
    fig2, ax2 = plt.subplots(figsize=(10,5))
    ax2.bar(monthly.index.strftime("%b"), monthly.values, color="mediumseagreen", alpha=0.8)
    ax2.set_title("Monthly Revenue (1 MW Solar)")
    ax2.set_ylabel("Revenue ($)")
    ax2.grid(True, axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()
    save_figure(fig2, "monthly_revenue.png")

    # Scatter price vs. generation
    fig3, ax3 = plt.subplots(figsize=(8,5))
    sc = ax3.scatter(merged["AC_MWh"], merged["DAM_LBMP"],
                     c=merged["revenue_$"], cmap="viridis", alpha=0.6)
    plt.colorbar(sc, label="Hourly Revenue ($)")
    ax3.set_title("Price vs. Solar Generation (Hourly)")
    ax3.set_xlabel("Solar Generation (MWh)")
    ax3.set_ylabel("Price ($/MWh)")
    ax3.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()
    save_figure(fig3, "price_vs_generation.png")
