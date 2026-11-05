"""India's toll network: an end-to-end data analysis.

Source: toll_plazas_raw.csv, the plaza registry from my Smart Toll Plaza project (list dated 26 May 2026).
Pipeline: profile -> clean with pandas (every change is logged) -> load into SQL -> answer questions -> export.

Run:  python analysis.py
Out:  toll_plazas_clean.csv, cleaning_log.csv, toll.db, results.json
"""
import json
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
log = []  # one row per change or flag: what happened, to which plaza, and why


def note(code, name, issue, before, after):
    log.append({"plaza_code": code, "plaza_name": name, "issue": issue, "before": before, "after": after})


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))


# ---------- 1. Load ----------
raw = pd.read_csv(HERE / "toll_plazas_raw.csv", dtype=str, keep_default_na=False)
df = raw.rename(columns={
    "PLAZA CODE": "plaza_code", "PLAZA NAME": "plaza_name", "CONCESSIONAIRE TYPE": "funding_raw",
    "PLAZA SUB TYPE": "road_class", "STATE": "state", "CITY": "city", "LATITUDE": "lat", "LONGITUDE": "lon",
}).copy()

# ---------- 2. Clean ----------
# 2a. 16 spellings of the funding type collapse into 6 real categories.
FUNDING = {
    "conc": "Concession", "conce": "Concession", "concessio": "Concession",
    "pf": "Public Funded", "public fun": "Public Funded",
    "bot": "BOT", "tot": "TOT", "dbfot": "DBFOT", "nhai": "NHAI", "state": "State",
}
key = df["funding_raw"].str.lower().str.strip(" .")
df["funding"] = key.map(FUNDING)
assert df["funding"].notna().all(), "a funding spelling is not mapped"
changed = df["funding_raw"] != df["funding"]
funding_variants = int(df["funding_raw"].nunique())
for r in df[changed & ~df["funding_raw"].isin(["PF", "Conc."])].itertuples():
    note(r.plaza_code, r.plaza_name, "funding spelling", r.funding_raw, r.funding)

# 2b. Truncated state name.
for r in df[df["state"] == "Uttarakha"].itertuples():
    note(r.plaza_code, r.plaza_name, "state typo", r.state, "Uttarakhand")
df["state"] = df["state"].replace({"Uttarakha": "Uttarakhand"})

# 2c. Tidy names and cities (case and spacing only).
df["plaza_name"] = df["plaza_name"].str.replace(r"\s+", " ", regex=True).str.strip()
df["city"] = df["city"].str.replace(r"\s+", " ", regex=True).str.strip().str.title()
df["road_class"] = df["road_class"].str.title()

# 2d. Longitudes that lost their decimal point: 731669180 -> 73.1669180.
df["lat"] = df["lat"].astype(float)
df["lon"] = df["lon"].astype(float)
for i in df.index[df["lon"] > 180]:
    digits = re.sub(r"\D", "", f"{df.at[i, 'lon']:.0f}")
    fixed = float(digits[:2] + "." + digits[2:])
    note(df.at[i, "plaza_code"], df.at[i, "plaza_name"], "decimal point lost", df.at[i, "lon"], fixed)
    df.at[i, "lon"] = fixed

# 2e. Likely duplicate records: same name, same state, under 2 km apart, different codes.
df["name_key"] = df["plaza_name"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
df["is_duplicate"] = False
for _, g in df[df.duplicated(["name_key", "state"], keep=False)].groupby(["name_key", "state"]):
    first = g.iloc[0]
    for i, r in g.iloc[1:].iterrows():
        if haversine(first.lat, first.lon, r.lat, r.lon) < 2:
            df.at[i, "is_duplicate"] = True
            note(r.plaza_code, r.plaza_name, "likely duplicate record", f"same as code {first.plaza_code}", "excluded from counts")
duplicates = int(df["is_duplicate"].sum())
df = df[~df["is_duplicate"]].copy()

# 2f. Coordinates that can't be right: far outside the plaza's own state.
#     No map boundaries needed: a plaza should sit near the other plazas of its state.
med = df.groupby("state")[["lat", "lon"]].transform("median")
df["km_from_state_centre"] = haversine(df["lat"], df["lon"], med["lat"], med["lon"])
stats = df.groupby("state")["km_from_state_centre"].quantile([0.25, 0.75]).unstack()
limit = (stats[0.75] + 3 * (stats[0.75] - stats[0.25])).clip(lower=350)
df["coord_suspect"] = df["km_from_state_centre"] > df["state"].map(limit)
# Several different plazas sharing one exact coordinate is a copy-paste sign too.
shared = df.groupby(["lat", "lon"])["plaza_code"].transform("count") > 1
df["coord_shared"] = shared
for r in df[df["coord_suspect"]].itertuples():
    note(r.plaza_code, r.plaza_name, "coordinates far outside state", f"{r.lat},{r.lon} ({r.state})", f"flagged, {r.km_from_state_centre:.0f} km off")
for r in df[df["coord_shared"] & ~df["coord_suspect"]].itertuples():
    note(r.plaza_code, r.plaza_name, "coordinate shared with another plaza", f"{r.lat},{r.lon}", "flagged")
df["geo_ok"] = ~(df["coord_suspect"] | df["coord_shared"])

# 2g. Nearest neighbour, using trustworthy coordinates only.
geo = df[df["geo_ok"]]
la, lo = geo["lat"].to_numpy(), geo["lon"].to_numpy()
d = haversine(la[:, None], lo[:, None], la[None, :], lo[None, :])
np.fill_diagonal(d, np.inf)
df["nearest_km"] = pd.Series(d.min(axis=1), index=geo.index).round(1)

clean = df[["plaza_code", "plaza_name", "funding", "road_class", "state", "city", "lat", "lon", "geo_ok", "coord_suspect", "coord_shared", "nearest_km"]]
clean.to_csv(HERE / "toll_plazas_clean.csv", index=False)
pd.DataFrame(log).to_csv(HERE / "cleaning_log.csv", index=False)

# ---------- 3. Load into SQL and run the questions ----------
db = HERE / "toll.db"
db.unlink(missing_ok=True)
con = sqlite3.connect(db)
clean.to_sql("toll_plazas", con, index=False)

queries = {}
for block in (HERE / "queries.sql").read_text(encoding="utf-8").split("-- @")[1:]:
    head, sql = block.split("\n", 1)
    queries[head.strip()] = sql.strip().rstrip(";")
answers = {name: pd.read_sql_query(sql, con).to_dict("records") for name, sql in queries.items()}
con.close()

# ---------- 4. Export ----------
results = {
    "rows_raw": int(len(raw)),
    "rows_clean": int(len(clean)),
    "funding_variants": funding_variants,
    "funding_categories": int(clean["funding"].nunique()),
    "states": int(clean["state"].nunique()),
    "duplicates_removed": duplicates,
    "decimal_fixes": int(sum(1 for l in log if l["issue"] == "decimal point lost")),
    "coords_suspect": int(clean["coord_suspect"].sum()),
    "coords_shared": int((clean["coord_shared"] & ~clean["coord_suspect"]).sum()),
    "geo_ok": int(clean["geo_ok"].sum()),
    "log_rows": len(log),
    **answers,
}
(HERE / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in results.items() if not isinstance(v, list)}, indent=1))
for name, rows in answers.items():
    print("\n#", name)
    print(pd.DataFrame(rows).to_string(index=False))
