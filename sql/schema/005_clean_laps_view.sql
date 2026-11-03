CREATE OR REPLACE VIEW clean_laps AS
SELECT
    e.season_year AS year,
    e.round_number AS round,
    e.event_name,
    e.location,
    s.session_name,
    s.session_type,
    d.abbreviation AS driver_code,
    l.team,
    l.compound,
    l.tyre_life,
    l.stint_number,
    l.lap_number,
    l.lap_time_seconds
FROM laps AS l
JOIN sessions AS s ON s.session_id = l.session_id
JOIN events AS e ON e.event_id = s.event_id
JOIN drivers AS d ON d.driver_id = l.driver_id
WHERE
    -- Pit-in timing marks an in-lap and pit-out timing marks an out-lap
    l.pit_in_time_seconds IS NULL
    AND l.pit_out_time_seconds IS NULL
    -- Track status may contain several codes, so exclude any safety or red flag code
    AND COALESCE(l.track_status, '') !~ '[4567]'
    -- Keep dry compounds and unknown compounds, excluding intermediate and wet tyres
    AND (
        l.compound IS NULL
        OR l.compound NOT IN ('INTERMEDIATE', 'WET')
    )
    -- A lap without a measured lap time cannot be used for pace comparisons
    AND l.lap_time_seconds IS NOT NULL
    -- Exclude laps explicitly marked deleted while retaining unmarked NULL values
    AND l.deleted IS NOT TRUE
    -- Keep laps FastF1 marked as accurate
    AND l.is_accurate IS TRUE
    -- Lap one is excluded to avoid formation and opening-lap effects
    AND l.lap_number > 1;
