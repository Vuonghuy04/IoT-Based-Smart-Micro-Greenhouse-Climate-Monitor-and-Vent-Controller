import database
import time
from config import Config


AUTO_SOURCE = "auto_rule"
CLOSED_STATES = {"CLOSED", "CLOSE"}


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
    needs_venting = reading_needs_venting(reading, thresholds)

    commands = []
    vent_state = _normalise_state(reading.get("vent_state"))
    led_state = _normalise_state(reading.get("led_state"))

    if needs_venting and not _vent_is_open(vent_state):
        commands.append("OPEN")
    elif not needs_venting and not _vent_is_closed(vent_state):
        commands.append("CLOSE")

    if commands:
        return commands, needs_venting

    if _vent_is_open(vent_state) and led_state != "ON":
        commands.append("LED_ON")
    elif _vent_is_closed(vent_state) and led_state != "OFF":
        commands.append("LED_OFF")

    return commands, needs_venting


def reading_needs_venting(reading, thresholds=None):
    thresholds = thresholds or load_thresholds()

    humidity_threshold = float(thresholds["humidity_threshold"])
    steam_threshold = int(thresholds["steam_threshold"])

    return (
        float(reading["humidity"]) > humidity_threshold
        or int(reading["steam_value"]) > steam_threshold
    )


class AutoController:
    """Stateful automatic controller that avoids servo chatter."""

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._vent_open_until = 0
        self._pending_servo_command = None
        self._pending_servo_at = 0

    def apply(self, reading, command_sender):
        now = self._clock()
        needs_venting = reading_needs_venting(reading)
        vent_state = _normalise_state(reading.get("vent_state"))
        led_state = _normalise_state(reading.get("led_state"))

        self._clear_confirmed_servo_command(vent_state)

        if needs_venting:
            self._vent_open_until = max(
                self._vent_open_until,
                now + Config.AUTO_VENT_MIN_OPEN_SECONDS,
            )

        desired_vent_open = needs_venting or now < self._vent_open_until
        commands = self._build_commands(
            now,
            vent_state,
            led_state,
            desired_vent_open,
        )
        sent_commands = self._send_commands(commands, command_sender)
        self._record_sent_servo_commands(now, sent_commands)

        return {
            "needs_venting": needs_venting,
            "holding_vent_open": desired_vent_open and not needs_venting,
            "commands": sent_commands,
        }

    def _build_commands(
        self,
        now,
        vent_state,
        led_state,
        desired_vent_open,
    ):
        commands = []
        servo_command = self._needed_servo_command(vent_state, desired_vent_open)

        if servo_command and self._can_send_servo_command(now):
            commands.append(servo_command)
            return commands

        if _vent_is_open(vent_state):
            if led_state != "ON":
                commands.append("LED_ON")
        elif _vent_is_closed(vent_state) and led_state != "OFF":
            commands.append("LED_OFF")

        return commands

    def _needed_servo_command(self, vent_state, desired_vent_open):
        if desired_vent_open and not _vent_is_open(vent_state):
            return "OPEN"
        if not desired_vent_open and not _vent_is_closed(vent_state):
            return "CLOSE"
        return None

    def _can_send_servo_command(self, now):
        if not self._pending_servo_command:
            return True

        if now - self._pending_servo_at >= Config.AUTO_SERVO_COMMAND_COOLDOWN_SECONDS:
            return True

        return False

    def _clear_confirmed_servo_command(self, vent_state):
        if not self._pending_servo_command:
            return

        if self._pending_servo_command == "OPEN" and _vent_is_open(vent_state):
            self._pending_servo_command = None
        elif self._pending_servo_command == "CLOSE" and _vent_is_closed(vent_state):
            self._pending_servo_command = None

    def _send_commands(self, commands, command_sender):
        sent_commands = []
        for command in commands:
            success, _ = command_sender.send_command(command, source=AUTO_SOURCE)
            if not success:
                break
            sent_commands.append(command)
        return sent_commands

    def _record_sent_servo_commands(self, now, commands):
        for command in commands:
            if command not in {"OPEN", "CLOSE"}:
                continue

            self._pending_servo_command = command
            self._pending_servo_at = now

            if command == "OPEN":
                self._vent_open_until = max(
                    self._vent_open_until,
                    now + Config.AUTO_VENT_MIN_OPEN_SECONDS,
                )


_default_controller = AutoController()


def apply_rules(reading, command_sender):
    """Apply automatic control rules and send needed Arduino commands."""
    return _default_controller.apply(reading, command_sender)


def _normalise_state(value):
    return str(value or "").strip().upper()


def _vent_is_open(value):
    return _normalise_state(value) == "OPEN"


def _vent_is_closed(value):
    return _normalise_state(value) in CLOSED_STATES
