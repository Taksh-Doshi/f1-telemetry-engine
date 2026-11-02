CREATE TABLE IF NOT EXISTS telemetry_samples (
    session_id BIGINT NOT NULL,
    driver_id BIGINT NOT NULL,
    lap_number SMALLINT NOT NULL,
    time_seconds DOUBLE PRECISION NOT NULL,
    speed DOUBLE PRECISION,
    throttle DOUBLE PRECISION,
    brake BOOLEAN,
    gear SMALLINT,
    rpm INTEGER,
    drs SMALLINT,
    x DOUBLE PRECISION,
    y DOUBLE PRECISION,
    CONSTRAINT pk_telemetry_samples
        PRIMARY KEY (session_id, driver_id, time_seconds),
    CONSTRAINT fk_telemetry_samples_session
        FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE,
    CONSTRAINT fk_telemetry_samples_driver
        FOREIGN KEY (driver_id) REFERENCES drivers (driver_id)
) PARTITION BY LIST (session_id);
