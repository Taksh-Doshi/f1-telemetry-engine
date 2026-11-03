-- Question: How do teams compare by average clean lap time within each race?
WITH team_pace AS (
    SELECT
        year,
        round,
        event_name,
        team,
        count(*) AS clean_laps,
        avg(lap_time_seconds) AS average_lap_seconds
    FROM clean_laps
    WHERE session_type = 'R'
      AND team IS NOT NULL
    GROUP BY year, round, event_name, team
)
SELECT
    year,
    round,
    event_name,
    team,
    clean_laps,
    round(average_lap_seconds::numeric, 3) AS average_lap_seconds,
    rank() OVER (
        PARTITION BY year, round
        ORDER BY average_lap_seconds
    ) AS team_pace_rank
FROM team_pace
ORDER BY year, round, team_pace_rank
LIMIT 10;
