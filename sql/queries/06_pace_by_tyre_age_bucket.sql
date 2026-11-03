-- Question: How does clean lap pace vary across tyre-age buckets?
WITH age_buckets AS (
    SELECT
        year,
        round,
        event_name,
        compound,
        CASE
            WHEN tyre_life BETWEEN 1 AND 2 THEN '01-02'
            WHEN tyre_life BETWEEN 3 AND 5 THEN '03-05'
            WHEN tyre_life BETWEEN 6 AND 10 THEN '06-10'
            WHEN tyre_life >= 11 THEN '11+'
            ELSE 'Unknown'
        END AS tyre_age_bucket,
        lap_time_seconds
    FROM clean_laps
    WHERE session_type = 'R'
)
SELECT
    event_name,
    compound,
    tyre_age_bucket,
    count(*) AS clean_laps,
    round(avg(lap_time_seconds)::numeric, 3) AS average_lap_seconds
FROM age_buckets
GROUP BY event_name, compound, tyre_age_bucket
ORDER BY event_name, compound, tyre_age_bucket
LIMIT 10;
