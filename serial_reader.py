import re
import threading
import time

import serial

import database
from config import Config
from rule_engine import apply_rules


SENSOR_LINE_PATTERN = re.compile(
    r"^TEMP:(?P<temperature>-?\d+(?:\.\d+)?),"
    r"HUM:(?P<humidity>\d+(?:\.\d+)?),"
    r"STEAM:(?P<steam_value>\d+),"
    r"VENT:(?P<vent_state>[A-Za-z]+),"
    r"LED:(?P<led_state>[A-Za-z]+)$"
)

ALLOWED_COMMANDS = {"OPEN", "CLOSE", "LED_ON", "LED_OFF"}


def parse_sensor_line(line):
    """Parse one Arduino line into a dictionary of sensor values."""
    match = SENSOR_LINE_PATTERN.match(line.strip())
    if not match:
        raise ValueError(f"Invalid sensor line: {line!r}")

    data = match.groupdict()
    return {
        "temperature": float(data["temperature"]),
        "humidity": float(data["humidity"]),
        "steam_value": int(data["steam_value"]),
        "vent_state": data["vent_state"].upper(),
        "led_state": data["led_state"].upper(),
    }


class SerialReader:
    """Background serial worker for Arduino readings and commands."""

    def __init__(self, port=None, baud_rate=None, timeout=None):
        self.port = port or Config.SERIAL_PORT
        self.baud_rate = baud_rate or Config.SERIAL_BAUD_RATE
        self.timeout = timeout or Config.SERIAL_TIMEOUT

        self._serial = None
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()

        self.connected = False
        self.last_error = None
        self.latest_reading = None
        self.last_line = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._close_serial()

    def status(self):
        return {
            "port": self.port,
            "connected": self.connected,
            "last_error": self.last_error,
            "last_line": self.last_line,
        }

    def send_command(self, command, source="manual"):
        """Send a command to Arduino and write the result to command_log."""
        command = command.strip().upper()

        if command not in ALLOWED_COMMANDS:
            message = f"Rejected invalid command: {command}"
            self._safe_log_command(command, source, False, message)
            return False, message

        try:
            self._ensure_connection()
            with self._lock:
                self._serial.write(f"{command}\n".encode("utf-8"))
                self._serial.flush()

            message = f"Sent {command}"
            self._safe_log_command(command, source, True, message)
            return True, message
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            self._close_serial()

            message = f"Could not send {command}: {exc}"
            self._safe_log_command(command, source, False, message)
            return False, message

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._ensure_connection()
                line = self._readline()
                if not line:
                    continue

                self.last_line = line
                reading = parse_sensor_line(line)
                self.latest_reading = reading

                try:
                    database.insert_sensor_reading(reading)
                except Exception as exc:
                    self.last_error = f"Database insert failed: {exc}"

                try:
                    apply_rules(reading, self)
                except Exception as exc:
                    self.last_error = f"Rule engine failed: {exc}"
            except ValueError as exc:
                self.last_error = str(exc)
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                self._close_serial()
                time.sleep(Config.SERIAL_RECONNECT_SECONDS)

    def _ensure_connection(self):
        with self._lock:
            if self._serial and self._serial.is_open:
                self.connected = True
                return

            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
            )
            time.sleep(2)
            self.connected = True
            self.last_error = None

    def _readline(self):
        with self._lock:
            raw = self._serial.readline()

        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").strip()

    def _close_serial(self):
        with self._lock:
            if self._serial:
                try:
                    self._serial.close()
                finally:
                    self._serial = None
            self.connected = False

    def _safe_log_command(self, command, source, success, message):
        try:
            database.log_command(command, source, success, message)
        except Exception as exc:
            self.last_error = f"Command log failed: {exc}"
