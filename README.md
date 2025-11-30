# solar-bess-financial-model
Financial Feasibility Model for 1 MW Solar + 4-Hour BESS (NYISO Zone A) Includes NREL ATB CAPEX/OPEX, PVWatts generation, hourly NYISO prices, BESS arbitrage, and full DCF analysis.

# Western NY Solar + 4-Hour BESS Financial Feasibility Model
### Python-based economic analysis using NREL ATB 2024 + NYISO 2024 market data

---

## *** Overview ***
This repository implements a financial feasibility model for a **1 MW utility-scale solar photovoltaic system paired with a 4-hour battery energy storage system (BESS)** located in **Western New York (NYISO Zone A)**.

The purpose of the model is to:
- Estimate **CAPEX**, **O&M**, and **battery replacement costs**
- Simulate **annual solar generation with degradation**
- Model **battery storage performance** and round-trip losses
- Compute **cash flows, NPV, and IRR**
- Evaluate **merchant revenue scenarios** based on NYISO LBMP prices
- Run **sensitivity/scenario analyses** to support investment decisions

---

## *** Repository Structure ***
project_root/
│── .gitignore
│── requirements.txt
│── README.md
│── config.yaml                # Central user-editable project inputs
│
│── src/                       # Reusable, modularized Python code
│   ├── config_loader.py       # Loads YAML configuration
│   ├── data_loader.py         # Loads & cleans NYISO LBMP data
│   ├── report_utils.py        # Saving tables, charts, exports
│   ├── solar_profile.py       # PVWatts solar generation model
│   ├── market_analysis.py     # Revenue modeling (solar + pricing)
│   ├── bess.py                # Battery dispatch & degradation model
│   └── financials.py          # Cashflows, NPV/IRR, incentives, scenarios
│
│── notebooks/                 # Analysis notebooks (fully reproducible)
│   ├── 00_master_run.ipynb
│   ├── 01_data_ingestion.ipynb
│   ├── 02_solar_generation.ipynb
│   ├── 03_revenue_model.ipynb
│   ├── 04_bess_model.ipynb
│   └── 05_financial_model.ipynb
│
│── outputs/                   # Generated charts, CSVs, summary tables

---

## *** Technologies and Data Sources ***
| Component              | Source                                           |
| ---------------------- | ------------------------------------------------ |
| Solar generation model | NREL PVWatts API (TMY3 dataset)                  |
| CAPEX/OPEX             | NREL ATB 2024 Utility PV + Storage               |
| Price data             | NYISO 2024 LBMP (DAM + RTD)                      |
| Tax incentives         | IRA ITC, MACRS, NYSERDA NY-Sun                   |
| Python stack           | pandas, numpy, numpy-financial, pytz, matplotlib |

---

## *** Capabilities of the Model ***
Generation Modeling:
- Hourly solar PV Output (MWh) using PVWatts
- Leap-year adjustments and timezone alignment for NYISO
- 30-year solar degradation curve
Storage Modeling:
- 4-hour lithium-ion system
- Charge/discharge efficiency modeling
- Round-trip losses
- Mid-life battery replacement year (year 15)
Financial Modeling:
- CAPEX: Solar + BESS + Interconnection
- OPEX with inflation
- ITC (30–50%), MACRS depreciation
- Optional NY-Sun upfront incentive
- Cashflow simulation over 30 years
- NPV and IRR calculation
Sensitivity Analyses for:
- Discount rate
- Revenue growth
- Solar CAPEX
- BESS CAPEX
Scenario Analysis:
- Merchant / ITC / Energy Community / Full Incentive Stack

---

## *** How to Run this Model ***
1. Clone the repo: git clone https://github.com/yourusername/solar-bess-feasibility.git
2. Install dependencies: pip install -r requirements.txt
3. Add your NREL key: create .env → NREL_API_KEY=your_key_here
4. Run the master notebook: notebooks/00_master_run.ipynb
5. View generated charts and tables in outputs/
   
---

## *** License ***
This project is released under the MIT License.

---

## *** Contact ***
For questions or collaboration:
Jess Olena, olena.jessica@gmail.com
