-- Question: How many clean laps did each driver  in each tyre stint?
SELECT
    year,
    round,
    event_name,
    driver_code,
    stint_number,
    compound,
    count(*) AS clean_lap_count,
    min(lap_number) AS first_clean_lap,
    max(lap_number) AS last_clean_lap
FROM clean_laps
WHERE session_type = 'R'
GROUP BY
    year,
    round,
    event_name,
    driver_code,
    stint_number,
    compound
ORDER BY year, round, driver_code, stint_number
LIMIT 10;
