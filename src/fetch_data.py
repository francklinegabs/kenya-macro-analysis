"""Download macro indicators for Kenya and its East African peers from the World Bank API.

Writes one tidy CSV (country, indicator, year, value) to data/worldbank_raw.csv.
Run:  python src/fetch_data.py
"""
from __future__ import annotations

import csv
import json
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

COUNTRIES = {
    "KEN": "Kenya",
    "UGA": "Uganda",
    "TZA": "Tanzania",
    "RWA": "Rwanda",
    "ETH": "Ethiopia",
}

INDICATORS = {
    "FP.CPI.TOTL.ZG": "inflation_pct",
    "NY.GDP.MKTP.KD.ZG": "gdp_growth_pct",
    "NY.GDP.PCAP.KD": "gdp_per_capita_usd_2015",
    "PA.NUS.FCRF": "fx_lcu_per_usd",
    "BX.TRF.PWKR.DT.GD.ZS": "remittances_pct_gdp",
    "NE.EXP.GNFS.ZS": "exports_pct_gdp",
    "NE.IMP.GNFS.ZS": "imports_pct_gdp",
    "GC.DOD.TOTL.GD.ZS": "central_govt_debt_pct_gdp",
    "FR.INR.LEND": "lending_rate_pct",
    "SP.POP.TOTL": "population",
    "SL.UEM.TOTL.ZS": "unemployment_pct",
    "NV.AGR.TOTL.ZS": "agriculture_pct_gdp",
}

START, END = 2000, 2024
URL = (
    "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
    "?format=json&per_page=2000&date={start}:{end}"
)


def fetch_indicator(code: str) -> list[dict]:
    url = URL.format(countries=";".join(COUNTRIES), indicator=code, start=START, end=END)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                payload = json.load(resp)
            break
        except Exception:  # network hiccups are common on this API
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    if len(payload) < 2 or payload[1] is None:
        return []
    return payload[1]


def main() -> None:
    DATA.mkdir(exist_ok=True)
    rows = []
    for code, name in INDICATORS.items():
        records = fetch_indicator(code)
        kept = 0
        for r in records:
            if r["value"] is None:
                continue
            rows.append(
                {
                    "iso3": r["countryiso3code"],
                    "country": COUNTRIES.get(r["countryiso3code"], r["country"]["value"]),
                    "indicator": name,
                    "year": int(r["date"]),
                    "value": r["value"],
                }
            )
            kept += 1
        print(f"{name:<28} {kept:>4} observations")

    out = DATA / "worldbank_raw.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["iso3", "country", "indicator", "year", "value"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["indicator"], r["iso3"], r["year"])))
    print(f"\nWrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
