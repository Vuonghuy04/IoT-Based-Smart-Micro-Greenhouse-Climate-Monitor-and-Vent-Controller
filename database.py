from contextlib import contextmanager
import re

import mariadb

from config import Config


CREATE_SENSOR_LOG_SQL = """
CREATE TABLE IF NOT EXISTS sensor_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    temperature DECIMAL(5, 2) NOT NULL,
    humidity DECIMAL(5, 2) NOT NULL,
    steam_value INT NOT NULL,
    vent_state VARCHAR(20) NOT NULL,
    led_state VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sensor_log_created_at (created_at)
)
"""

CREATE_CONTROL_RULE_SQL = """
CREATE TABLE IF NOT EXISTS control_rule (
    id INT PRIMARY KEY,
    humidity_threshold DECIMAL(5, 2) NOT NULL,
    steam_threshold INT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
)
"""

CREATE_COMMAND_LOG_SQL = """
CREATE TABLE IF NOT EXISTS command_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    command VARCHAR(30) NOT NULL,
    source VARCHAR(30) NOT NULL,
    success TINYINT(1) NOT NULL DEFAULT 1,
    message VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_command_log_created_at (created_at)
)
"""


def _safe_identifier(identifier):
    """Allow simple database names while preventing SQL injection in identifiers."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", identifier):
        raise ValueError(f"Unsafe database identifier: {identifier}")
    return f"`{identifier}`"


def _connect(database=None):
    return mariadb.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=database,
        autocommit=False,
    )


@contextmanager
def get_connection():
    """Open a MariaDB connection and commit or roll back automatically."""
    conn = _connect(Config.DB_NAME)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database():
    """Create the database, tables, and default rule row if needed."""
    db_name = _safe_identifier(Config.DB_NAME)

    server_conn = _connect()
    try:
        cur = server_conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS {db_name} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        server_conn.commit()
    finally:
        server_conn.close()

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(CREATE_SENSOR_LOG_SQL)
        cur.execute(CREATE_CONTROL_RULE_SQL)
        cur.execute(CREATE_COMMAND_LOG_SQL)
        cur.execute(
            """
            INSERT IGNORE INTO control_rule
                (id, humidity_threshold, steam_threshold)
            VALUES (?, ?, ?)
            """,
            (
                1,
                Config.DEFAULT_HUMIDITY_THRESHOLD,
                Config.DEFAULT_STEAM_THRESHOLD,
            ),
        )


def insert_sensor_reading(reading):
    """Store one parsed Arduino reading in sensor_log."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sensor_log
                (temperature, humidity, steam_value, vent_state, led_state)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                reading["temperature"],
                reading["humidity"],
                reading["steam_value"],
                reading["vent_state"],
                reading["led_state"],
            ),
        )
        return cur.lastrowid


def get_latest_reading():
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, temperature, humidity, steam_value,
                   vent_state, led_state, created_at
            FROM sensor_log
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
        return cur.fetchone()


def get_recent_readings(limit=None):
    limit = int(limit or Config.HISTORY_LIMIT)
    limit = max(1, min(limit, 500))
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, temperature, humidity, steam_value,
                   vent_state, led_state, created_at
            FROM sensor_log
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


def get_thresholds():
    """Load the active threshold row from control_rule."""
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, humidity_threshold, steam_threshold, updated_at
            FROM control_rule
            WHERE id = 1
            """
        )
        thresholds = cur.fetchone()

        if thresholds:
            return thresholds

        cur.execute(
            """
            INSERT INTO control_rule
                (id, humidity_threshold, steam_threshold)
            VALUES (?, ?, ?)
            """,
            (
                1,
                Config.DEFAULT_HUMIDITY_THRESHOLD,
                Config.DEFAULT_STEAM_THRESHOLD,
            ),
        )
        return {
            "id": 1,
            "humidity_threshold": Config.DEFAULT_HUMIDITY_THRESHOLD,
            "steam_threshold": Config.DEFAULT_STEAM_THRESHOLD,
            "updated_at": None,
        }


def update_thresholds(humidity_threshold, steam_threshold):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE control_rule
            SET humidity_threshold = ?, steam_threshold = ?
            WHERE id = 1
            """,
            (humidity_threshold, steam_threshold),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO control_rule
                    (id, humidity_threshold, steam_threshold)
                VALUES (?, ?, ?)
                """,
                (1, humidity_threshold, steam_threshold),
            )


def log_command(command, source, success=True, message=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO command_log (command, source, success, message)
            VALUES (?, ?, ?, ?)
            """,
            (command, source, 1 if success else 0, message),
        )


def get_recent_commands(limit=None):
    limit = int(limit or Config.COMMAND_LIMIT)
    limit = max(1, min(limit, 100))
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, command, source, success, message, created_at
            FROM command_log
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


def get_statistics():
    """Return min, max, and mean values from sensor_log."""
    with get_connection() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT
                COUNT(*) AS reading_count,
                MIN(temperature) AS temperature_min,
                MAX(temperature) AS temperature_max,
                AVG(temperature) AS temperature_mean,
                MIN(humidity) AS humidity_min,
                MAX(humidity) AS humidity_max,
                AVG(humidity) AS humidity_mean,
                MIN(steam_value) AS steam_min,
                MAX(steam_value) AS steam_max,
                AVG(steam_value) AS steam_mean
            FROM sensor_log
            """
        )
        return cur.fetchone()
