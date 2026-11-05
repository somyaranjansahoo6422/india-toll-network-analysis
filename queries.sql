-- India's toll network: the questions, answered in SQL.
-- Standard SQL with CTEs and window functions: runs on MySQL 8 and on SQLite (which analysis.py uses).

-- @top_states
-- Where are the toll plazas? Each state's share, and the running total.
WITH per_state AS (
  SELECT state, COUNT(*) AS plazas FROM toll_plazas GROUP BY state
)
SELECT state, plazas,
       ROUND(100.0 * plazas / SUM(plazas) OVER (), 1) AS share_pct,
       ROUND(100.0 * SUM(plazas) OVER (ORDER BY plazas DESC, state) / SUM(plazas) OVER (), 1) AS running_pct
FROM per_state
ORDER BY plazas DESC, state;

-- @funding_mix
-- Who pays for the roads? Funding model on national vs state roads.
SELECT road_class, funding, COUNT(*) AS plazas,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY road_class), 1) AS share_of_class_pct
FROM toll_plazas
GROUP BY road_class, funding
ORDER BY road_class, plazas DESC;

-- @private_share
-- Which big states lean on private operators? (Concession, BOT, TOT and DBFOT are private models.)
SELECT state, COUNT(*) AS plazas,
       SUM(CASE WHEN funding IN ('Concession', 'BOT', 'TOT', 'DBFOT') THEN 1 ELSE 0 END) AS private_plazas,
       ROUND(100.0 * SUM(CASE WHEN funding IN ('Concession', 'BOT', 'TOT', 'DBFOT') THEN 1 ELSE 0 END) / COUNT(*), 1) AS private_pct
FROM toll_plazas
GROUP BY state
HAVING COUNT(*) >= 50
ORDER BY private_pct DESC;

-- @spacing
-- How close together are plazas? Straight-line distance to the nearest plaza on any road,
-- so this shows clusters, not rule breaches.
SELECT CASE WHEN nearest_km < 10 THEN 'Under 10 km'
            WHEN nearest_km < 30 THEN '10-30 km'
            WHEN nearest_km < 60 THEN '30-60 km'
            ELSE '60 km or more' END AS gap,
       COUNT(*) AS plazas,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct
FROM toll_plazas
WHERE geo_ok = 1
GROUP BY gap
ORDER BY MIN(nearest_km);

-- @spacing_by_state
-- The median-like view by state: average gap and how many plazas sit within 10 km of another.
SELECT state, COUNT(*) AS plazas, ROUND(AVG(nearest_km), 1) AS avg_nearest_km,
       SUM(CASE WHEN nearest_km < 10 THEN 1 ELSE 0 END) AS within_10km
FROM toll_plazas
WHERE geo_ok = 1
GROUP BY state
HAVING COUNT(*) >= 50
ORDER BY avg_nearest_km;

-- @quality_by_state
-- Where is the data least trustworthy? Share of plazas with suspect or shared coordinates.
SELECT state, COUNT(*) AS plazas,
       SUM(CASE WHEN geo_ok = 0 THEN 1 ELSE 0 END) AS flagged,
       ROUND(100.0 * SUM(CASE WHEN geo_ok = 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS flagged_pct
FROM toll_plazas
GROUP BY state
HAVING COUNT(*) >= 20
ORDER BY flagged_pct DESC
LIMIT 8;
