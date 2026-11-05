# India's toll network, in data

An end-to-end analysis of the plaza registry from my Smart Toll Plaza project (list dated 26 May 2026).

**Questions:** where are India's toll plazas, who runs them, how close together are they, and can this data be trusted?

## Run it

```
pip install pandas numpy
python analysis.py
```

It reads `toll_plazas_raw.csv`, runs the SQL in `queries.sql`, and writes `toll_plazas_clean.csv`, `cleaning_log.csv`, `toll.db` and `results.json`.

## Files

| File | What it is |
|---|---|
| `analysis.py` | Cleaning pipeline: every change is logged |
| `queries.sql` | The questions in SQL (CTEs, window functions). Written for MySQL 8, run here on SQLite |
| `cleaning_log.csv` | All 159 records that were fixed or flagged, and why |

## Main findings

- Four states (Rajasthan, Uttar Pradesh, Madhya Pradesh, Maharashtra) hold 53.6% of 1,997 plazas.
- 73.5% of national-road plazas are publicly funded, while 65% of state-road plazas use private models.
- Karnataka has the highest private share among big states (71.7%), Punjab the lowest (17.6%).
- 29.6% of plazas have another plaza within 10 km in a straight line.

## Limits

A single snapshot with no traffic or revenue data. Distances are straight lines on any road, so they show clusters, not rule breaches. Concession, BOT, TOT and DBFOT are grouped as "private".
