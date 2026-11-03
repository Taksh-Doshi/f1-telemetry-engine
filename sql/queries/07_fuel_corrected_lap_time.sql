-- Question: What are lap times adjusted to the starting-fuel reference using an estimated fuel penalty?
-- Estimate only: 0.03 seconds per lap is an illustrative fuel-burn penalty, not a measured constant.
WITH parameters AS (
    SELECT 0.03::double precision AS estimated_seconds_lost_per_lap
),
corrected_laps AS (
    SELECT
        clean.year,
        clean.round,
        clean.event_name,
        clean.driver_code,
        clean.lap_number,
        clean.lap_time_seconds,
        clean.lap_time_seconds
            + (clean.lap_number - 1) * parameters.estimated_seconds_lost_per_lap
            AS estimated_start_fuel_lap_seconds,
        parameters.estimated_seconds_lost_per_lap
    FROM clean_laps AS clean
    CROSS JOIN parameters
    WHERE clean.session_type = 'R'
)
SELECT
    year,
    round,
    event_name,
    driver_code,
    lap_number,
    estimated_seconds_lost_per_lap,
    round(lap_time_seconds::numeric, 3) AS observed_lap_seconds,
    round(estimated_start_fuel_lap_seconds::numeric, 3)
        AS estimated_start_fuel_lap_seconds
FROM corrected_laps
ORDER BY year, round, driver_code, lap_number
LIMIT 10;
