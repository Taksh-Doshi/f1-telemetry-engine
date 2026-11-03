-- Question: What are the average and median clean lap times for each tyre compound at each circuit?
SELECT
    event_name AS circuit,
    compound,
    count(*) AS clean_laps,
    round(avg(lap_time_seconds)::numeric, 3) AS average_lap_seconds,
    round(
        percentile_cont(0.5) WITHIN GROUP (ORDER BY lap_time_seconds)::numeric,
        3
    ) AS median_lap_seconds
FROM clean_laps
WHERE session_type = 'R'
  AND compound IS NOT NULL
GROUP BY event_name, compound
ORDER BY event_name, compound
LIMIT 10;
