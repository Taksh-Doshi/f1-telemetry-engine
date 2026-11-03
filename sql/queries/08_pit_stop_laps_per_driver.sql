-- Question: How many laps per driver have pit-in or pit-out timing recorded in each race?
SELECT
    e.season_year AS year,
    e.round_number AS round,
    e.event_name,
    d.abbreviation AS driver_code,
    count(*) FILTER (WHERE l.pit_in_time_seconds IS NOT NULL) AS pit_in_laps,
    count(*) FILTER (WHERE l.pit_out_time_seconds IS NOT NULL) AS pit_out_laps,
    count(*) FILTER (
        WHERE l.pit_in_time_seconds IS NOT NULL
           OR l.pit_out_time_seconds IS NOT NULL
    ) AS laps_with_pit_timing
FROM laps AS l
JOIN sessions AS s ON s.session_id = l.session_id
JOIN events AS e ON e.event_id = s.event_id
JOIN drivers AS d ON d.driver_id = l.driver_id
WHERE s.session_type = 'R'
GROUP BY e.season_year, e.round_number, e.event_name, d.abbreviation
HAVING count(*) FILTER (
    WHERE l.pit_in_time_seconds IS NOT NULL
       OR l.pit_out_time_seconds IS NOT NULL
) > 0
ORDER BY year, round, driver_code
LIMIT 10;
