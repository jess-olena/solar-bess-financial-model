# src/report_utils.py
"""
Utilities to save figures and export summary statistics.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt

def save_figure(fig, filename: str, output_dir: str = "../outputs", dpi: int = 300):
    """
    Saves a Matplotlib figure to the outputs directory.
    """
    os.makedirs(output_dir, exist_ok=True)
    fig.savefig(os.path.join(output_dir, filename),
                dpi=dpi, bbox_inches='tight')
    plt.close(fig)

def save_dataframe(df: pd.DataFrame, filename: str, output_dir: str = "../outputs"):
    """
    Saves a DataFrame (stats or cleaned data) to CSV.
    """
    os.makedirs(output_dir, exist_ok=True)
    df.to_csv(os.path.join(output_dir, filename))
    print(f"Saved DataFrame → {filename}")

def export_summary_report(prices, monthly_stats, hourly_stats, monthly_vol, summary_file="lbmp_summary.csv"):
    """
    Combines all basic statistics into one CSV summary.
    """
    combined = {
        "Monthly_Mean_$MWh": monthly_stats.mean().mean(),
        "Hourly_Std_$MWh": hourly_stats.std().mean(),
        "Annual_Mean_$MWh": prices.mean().mean(),
        "Annual_Std_$MWh": prices.std().mean(),
        "Correlation_DAM_RTD": prices["DAM_LBMP"].corr(prices["RTD_LBMP"])
    }
    df_summary = pd.DataFrame([combined])
    save_dataframe(df_summary, summary_file)