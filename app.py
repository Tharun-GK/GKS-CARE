import math
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import initialize_database
from repository import (
    get_patient,
    get_patient_history,
    get_patients,
    get_recent_observations,
    record_observation,
    seed_demo_patient,
    validate_patient_id,
)
from risk_logic import RiskThresholds, assess_vitals


REQUIRED_COLUMNS = ("time", "hr", "spo2", "temp")
DATA_DIRECTORY = Path(__file__).resolve().parent / "data"
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}\Z")
PASSWORD_HASH_PATTERN = re.compile(
    r"(?:scrypt:\d+:\d+:\d+|pbkdf2:sha256:\d+)\$[A-Za-z0-9]+\$[a-f0-9]+\Z"
)
AUTH_EXEMPT_ENDPOINTS = {"healthz", "login", "static"}


def _load_auth_users(configured_users):
    if configured_users is None:
        configured_users = os.environ.get("GKS_CARE_USERS")
    if isinstance(configured_users, str):
        try:
            configured_users = json.loads(configured_users)
        except json.JSONDecodeError as error:
            raise RuntimeError("GKS_CARE_USERS must be a JSON object of password hashes.") from error
    if not isinstance(configured_users, dict) or not configured_users:
        raise RuntimeError("Configure at least one account in GKS_CARE_USERS.")

    users = {}
    for username, password_hash in configured_users.items():
        if (
            not isinstance(username, str)
            or not USERNAME_PATTERN.fullmatch(username)
            or not isinstance(password_hash, str)
            or not PASSWORD_HASH_PATTERN.fullmatch(password_hash)
        ):
            raise RuntimeError(
                "GKS_CARE_USERS contains an invalid username or invalid password hash."
            )
        try:
            check_password_hash(password_hash, "configuration-validation")
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"GKS_CARE_USERS contains an invalid password hash for '{username}'."
            ) from error
        users[username] = password_hash
    return users


def _csrf_token():
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _csrf_is_valid():
    expected = session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token")
    if supplied is None:
        supplied = request.form.get("csrf_token")
    return (
        isinstance(expected, str)
        and isinstance(supplied, str)
        and secrets.compare_digest(expected, supplied)
    )


DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


class DatasetError(Exception):
    """Raised when the simulated patient dataset cannot be used."""


def load_dataset(dataset_path):
    try:
        dataset = pd.read_csv(dataset_path)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
        raise DatasetError("Unable to read the patient simulation dataset.") from error

    if dataset.empty:
        raise DatasetError("The patient simulation dataset is empty.")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataset.columns]
    if missing_columns:
        raise DatasetError(
            "The patient simulation dataset is missing required columns: "
            + ", ".join(missing_columns)
        )

    for column in REQUIRED_COLUMNS:
        try:
            dataset[column] = pd.to_numeric(dataset[column], errors="raise")
        except (TypeError, ValueError) as error:
            raise DatasetError(
                f"The patient simulation dataset contains invalid values in '{column}'."
            ) from error

        if not all(math.isfinite(float(value)) for value in dataset[column]):
            raise DatasetError(
                f"The patient simulation dataset contains non-finite values in '{column}'."
            )

    return dataset


def calculate_health_score(row, risk, thresholds):
    score = 100

    if row["hr"] > thresholds.score_heart_rate_high_above:
        score -= 25
    elif row["hr"] > thresholds.score_heart_rate_medium_above:
        score -= 10

    if row["spo2"] < thresholds.score_spo2_low_below:
        score -= 30
    elif row["spo2"] < thresholds.score_spo2_medium_below:
        score -= 15

    if row["temp"] > thresholds.score_temperature_high_above_f:
        score -= 15
    elif row["temp"] > thresholds.score_temperature_medium_above_f:
        score -= 8

    if risk == "Medium":
        score -= 10
    elif risk == "High":
        score -= 20

    return max(score, 0)


def generate_bp(risk):
    if risk == "Low":
        return "120/80"
    if risk == "Medium":
        return "140/90"
    return "165/105"


