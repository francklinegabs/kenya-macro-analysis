"""Kenya vs East African peers: inflation, growth, the shilling and remittances, 2000-2024.

Reads data/worldbank_raw.csv (from fetch_data.py), writes charts to figures/ and
summary tables to output/.
Run:  python src/analysis.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "worldbank_raw.csv"
FIG = ROOT / "figures"
OUT = ROOT / "output"

PALETTE = {"Kenya": "#1f5c4b", "Uganda": "#b5541c", "Tanzania": "#3d6fb4", "Rwanda": "#8a6bb8", "Ethiopia": "#9a9a9a"}
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "font.size": 10})


def load() -> pd.DataFrame:
    """Tidy long table -> wide panel indexed by (country, year), one column per indicator."""
    raw = pd.read_csv(DATA)
    panel = raw.pivot_table(index=["country", "year"], columns="indicator", values="value").sort_index()
    panel.columns.name = None
    return panel


def flag_series_breaks(panel: pd.DataFrame, ratio: float = 4.0,
                       cols=("remittances_pct_gdp", "exports_pct_gdp", "imports_pct_gdp", "agriculture_pct_gdp"),
                       ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Blank out values that jump more than `ratio`x against BOTH neighbouring years.

    Ratios of GDP don't move 4x in one year for real. When one does, it is a break in how the
    series was compiled, so the value is set to NaN and logged rather than silently kept.
    """
    p = panel.copy()
    flags = []
    for col in cols:
        for country, s in p[col].groupby(level="country"):
            s = s.droplevel("country")
            prev, nxt = s.shift(1), s.shift(-1)
            near = prev.fillna(nxt)
            far = nxt.fillna(prev)
            bad = ((s / near > ratio) | (near / s > ratio)) & ((s / far > ratio) | (far / s > ratio))
            for yr in s[bad].index:
                flags.append({"country": country, "indicator": col, "year": int(yr), "value": s[yr],
                              "previous": prev.get(yr), "next": nxt.get(yr)})
                p.loc[(country, yr), col] = np.nan
    return p, pd.DataFrame(flags)


