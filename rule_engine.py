import database
from config import Config


AUTO_SOURCE = "auto_rule"


def _default_thresholds():
    return {
        "humidity_threshold": Config.DEFAULT_HUMIDITY_THRESHOLD,
        "steam_threshold": Config.DEFAULT_STEAM_THRESHOLD,
    }


def load_thresholds():
    """Read thresholds from MariaDB, falling back to configured defaults."""
    try:
        return database.get_thresholds()
    except Exception:
        return _default_thresholds()


def evaluate_reading(reading, thresholds=None):
    """Return the commands required by the latest greenhouse reading."""
    thresholds = thresholds or load_thresholds()

    humidity_threshold = float(thresholds["humidity_threshold"])
    steam_threshold = int(thresholds["steam_threshold"])

    needs_venting = (
        float(reading["humidity"]) > humidity_threshold
        or int(reading["steam_value"]) > steam_threshold
    )

    if needs_venting:
        commands = ["OPEN", "LED_ON"]
    else:
        commands = ["CLOSE", "LED_OFF"]

    return commands, needs_venting


def apply_rules(reading, command_sender):
    """Apply automatic control rules and send needed Arduino commands."""
    commands, needs_venting = evaluate_reading(reading)

    for command in commands:
        command_sender.send_command(command, source=AUTO_SOURCE)

    return {
        "needs_venting": needs_venting,
        "commands": commands,
    }
