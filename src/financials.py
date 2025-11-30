# src/financials.py
"""
Financial modeling for co-located Solar + Storage (WNY - NYISO Zone A)
Major points: 
- Uses real hourly NYISO-based solar + storage revenues as the starting point.
- Uses ATB-aligned assumptions for CAPEX, degradation, and battery replacement.
- Treats ITC as an upfront reduction in effective CAPEX (simplified vs a full tax model).
- Includes degradation for solar and BESS.
- Escalates revenues and OPEX separately (merchant-style, not per NREL ATB LCOE).
- Computes project-level NPV and IRR.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import numpy_financial as npf
from pathlib import Path
from src.config_loader import load_config
cfg = load_config()

### Config Variables ###
PROJECT_LIFE = cfg["project"]["project_life"]
DISCOUNT_RATE = cfg["financials"]["discount_rate"]     # nominal WACC 
INFLATION_RATE = cfg["financials"]["inflation_rate"]   # for OPEX
REVENUE_ESCALATION = cfg["financials"].get("escalation_rate", 0.0)

# Capital Costs
SOLAR_CAPEX = cfg["capex"]["solar_per_mw"] * cfg["project"]["capacity_mw"]
BESS_CAPEX = cfg["capex"]["bess_per_mwh"] * cfg["project"]["capacity_mw"] * cfg["bess"]["duration_hours"]
ITC_CREDIT = cfg["financials"]["itc_credit"]

# Degradation
SOLAR_DEGRADATION = cfg["solar_generation"]["solar_degradation"]               # 0.5% per year
BESS_DEGRADATION = cfg["bess"]["bess_degradation"]                             # 2% per year

# Battery replacement
BATTERY_REPLACEMENT_YEAR = cfg["bess"]["battery_replacement_year"] 
BATTERY_REPLACEMENT_COST_FRAC = cfg["bess"]["battery_replacement_cost_frac"]   # 40% of initial cost

# Operating Expenses
OPEX_FIXED = cfg["financials"]["o_and_m_per_mw"] * cfg["project"]["capacity_mw"] # $/year combined

# ITC Credits
#total_capex = (solar_capex + bess_capex) + interconnection_cost
#after_itc_capex = total_capex * (1 - itc_credit)

### Main Functions ###

def combine_solar_bess(solar_df, bess_df, price_col="DAM_LBMP"):
    """
    Combine hourly solar and battery data into a single DataFrame and compute revenues.

    Parameters
    ----------
    solar_df : DataFrame
        Must contain 'AC_MWh' and the price column (e.g. DAM_LBMP, RTD_LBMP).
    bess_df : DataFrame
        Must contain 'net_revenue_$' or 'revenue_$' for the battery arbitrage model.
    price_col : str
        Column name for price (e.g. 'DAM_LBMP' or 'RTD_LBMP').

    Returns
    -------
    merged : DataFrame
        Index: hourly timestamps
        Columns: AC_MWh, price_col, solar_revenue_$, bess_revenue_$, total_revenue_$, ...
    """
    merged = solar_df.join(bess_df, how="inner", lsuffix="_solar", rsuffix="_bess")

    if "AC_MWh" not in merged.columns:
        raise KeyError("Expected 'AC_MWh' column in solar_df for energy calculations.")

    if price_col not in merged.columns:
        raise KeyError(f"Missing '{price_col}' column for revenue computation.")

    # Solar revenue = hourly MWh * price
    merged["solar_revenue_$"] = merged["AC_MWh"] * merged[price_col]

    # BESS revenue = from arbitrage model (net of charging costs)
    if "net_revenue_$" in merged.columns:
        merged["bess_revenue_$"] = merged["net_revenue_$"]
    elif "revenue_$" in merged.columns:
        merged["bess_revenue_$"] = merged["revenue_$"]
    else:
        merged["bess_revenue_$"] = 0.0

    merged["total_revenue_$"] = merged["solar_revenue_$"] + merged["bess_revenue_$"]
    return merged

def annualize_revenue(merged_df):
    """
    Aggregate hourly revenue data into annual totals for solar, BESS, and combined.
    """
    merged_df = merged_df.copy()
    merged_df.index = pd.to_datetime(merged_df.index, errors="coerce")

    # Aggregate all relevant revenue columns
    annual = merged_df.resample("YE")[[
        "solar_revenue_$",
        "bess_revenue_$",
        "total_revenue_$"
    ]].sum()

    # Convert index to year integers (2024, 2025, …)
    annual.index = annual.index.year

    return annual

# Degradation & Cashflow Construction
def apply_degradation(base_value, degradation_rate, years):
    """
    Apply compounding degradation over project lifetime.

    Parameters
    ----------
    base_value : float
        Initial (year-1) value.
    degradation_rate : float
        Annual fractional degradation (e.g., 0.005 for 0.5%).
    years : int
        Number of years to compute.

    Returns
    -------
    values : list[float]
        Length = years; values[0] = base_value (year 1),
        values[y] = base_value * (1 - degradation_rate)^y
    """
    return [base_value * ((1 - degradation_rate) ** y) for y in range(years)]


def build_cashflows(
    base_solar_revenue,
    base_bess_revenue,
    opex_fixed,
    solar_deg,
    bess_deg,
):
    """
    Construct annual project cashflows (pre-tax) for Solar + 4-hr BESS.

    Assumptions:
    - ITC is treated as an upfront reduction to CAPEX, not as a tax credit.
    - Cashflows are pre-tax; no explicit depreciation or capital structure.
    - Revenues are split into solar and BESS, both with degradation and escalation.
    - OPEX escalates with inflation.
    - BESS replacement occurs in BATTERY_REPLACEMENT_YEAR at a %
      of initial BESS CAPEX.

    Parameters
    ----------
    base_solar_revenue : float
        Year-1 annual revenue attributable to solar generation (USD, nominal).
    base_bess_revenue : float
        Year-1 annual revenue attributable to BESS arbitrage (USD, nominal).
    opex_fixed : float
        Year-1 fixed OPEX (USD, nominal).
    solar_deg : float
        Annual PV degradation rate (fraction).
    bess_deg : float
        Annual BESS degradation rate (fraction).

    Returns
    -------
    cashflows : list[float]
        cashflows[0] = initial (negative) investment
        cashflows[1:] = net cashflow for each project year
    """
    # Reduce upfront capex via ITC application
    initial_investment = (SOLAR_CAPEX + BESS_CAPEX) * (1 - ITC_CREDIT)
    cashflows = [-initial_investment]

    # Real (degraded) revenue profiles (before escalation)
    degraded_solar = apply_degradation(base_solar_revenue, solar_deg, PROJECT_LIFE)
    degraded_bess = apply_degradation(base_bess_revenue, bess_deg, PROJECT_LIFE)

    for y in range(PROJECT_LIFE):
        # Year index y corresponds to project year (y+1)
        year = y + 1

        # Apply revenue escalation (merchant price)
        revenue_escalation_factor = (1 + REVENUE_ESCALATION) ** y
        annual_rev = (degraded_solar[y] + degraded_bess[y]) * revenue_escalation_factor

        # Escalate OPEX with inflation
        opex_factor = (1 + INFLATION_RATE) ** y
        annual_opex = opex_fixed * opex_factor

        net = annual_rev - annual_opex

        # Battery mid-life replacement
        if year == BATTERY_REPLACEMENT_YEAR:
            net -= BESS_CAPEX * BATTERY_REPLACEMENT_COST_FRAC

        cashflows.append(net)

    return cashflows

# High-Level Summary 

def summarize_financials(base_solar_revenue, base_bess_revenue=0.0):
    """
    Compute NPV, IRR, and return a financial summary.
    1. Build hourly solar + BESS revenue DataFrames.
    2. Combine them with `combine_solar_bess`.
    3. Aggregate to annual with `annualize_revenue`.
    4. Take year-1 solar and bess revenue as inputs here.

    Parameters
    ----------
    base_solar_revenue : float
        Year-1 solar revenue (USD).
    base_bess_revenue : float, optional
        Year-1 BESS revenue (USD). Default is 0 (solar-only).

    Returns
    -------
    summary : dict
        Key financial metrics for reporting.
    cashflow_df : DataFrame
        Columns: ['Year', 'Cashflow'] including Year 0.
    """
    cashflows = build_cashflows(
        base_solar_revenue=base_solar_revenue,
        base_bess_revenue=base_bess_revenue,
        opex_fixed=OPEX_FIXED,
        solar_deg=SOLAR_DEGRADATION,
        bess_deg=BESS_DEGRADATION,
    )

    # Compute NPV and IRR (pre-tax)
    npv = cashflows[0] + npf.npv(DISCOUNT_RATE, cashflows[1:])
    irr = npf.irr(cashflows)

    # Compute initial investment
    initial_investment = (SOLAR_CAPEX + BESS_CAPEX) * (1 - ITC_CREDIT)

    summary = {
        "NPV ($M)": npv / 1_000_000,
        "IRR (%)": float(irr * 100) if irr is not None else np.nan,
        "Total CAPEX ($M)": (SOLAR_CAPEX + BESS_CAPEX) / 1_000_000,
        "Initial Investment ($)": initial_investment,
        "Annual OPEX (Year 1, $)": OPEX_FIXED,
        "Discount Rate": DISCOUNT_RATE,
        "Revenue Escalation Rate": REVENUE_ESCALATION,
        "Inflation Rate": INFLATION_RATE,
        "Project Life (yrs)": PROJECT_LIFE,
        "Battery Replacement Year": BATTERY_REPLACEMENT_YEAR,
        "Battery Replacement Cost Fraction": BATTERY_REPLACEMENT_COST_FRAC,
    }

    years = list(range(len(cashflows)))
    cashflow_df = pd.DataFrame({"Year": years, "Cashflow": cashflows})

    return summary, cashflow_df

def summarize_from_annual_df(annual, cfg=None):
    """
    Computes NPV, IRR, and cashflows from annual revenue.
    Uses the current cfg values (important for sensitivity analysis).
    """
    if cfg is None:
        cfg = load_config()

    # Load config values (DYNAMIC, not globals)
    discount_rate = cfg["financials"]["discount_rate"]
    inflation_rate = cfg["financials"]["inflation_rate"]
    escalation_rate = cfg["financials"]["escalation_rate"]

    solar_capex = cfg["capex"]["solar_per_mw"] * cfg["project"]["capacity_mw"]
    bess_capex = cfg["capex"]["bess_per_mwh"] * cfg["project"]["capacity_mw"] * cfg["bess"]["duration_hours"]
    itc_credit = cfg["financials"]["itc_credit"]

    init_invest = (solar_capex + bess_capex) * (1 - itc_credit)

    opex = cfg["financials"]["o_and_m_per_mw"] * cfg["project"]["capacity_mw"]
    bess_deg = cfg["bess"]["bess_degradation"]
    solar_deg = cfg["solar_generation"]["solar_degradation"]

    replacement_year = cfg["bess"]["battery_replacement_year"]
    replacement_fraction = cfg["bess"]["battery_replacement_cost_frac"]

    project_life = cfg["project"]["project_life"]

    # Build cashflows
    cashflows = [-init_invest]

    base_solar = annual.iloc[0]["solar_revenue_$"]
    base_bess = annual.iloc[0]["bess_revenue_$"]

    for y in range(project_life):
        # Apply degradation & escalation
        solar_rev = base_solar * ((1 - solar_deg) ** y) * ((1 + escalation_rate) ** y)
        bess_rev  = base_bess  * ((1 - bess_deg) ** y)  * ((1 + escalation_rate) ** y)

        revenue = solar_rev + bess_rev

        year_opex = opex * ((1 + inflation_rate) ** y)
        net = revenue - year_opex

        if y + 1 == replacement_year:
            net -= bess_capex * replacement_fraction

        cashflows.append(net)

    npv = cashflows[0] + npf.npv(discount_rate, cashflows[1:])
    irr = npf.irr(cashflows)

    summary = {
        "NPV ($M)": npv / 1_000_000,
        "IRR (%)": irr * 100 if irr is not None else None,
        "Initial Investment ($)": init_invest,
        "Solar CAPEX ($M)": solar_capex / 1_000_000,
        "BESS CAPEX ($M)": bess_capex / 1_000_000,
        "Discount Rate": discount_rate,
        "Escalation Rate": escalation_rate,
        "Inflation Rate": inflation_rate,
    }

    return summary, pd.DataFrame({"Year": range(len(cashflows)), "Cashflow": cashflows})

# Visualization & Export
def visualize_cashflows(cashflow_df):
    """
    Visualize annual cashflows (including Year 0 initial investment).
    """
    cf = cashflow_df.set_index("Year")
    plt.figure(figsize=(10, 5))
    plt.bar(cf.index, cf["Cashflow"], alpha=0.7)
    plt.title("Annual Project Cashflows (Solar + 4-Hour BESS)")
    plt.xlabel("Year")
    plt.ylabel("Cashflow ($)")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.show()


def save_summary(summary_dict, output_dir="../outputs"):
    """
    Save summary metrics to CSV.

    Parameters
    ----------
    summary_dict : dict
        Output from summarize_financials or summarize_from_annual_df.
    output_dir : str or Path
        Directory to write 'financial_summary.csv'.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    out_path = output_dir / "financial_summary.csv"
    pd.DataFrame([summary_dict]).to_csv(out_path, index=False)