def add_derived(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    g = p.groupby(level="country")
    # Depreciation: % change in local currency per USD (positive = currency weakened).
    p["fx_depreciation_pct"] = g["fx_lcu_per_usd"].pct_change(fill_method=None) * 100
    p["trade_balance_pct_gdp"] = p["exports_pct_gdp"] - p["imports_pct_gdp"]
    base = p.xs(2000, level="year")["gdp_per_capita_usd_2015"]
    p["gdp_pc_index_2000"] = p["gdp_per_capita_usd_2015"] / p.index.get_level_values("country").map(base).values * 100
    return p


def inflation_profile(p: pd.DataFrame) -> pd.DataFrame:
    infl = p["inflation_pct"].unstack("country")
    return pd.DataFrame({
        "mean_pct": infl.mean(),
        "median_pct": infl.median(),
        "std_pct": infl.std(),
        "years_above_10pct": (infl > 10).sum(),
        "max_pct": infl.max(),
        "max_year": infl.idxmax(),
        "latest_pct": infl.ffill().iloc[-1],
    }).round(2).sort_values("std_pct")


def growth_profile(p: pd.DataFrame) -> pd.DataFrame:
    gdp = p["gdp_growth_pct"].unstack("country")
    pc = p["gdp_per_capita_usd_2015"].unstack("country")
    years = pc.index.max() - 2000
    cagr = ((pc.iloc[-1] / pc.loc[2000]) ** (1 / years) - 1) * 100
    return pd.DataFrame({
        "avg_gdp_growth_pct": gdp.mean(),
        "growth_volatility": gdp.std(),
        "worst_year_pct": gdp.min(),
        "worst_year": gdp.idxmin(),
        "gdp_pc_2000": pc.loc[2000],
        "gdp_pc_latest": pc.iloc[-1],
        "gdp_pc_cagr_pct": cagr,
    }).round(2).sort_values("gdp_pc_cagr_pct", ascending=False)


def fx_passthrough(p: pd.DataFrame, country: str = "Kenya") -> dict:
    """Does a weaker shilling show up in inflation? Same-year and one-year-lagged regressions."""
    k = p.xs(country, level="country")[["inflation_pct", "fx_depreciation_pct"]].copy()
    k["fx_dep_lag1"] = k["fx_depreciation_pct"].shift(1)
    res = {}
    for col, label in [("fx_depreciation_pct", "same_year"), ("fx_dep_lag1", "lag_1y")]:
        d = k[["inflation_pct", col]].dropna()
        lr = stats.linregress(d[col], d["inflation_pct"])
        rho, rho_p = stats.spearmanr(d[col], d["inflation_pct"])
        res[label] = {"n": len(d), "slope": lr.slope, "intercept": lr.intercept, "r": lr.rvalue,
                      "r2": lr.rvalue ** 2, "p_value": lr.pvalue, "spearman": rho, "spearman_p": rho_p}
    return res


def kenya_periods(p: pd.DataFrame) -> pd.DataFrame:
    k = p.xs("Kenya", level="country")
    bins = {"2000-2007": (2000, 2007), "2008-2012": (2008, 2012), "2013-2019": (2013, 2019), "2020-2024": (2020, 2024)}
    cols = ["gdp_growth_pct", "inflation_pct", "fx_depreciation_pct", "remittances_pct_gdp",
            "trade_balance_pct_gdp", "lending_rate_pct", "agriculture_pct_gdp"]
    rows = {name: k.loc[a:b, cols].mean() for name, (a, b) in bins.items()}
    return pd.DataFrame(rows).T.round(2)


def remittance_trend(p: pd.DataFrame) -> dict:
    # 2001-2003 sit near 0.4% of GDP and then jump 5x in 2004: the same recording change as the
    # 2000 break, spread over three years, so the trend is measured from 2004 onward.
    r = p.xs("Kenya", level="country")["remittances_pct_gdp"].loc[2004:].dropna()
    lr = stats.linregress(r.index, r.values)
    return {"first_year": int(r.index[0]), "first": r.iloc[0], "last_year": int(r.index[-1]), "last": r.iloc[-1],
            "peak_year": int(r.idxmax()), "peak": r.max(), "trend_per_year": lr.slope, "trend_p": lr.pvalue}


# ---------------------------------------------------------------- charts
def chart_inflation(p):
    infl = p["inflation_pct"].unstack("country")
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for c in infl.columns:
        ax.plot(infl.index, infl[c], color=PALETTE[c], lw=2.6 if c == "Kenya" else 1.3,
                alpha=1 if c == "Kenya" else 0.75, label=c)
    ax.axhspan(2.5, 7.5, color="#1f5c4b", alpha=0.06)
    ax.text(2000.3, 7.9, "Central Bank of Kenya current target band (5% ± 2.5)", fontsize=8.5, color="#1f5c4b")
    ax.set_ylabel("Consumer price inflation (%)")
    ax.set_title("Inflation: Kenya vs East African peers")
    ax.legend(frameon=False, ncol=5, loc="upper right")
    fig.tight_layout(); fig.savefig(FIG / "inflation_peers.png"); plt.close(fig)


def chart_gdp_index(p):
    idx = p["gdp_pc_index_2000"].unstack("country")
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for c in idx.columns:
        ax.plot(idx.index, idx[c], color=PALETTE[c], lw=2.6 if c == "Kenya" else 1.3, label=c)
        ax.annotate(f"{c} {idx[c].dropna().iloc[-1]:.0f}", (idx[c].dropna().index[-1], idx[c].dropna().iloc[-1]),
                    xytext=(4, 0), textcoords="offset points", fontsize=8.5, color=PALETTE[c], va="center")
    ax.axhline(100, color="#555", lw=0.8)
    ax.set_xlim(2000, idx.index.max() + 3)
    ax.set_ylabel("Real GDP per capita (2000 = 100)")
    ax.set_title("Real income per person since 2000")
    fig.tight_layout(); fig.savefig(FIG / "gdp_per_capita_index.png"); plt.close(fig)


def chart_shilling(p, fx):
    k = p.xs("Kenya", level="country")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.plot(k.index, k["fx_lcu_per_usd"], color=PALETTE["Kenya"], lw=2.2)
    ax.set_title("Kenyan shillings per US dollar (annual average)")
    ax.set_ylabel("KES per USD")
    ax = axes[1]
    d = k[["fx_depreciation_pct", "inflation_pct"]].dropna()
    ax.scatter(d["fx_depreciation_pct"], d["inflation_pct"], color=PALETTE["Kenya"], s=30)
    for yr, row in d.iterrows():
        if abs(row["fx_depreciation_pct"]) > 9 or row["inflation_pct"] > 12:
            ax.annotate(str(yr), (row["fx_depreciation_pct"], row["inflation_pct"]), xytext=(4, 3),
                        textcoords="offset points", fontsize=8)
    s = fx["same_year"]
    xs = np.linspace(d["fx_depreciation_pct"].min(), d["fx_depreciation_pct"].max(), 50)
    ax.plot(xs, s["intercept"] + s["slope"] * xs, color="#b5541c", lw=1.4,
            label=f"OLS slope {s['slope']:.2f}, R² {s['r2']:.2f}, p {s['p_value']:.2f}")
    ax.axvline(0, color="#555", lw=0.8)
    ax.set_xlabel("Shilling depreciation vs USD (%)")
    ax.set_ylabel("Inflation (%)")
    ax.set_title("Does a weaker shilling mean higher inflation?")
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout(); fig.savefig(FIG / "shilling_and_inflation.png"); plt.close(fig)


def chart_external(p):
    k = p.xs("Kenya", level="country")
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(k.index, k["remittances_pct_gdp"], color=PALETTE["Kenya"], lw=2.4, label="Diaspora remittances")
    ax.plot(k.index, k["exports_pct_gdp"], color="#3d6fb4", lw=1.6, label="Exports")
    ax.plot(k.index, k["imports_pct_gdp"], color="#b5541c", lw=1.6, label="Imports")
    ax.fill_between(k.index, k["exports_pct_gdp"], k["imports_pct_gdp"], color="#b5541c", alpha=0.08,
                    label="Trade deficit")
    ax.set_ylabel("% of GDP")
    ax.set_title("Kenya: a persistent trade deficit, increasingly offset by diaspora remittances")
    ax.legend(frameon=False, ncol=4)
    fig.tight_layout(); fig.savefig(FIG / "kenya_external.png"); plt.close(fig)


def chart_correlation(p):
    k = p.xs("Kenya", level="country")
    cols = {"gdp_growth_pct": "GDP growth", "inflation_pct": "Inflation", "fx_depreciation_pct": "KES depreciation",
            "lending_rate_pct": "Lending rate", "remittances_pct_gdp": "Remittances", "trade_balance_pct_gdp": "Trade balance",
            "agriculture_pct_gdp": "Agriculture share"}
    corr = k[list(cols)].rename(columns=cols).corr(method="spearman")
    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=40, ha="right")
    ax.set_yticks(range(len(corr)), corr.columns)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(corr.iloc[i, j]) > 0.6 else "#222")
    ax.grid(False)
    ax.set_title("Kenya 2000-2024: Spearman correlations")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout(); fig.savefig(FIG / "kenya_correlations.png"); plt.close(fig)
    return corr


