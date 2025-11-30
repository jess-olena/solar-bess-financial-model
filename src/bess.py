# src/bess.py
"""
Battery Energy Storage Simulation (4-hour system)
    Simulate heuristic BESS dispatch based on hourly price signals.
    - Charges when price <= low quantile
    - Discharges when price >= high quantile
    - Accounts for charge/discharge efficiency and throughput degradation tracking
"""
import pandas as pd
import matplotlib.pyplot as plt
import os
from src.report_utils import save_figure, save_dataframe
from src.config_loader import load_config
cfg = load_config()

# Config parameters
BESS_DURATION_H = cfg["bess"]["duration_hours"]
BESS_POWER_MW = cfg["project"]["capacity_mw"]               # assume same size as PV
BESS_CAPACITY_MWh = BESS_POWER_MW * BESS_DURATION_H
EFFICIENCY = cfg["bess"]["roundtrip_efficiency"]
CHARGE_EFF = cfg["bess"]["charge_efficiency"]
DISCHARGE_EFF = cfg["bess"]["discharge_efficiency"]
LOW_Q = 0.25
HIGH_Q = 0.75

def simulate_bess_dispatch(
    price_series: pd.Series,
    capacity_MWh: float = BESS_CAPACITY_MWh,
    power_MW: float = BESS_POWER_MW,
    charge_eff: float = CHARGE_EFF,
    discharge_eff: float = DISCHARGE_EFF,
    low_q: float = LOW_Q,
    high_q: float = HIGH_Q,
    use_daily_thresholds: bool = False,
) -> pd.DataFrame:
    """
    Simulate heuristic BESS dispatch based on hourly price signals.

    Assumes 1-hour time steps, so MW ~ MWh per step.

    Charging:
        - When price <= low threshold
        - SOC increases by energy_to_battery
        - Grid energy = energy_to_battery / charge_eff
        - Cost = grid energy * price

    Discharging:
        - When price >= high threshold
        - SOC decreases by energy_from_battery
        - Grid energy = energy_from_battery * discharge_eff
        - Revenue = grid energy * price
    """

    # Align price series
    price_series = price_series.sort_index()
    if not isinstance(price_series.index, pd.DatetimeIndex):
        raise ValueError("price_series must have a DatetimeIndex.")

    bess = pd.DataFrame(index=price_series.index)
    bess["price"] = price_series

    # Initialize columns
    bess["SOC_MWh"] = 0.0
    bess["charge_MW"] = 0.0          # grid power into BESS (MWh per hour)
    bess["discharge_MW"] = 0.0       # grid power out of BESS
    bess["charge_cost_$"] = 0.0
    bess["discharge_rev_$"] = 0.0
    bess["net_revenue_$"] = 0.0
    bess["throughput_MWh"] = 0.0     # per-step energy through the battery (inside)
    bess["charge_energy_MWh"] = 0.0  # energy added to SOC
    bess["discharge_energy_MWh"] = 0.0  # energy drawn from SOC

    # Thresholds
    if use_daily_thresholds:
        # Group by calendar day (normalized timestamps)
        dates_norm = bess.index.normalize()
        daily_q = (
            bess["price"]
            .groupby(dates_norm)
            .quantile([low_q, high_q])
            .unstack(level=-1)
        )
        # Columns are [low_q, high_q]
        low_daily = daily_q[low_q]
        high_daily = daily_q[high_q]

        # Map each timestamp to that day's thresholds
        low_th_series = dates_norm.map(low_daily)
        high_th_series = dates_norm.map(high_daily)
        low_th_series.index = bess.index
        high_th_series.index = bess.index
    else:
        low_th = bess["price"].quantile(low_q)
        high_th = bess["price"].quantile(high_q)

    # Dispatch loop
    soc = 0.0  # MWh

    for t in bess.index:
        price = bess.at[t, "price"]

        if use_daily_thresholds:
            low_th = low_th_series.at[t]
            high_th = high_th_series.at[t]

        # Defaults for this timestep
        charge_from_grid = 0.0          # MWh from grid into inverter
        discharge_to_grid = 0.0         # MWh from inverter to grid
        energy_into_battery = 0.0       # MWh added to SOC
        energy_from_battery = 0.0       # MWh removed from SOC

        # Charge logic
        if price <= low_th and soc < capacity_MWh:
            # Energy that ends up in the battery this hour
            energy_into_battery = min(power_MW, capacity_MWh - soc)

            # Grid energy needed, accounting for charge efficiency
            charge_from_grid = energy_into_battery / charge_eff

            soc += energy_into_battery

            bess.at[t, "charge_MW"] = charge_from_grid
            bess.at[t, "charge_cost_$"] = charge_from_grid * price

        # Discharge logic
        elif price >= high_th and soc > 0:
            # Energy that can be drawn from the battery
            energy_from_battery = min(power_MW, soc)

            # Energy delivered to the grid after efficiency losses
            discharge_to_grid = energy_from_battery * discharge_eff

            soc -= energy_from_battery

            bess.at[t, "discharge_MW"] = discharge_to_grid
            bess.at[t, "discharge_rev_$"] = discharge_to_grid * price

        # Enforce SOC bounds to guard against any numeric shifting
        soc = max(0.0, min(soc, capacity_MWh))
        bess.at[t, "SOC_MWh"] = soc

        # Store internal energies and per-step throughput
        bess.at[t, "charge_energy_MWh"] = energy_into_battery
        bess.at[t, "discharge_energy_MWh"] = energy_from_battery
        bess.at[t, "throughput_MWh"] = energy_into_battery + energy_from_battery

    bess["net_revenue_$"] = bess["discharge_rev_$"] - bess["charge_cost_$"]
    return bess

