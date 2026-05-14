import os

from flask import Flask, flash, redirect, render_template, request, url_for

import database
from config import Config
from serial_reader import ALLOWED_COMMANDS, SerialReader


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    serial_reader = SerialReader()
    app.config["SERIAL_READER"] = serial_reader
    app.config["DATABASE_ERROR"] = None

    try:
        database.initialize_database()
    except Exception as exc:
        app.config["DATABASE_ERROR"] = str(exc)

    if _should_start_serial_thread():
        serial_reader.start()

    register_template_helpers(app)
    register_routes(app)
    return app


def _should_start_serial_thread():
    if not Config.START_SERIAL_THREAD:
        return False

    # Avoid starting the reader twice when Flask's debug reloader is active.
    if Config.DEBUG:
        return os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    return True


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        return {
            "project_name": Config.PROJECT_NAME,
        }

    @app.template_filter("fmt")
    def format_number(value, digits=1):
        try:
            if value is None:
                return "N/A"
            return f"{float(value):.{int(digits)}f}"
        except Exception:
            return "N/A"

    @app.template_filter("yesno")
    def format_success(value):
        return "OK" if value else "Failed"


def register_routes(app):
    @app.route("/")
    def index():
        context = _load_dashboard_context(app)
        return render_template("index.html", **context)

    @app.route("/history")
    def history():
        context = _load_history_context(app)
        return render_template("history.html", **context)

    @app.route("/thresholds", methods=["POST"])
    def thresholds():
        try:
            humidity_threshold = float(request.form["humidity_threshold"])
            steam_threshold = int(request.form["steam_threshold"])

            if humidity_threshold < 0 or steam_threshold < 0:
                raise ValueError("Thresholds cannot be negative.")

            database.update_thresholds(humidity_threshold, steam_threshold)
            flash("Thresholds updated.", "success")
        except Exception as exc:
            flash(f"Could not update thresholds: {exc}", "error")

        return redirect(url_for("index"))

    @app.route("/control", methods=["POST"])
    def control():
        command = request.form.get("command", "").strip().upper()
        serial_reader = app.config["SERIAL_READER"]

        if command not in ALLOWED_COMMANDS:
            flash(f"Invalid command: {command}", "error")
            return redirect(url_for("index"))

        success, message = serial_reader.send_command(command, source="manual")
        flash(message, "success" if success else "error")
        return redirect(url_for("index"))


def _load_dashboard_context(flask_app):
    context = _empty_context(flask_app)

    try:
        context.update(
            latest=database.get_latest_reading(),
            thresholds=database.get_thresholds(),
            stats=database.get_statistics(),
            commands=database.get_recent_commands(Config.COMMAND_LIMIT),
        )
    except Exception as exc:
        context["database_error"] = str(exc)

    return context


def _load_history_context(flask_app):
    context = _empty_context(flask_app)

    try:
        context.update(
            readings=database.get_recent_readings(Config.HISTORY_LIMIT),
            stats=database.get_statistics(),
        )
    except Exception as exc:
        context["database_error"] = str(exc)

    return context


def _empty_context(flask_app):
    serial_reader = flask_app.config["SERIAL_READER"]
    return {
        "latest": None,
        "thresholds": {
            "humidity_threshold": Config.DEFAULT_HUMIDITY_THRESHOLD,
            "steam_threshold": Config.DEFAULT_STEAM_THRESHOLD,
        },
        "stats": {},
        "readings": [],
        "commands": [],
        "serial_status": serial_reader.status(),
        "database_error": flask_app.config.get("DATABASE_ERROR"),
    }


app = create_app()


if __name__ == "__main__":
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT, debug=Config.DEBUG)
