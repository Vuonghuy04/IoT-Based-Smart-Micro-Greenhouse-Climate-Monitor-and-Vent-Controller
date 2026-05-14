import os


def _bool_from_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Central settings for the greenhouse edge application."""

    PROJECT_NAME = "IoT-Based Smart Micro-Greenhouse Climate Monitor and Vent Controller"

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
    DEBUG = _bool_from_env("FLASK_DEBUG", False)
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

    # Arduino serial connection
    SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
    SERIAL_BAUD_RATE = int(os.getenv("SERIAL_BAUD_RATE", "9600"))
    SERIAL_TIMEOUT = float(os.getenv("SERIAL_TIMEOUT", "1"))
    SERIAL_RECONNECT_SECONDS = float(os.getenv("SERIAL_RECONNECT_SECONDS", "5"))
    START_SERIAL_THREAD = _bool_from_env("START_SERIAL_THREAD", True)

    # MariaDB connection
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "greenhouse_iot")

    # Default rule values inserted into control_rule when the table is empty.
    DEFAULT_HUMIDITY_THRESHOLD = float(os.getenv("DEFAULT_HUMIDITY_THRESHOLD", "80.0"))
    DEFAULT_STEAM_THRESHOLD = int(os.getenv("DEFAULT_STEAM_THRESHOLD", "80"))

    # Dashboard sizes
    HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "50"))
    COMMAND_LIMIT = int(os.getenv("COMMAND_LIMIT", "10"))
