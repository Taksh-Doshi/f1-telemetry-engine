-- Question: What is each driver's rolling average over three consecutive clean laps?
WITH rolling_laps AS (
    SELECT
        year,
        round,
        event_name,
        driver_code,
        lap_number,
        lap_time_seconds,
        lag(lap_number, 1) OVER driver_laps AS previous_lap,
        lag(lap_number, 2) OVER driver_laps AS second_previous_lap,
        avg(lap_time_seconds) OVER (
            driver_laps ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS rolling_three_lap_seconds
    FROM clean_laps
    WHERE session_type = 'R'
    WINDOW driver_laps AS (
        PARTITION BY year, round, driver_code
        ORDER BY lap_number
    )
)
SELECT
    year,
    round,
    event_name,
    driver_code,
    lap_number,
    round(rolling_three_lap_seconds::numeric, 3) AS rolling_three_lap_seconds
FROM rolling_laps
WHERE previous_lap = lap_number - 1
  AND second_previous_lap = lap_number - 2
ORDER BY year, round, driver_code, lap_number
LIMIT 10;