def main() -> None:
    FIG.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    p, flags = flag_series_breaks(load())
    flags.to_csv(OUT / "data_quality_flags.csv", index=False)
    print("Series breaks removed:\n", flags.round(2).to_string(index=False), "\n")
    p = add_derived(p)
    p.to_csv(OUT / "panel_clean.csv")

    infl = inflation_profile(p)
    growth = growth_profile(p)
    periods = kenya_periods(p)
    fx = fx_passthrough(p)
    rem = remittance_trend(p)

    infl.to_csv(OUT / "inflation_profile.csv")
    growth.to_csv(OUT / "growth_profile.csv")
    periods.to_csv(OUT / "kenya_periods.csv")

    chart_inflation(p)
    chart_gdp_index(p)
    chart_shilling(p, fx)
    chart_external(p)
    corr = chart_correlation(p)
    corr.round(3).to_csv(OUT / "kenya_correlations.csv")

    pd.set_option("display.width", 160)
    print("Inflation profile\n", infl, "\n")
    print("Growth profile\n", growth, "\n")
    print("Kenya by period\n", periods, "\n")
    print("FX pass-through", {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in fx.items()}, "\n")
    print("Remittances", {k: round(v, 3) if isinstance(v, float) else v for k, v in rem.items()})
    k = p.xs("Kenya", level="country")
    print("\nKenya FX levels:", k["fx_lcu_per_usd"].round(1).to_dict())
    print("Kenya FX depreciation:", k["fx_depreciation_pct"].round(1).to_dict())
    print("Debt coverage:", p["central_govt_debt_pct_gdp"].dropna().groupby(level="country").size().to_dict())


if __name__ == "__main__":
    main()
