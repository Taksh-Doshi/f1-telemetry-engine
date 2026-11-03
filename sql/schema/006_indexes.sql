CREATE INDEX IF NOT EXISTS idx_laps_clean_analysis
ON laps (session_id, driver_id, lap_number)
INCLUDE (lap_time_seconds, compound, tyre_life, stint_number, team)
WHERE pit_in_time_seconds IS NULL
  AND pit_out_time_seconds IS NULL
  AND COALESCE(track_status, '') !~ '[4567]'
  AND (compound IS NULL OR compound NOT IN ('INTERMEDIATE', 'WET'))
  AND lap_time_seconds IS NOT NULL
  AND deleted IS NOT TRUE
  AND is_accurate IS TRUE
  AND lap_number > 1;