def create_app(
    dataset_path=None,
    database_path=None,
    risk_thresholds=None,
    auth_users=None,
    secret_key=None,
):
    app = Flask(__name__)
    resolved_secret_key = secret_key or os.environ.get("GKS_CARE_SECRET_KEY")
    if not isinstance(resolved_secret_key, str) or len(resolved_secret_key) < 32:
        raise RuntimeError("Set GKS_CARE_SECRET_KEY to a random value of at least 32 characters.")

    configured_users = _load_auth_users(auth_users)
    app.secret_key = resolved_secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("GKS_CARE_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    app.config["RISK_THRESHOLDS"] = RiskThresholds.from_mapping(
        risk_thresholds
    ).__dict__
    default_dataset_paths = {
        "P001": DATA_DIRECTORY / "critical.csv",
        "P002": DATA_DIRECTORY / "moderate.csv",
        "P003": DATA_DIRECTORY / "stable.csv",
    }
    if dataset_path:
        default_dataset_paths["P001"] = Path(dataset_path)
    resolved_database_path = (
        Path(database_path)
        if database_path
        else Path(
            os.environ.get(
                "GKS_CARE_DATABASE",
                Path(app.instance_path) / "gks-care.sqlite3",
            )
        )
    )
    initialize_database(resolved_database_path)
    seed_demo_patient(resolved_database_path)
    app.config["DATABASE_PATH"] = str(resolved_database_path)

    patient_datasets = {}
    patient_states = {}
    for patient_id, path in default_dataset_paths.items():
        try:
            patient_datasets[patient_id] = {"dataset": load_dataset(path), "error": None}
        except DatasetError as error:
            app.logger.error(
                "Patient simulation data for %s is unavailable: %s",
                patient_id,
                error,
            )
            patient_datasets[patient_id] = {"dataset": None, "error": error}
        patient_states[patient_id] = {"index": 0, "previous_row": None}

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=()",
        )
        if request.endpoint not in {"static", "healthz"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def protect_routes():
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not _csrf_is_valid():
            return jsonify({"error": "A valid CSRF token is required."}), 400

        if request.endpoint in AUTH_EXEMPT_ENDPOINTS:
            return None
        if "username" in session:
            return None
        if request.path.startswith("/patient") or request.path == "/patients":
            return jsonify({"error": "Authentication is required."}), 401
        return redirect(url_for("login"))

    @app.route("/healthz")
    def healthz():
        try:
            with closing(sqlite3.connect(resolved_database_path)) as connection:
                connection.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            app.logger.exception("Application health check failed.")
            return jsonify({"status": "unavailable"}), 503
        return jsonify({"status": "ok"})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html", csrf_token=_csrf_token(), error=None)

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        password_hash = configured_users.get(username, DUMMY_PASSWORD_HASH)
        password_matches = (
            isinstance(password, str)
            and check_password_hash(password_hash, password)
        )
        if username not in configured_users or not password_matches:
            return (
                render_template(
                    "login.html",
                    csrf_token=_csrf_token(),
                    error="Username or password is incorrect.",
                ),
                401,
            )

        session.clear()
        session["username"] = username
        session.permanent = True
        _csrf_token()
        return redirect(url_for("dashboard"))

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    def dashboard():
        return render_template(
            "dashboard.html",
            csrf_token=_csrf_token(),
            username=session["username"],
        )

    @app.route("/patients")
    def patients():
        return jsonify({"patients": get_patients(resolved_database_path)})

    def patient_data(patient_id, advance):
        try:
            patient_id = validate_patient_id(patient_id)
            patient = get_patient(resolved_database_path, patient_id)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        if patient is None:
            return jsonify({"error": "Patient was not found."}), 404

        patient_data = patient_datasets.get(patient_id)
        if patient_data is None:
            return jsonify({"error": "Patient simulation data is unavailable."}), 503

        patient_dataset = patient_data["dataset"]
        if patient_data["error"] is not None or patient_dataset is None:
            return jsonify({"error": "Patient simulation data is currently unavailable."}), 503

        patient_state = patient_states[patient_id]
        if patient_state["index"] >= len(patient_dataset):
            patient_state["index"] = 0
            patient_state["previous_row"] = None

        row = patient_dataset.iloc[patient_state["index"]]
        thresholds = RiskThresholds.from_mapping(app.config["RISK_THRESHOLDS"])
        risk_assessment = assess_vitals(
            row,
            patient_state["previous_row"],
            thresholds,
        )
        if risk_assessment.risk == "Unavailable":
            return jsonify({
                "error": risk_assessment.next_step,
                "risk_assessment": risk_assessment.to_dict(),
            }), 422

        risk = risk_assessment.risk
        reasons = risk_assessment.reasons
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if advance:
            observation = record_observation(
                resolved_database_path,
                patient_id=patient_id,
                measured_at=datetime.now(timezone.utc),
                heart_rate_bpm=row["hr"],
                spo2_percent=row["spo2"],
                temperature_value=row["temp"],
                temperature_unit="F",
                source="synthetic_csv",
                assessment=risk_assessment.to_dict(),
                actor=session["username"],
            )
            observed_at = observation["measured_at"]
        recent_observations = get_recent_observations(resolved_database_path, patient_id)

        data = {
            "patient_id": patient["patient_id"],
            "age": patient["age"],
            "gender": patient["gender"],
            "data_source": patient["data_source"],
            "last_updated": int(row["time"]),
            "observed_at": observed_at,
            "hr": int(row["hr"]),
            "spo2": int(row["spo2"]),
            "temp": float(row["temp"]),
            "temperature_unit": "F",
            "bp": generate_bp(risk),
            "risk": risk,
            "status": risk_assessment.status,
            "health_score": calculate_health_score(row, risk, thresholds),
            "reasons": reasons,
            "recommendation": risk_assessment.next_step,
            "risk_assessment": risk_assessment.to_dict(),
            "medical_history": get_patient_history(resolved_database_path, patient_id),
            "observations": [
                {
                    "id": item["id"],
                    "measured_at": item["measured_at"],
                    "hr": item["heart_rate_bpm"],
                    "hr_unit": "bpm",
                    "spo2": item["spo2_percent"],
                    "spo2_unit": "%",
                    "temp": item["temperature_value"],
                    "temperature_unit": item["temperature_unit"],
                    "source": item["source"],
                }
                for item in recent_observations
            ],
        }

        if advance:
            patient_state["previous_row"] = row
            patient_state["index"] += 1

        return jsonify(data)

    @app.route("/patient")
    def patient():
        return patient_data(request.args.get("patient_id", "P001"), advance=False)

    @app.route("/patient/advance", methods=["POST"])
    def advance_patient():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "A JSON object is required."}), 400
        patient_id = payload.get("patient_id", "P001")
        return patient_data(patient_id, advance=True)

    return app


app = create_app()


if __name__ == "__main__":
    from waitress import serve

    serve(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
    )
