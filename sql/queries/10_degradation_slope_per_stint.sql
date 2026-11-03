-- Question: What is the estimated lap-time degradation slope per tyre-life lap for each stint?
SELECT
    year,
    round,
    event_name,
    driver_code,
    stint_number,
    compound,
    count(*) AS clean_laps,
    round(regr_slope(lap_time_seconds, tyre_life)::numeric, 4)
        AS seconds_per_tyre_life_lap
FROM clean_laps
WHERE session_type = 'R'
  AND tyre_life IS NOT NULL
  AND stint_number IS NOT NULL
GROUP BY year, round, event_name, driver_code, stint_number, compound
HAVING count(*) >= 5
ORDER BY year, round, driver_code, stint_number
LIMIT 10;
