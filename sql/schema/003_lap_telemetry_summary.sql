CREATE TABLE IF NOT EXISTS lap_telemetry_summary (
    lap_id BIGINT NOT NULL,
    top_speed DOUBLE PRECISION,
    mean_speed DOUBLE PRECISION,
    mean_throttle DOUBLE PRECISION,
    full_throttle_pct DOUBLE PRECISION,
    brake_pct DOUBLE PRECISION,
    drs_pct DOUBLE PRECISION,
    gear_changes DOUBLE PRECISION,
    CONSTRAINT pk_lap_telemetry_summary PRIMARY KEY (lap_id),
    CONSTRAINT fk_lap_telemetry_summary_lap FOREIGN KEY (lap_id)
        REFERENCES laps (lap_id) ON DELETE CASCADE
);