def summarize_bess(bess_df):
    """Summarize BESS operational and financial metrics."""
    total_revenue = bess_df["net_revenue_$"].sum()
    total_throughput = bess_df["throughput_MWh"].sum()  # inside the battery
    full_cycles = total_throughput / (2.0 * BESS_CAPACITY_MWh)

    avg_soc = bess_df["SOC_MWh"].mean()

    # Days with any discharge activity
    days_active = (
    (bess_df["discharge_MW"] > 0)
    .astype(int)
    .resample("D")
    .sum()
    .gt(0)
    .sum()
)
    days_active = float(days_active)
    avg_daily_rev = total_revenue / days_active if days_active > 0 else 0.0

    return {
        "Total Net Revenue ($)": round(total_revenue, 2),
        "Estimated Full Cycles": round(full_cycles, 2),
        "Average SOC (MWh)": round(avg_soc, 2),
        "Days Active": round(days_active, 1),
        "Avg Daily Net Revenue ($/day)": round(avg_daily_rev, 2),
    }

def visualize_bess(bess_df, output_dir="../outputs"):
    """Visualize SOC, daily, and cumulative net revenues."""
    os.makedirs(output_dir, exist_ok=True)

    # SOC Plot
    fig1, ax1 = plt.subplots(figsize=(12, 5))
    bess_df["SOC_MWh"].plot(ax=ax1, color="royalblue")
    ax1.set_title("BESS State of Charge (4-Hour System)")
    ax1.set_ylabel("State of Charge [MWh]")
    ax1.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()
    save_figure(fig1, "bess_SOC.png")

    # Daily Revenue
    daily = bess_df["net_revenue_$"].resample("D").sum()
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    daily.plot(ax=ax2, color="seagreen")
    ax2.set_title("Daily BESS Arbitrage Revenue")
    ax2.set_ylabel("Revenue ($)")
    ax2.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()
    save_figure(fig2, "bess_daily_revenue.png")

    # Cumulative Net Profit
    cumulative = daily.cumsum()
    fig3, ax3 = plt.subplots(figsize=(12, 5))
    cumulative.plot(ax=ax3, color="darkorange")
    ax3.set_title("Cumulative Net Profit (BESS Arbitrage)")
    ax3.set_ylabel("Cumulative Profit ($)")
    ax3.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.show()
    save_figure(fig3, "bess_cumulative_profit.png")

    plt.show()

def run_bess_model(price_series, output_dir="../outputs",
                   use_daily_thresholds=False,
                   low_q=0.25, high_q=0.75):
    """
    Full run: sanitize index, simulate dispatch, summarize, visualize, save.
    """
    # Ensure datetime index for resampling and plotting
    if not isinstance(price_series.index, pd.DatetimeIndex):
        price_series.index = pd.to_datetime(price_series.index, errors="coerce")

    price_series = price_series[price_series.index.notnull()]
    price_series = price_series[~price_series.index.duplicated(keep="first")]
    price_series = price_series.sort_index()

    n = len(price_series)
    if n < 8000:  # clearly not a full year
        raise ValueError(
            f"Price series too short ({n} rows). "
            "Reload clean prices and avoid prior subsetting."
        )

    print(f"Hours in series: {price_series.shape[0]}")

    bess_df = simulate_bess_dispatch(
        price_series,
        use_daily_thresholds=use_daily_thresholds,
        low_q=low_q,
        high_q=high_q,
    )

    bess_summary = summarize_bess(bess_df)
    visualize_bess(bess_df, output_dir)
    save_dataframe(bess_df, "bess_hourly_results.csv")

    print("\nBESS simulation complete.")
    print("—" * 40)
    for k, v in bess_summary.items():
        print(f"{k}: {v:,}")

    return bess_df, bess_summary

