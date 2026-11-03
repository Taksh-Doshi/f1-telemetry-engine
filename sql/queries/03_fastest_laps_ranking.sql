-- Question: How do each driver's fastest clean laps rank within each race?
WITH driver_best_laps AS (
    SELECT
        year,
        round,
        event_name,
        driver_code,
        min(lap_time_seconds) AS fastest_clean_lap_seconds
    FROM clean_laps
    WHERE session_type = 'R'
    GROUP BY year, round, event_name, driver_code
)
SELECT
    year,
    round,
    event_name,
    driver_code,
    fastest_clean_lap_seconds,
    rank() OVER (
        PARTITION BY year, round
        ORDER BY fastest_clean_lap_seconds
    ) AS race_rank
FROM driver_best_laps
ORDER BY year, round, race_rank, driver_code
LIMIT 10;
