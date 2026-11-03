-- Question: How much faster or slower was each clean lap than the driver's immediately previous race lap?
WITH lap_changes AS (
    SELECT
        year,
        round,
        event_name,
        driver_code,
        lap_number,
        lap_time_seconds,
        lag(lap_number) OVER (
            PARTITION BY year, round, driver_code
            ORDER BY lap_number
        ) AS previous_lap_number,
        lag(lap_time_seconds) OVER (
            PARTITION BY year, round, driver_code
            ORDER BY lap_number
        ) AS previous_lap_seconds
    FROM clean_laps
    WHERE session_type = 'R'
)
SELECT
    year,
    round,
    event_name,
    driver_code,
    lap_number,
    previous_lap_number,
    round((lap_time_seconds - previous_lap_seconds)::numeric, 3) AS delta_seconds
FROM lap_changes
WHERE previous_lap_number = lap_number - 1
ORDER BY year, round, driver_code, lap_number
LIMIT 10;
