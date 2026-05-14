CREATE DATABASE IF NOT EXISTS greenhouse_iot
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE greenhouse_iot;

CREATE TABLE IF NOT EXISTS sensor_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    temperature DECIMAL(5, 2) NOT NULL,
    humidity DECIMAL(5, 2) NOT NULL,
    steam_value INT NOT NULL,
    vent_state VARCHAR(20) NOT NULL,
    led_state VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sensor_log_created_at (created_at)
);

CREATE TABLE IF NOT EXISTS control_rule (
    id INT PRIMARY KEY,
    humidity_threshold DECIMAL(5, 2) NOT NULL,
    steam_threshold INT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO control_rule
    (id, humidity_threshold, steam_threshold)
VALUES
    (1, 80.00, 80);

CREATE TABLE IF NOT EXISTS command_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    command VARCHAR(30) NOT NULL,
    source VARCHAR(30) NOT NULL,
    success TINYINT(1) NOT NULL DEFAULT 1,
    message VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_command_log_created_at (created_at)
);
