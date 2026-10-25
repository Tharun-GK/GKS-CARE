import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request

from database import initialize_database
from repository import (
    get_patient,
    get_patient_history,
    get_patients,
    get_recent_observations,
    record_observation,
    seed_demo_patient,
)
from risk_logic import RiskThresholds, assess_vitals


REQUIRED_COLUMNS = ("time", "hr", "spo2", "temp")
DATA_DIRECTORY = Path(__file__).resolve().parent / "data"


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


def create_app(dataset_path=None, database_path=None, risk_thresholds=None):
    app = Flask(__name__)
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
        else Path(app.instance_path) / "gks-care.sqlite3"
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

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/patients")
    def patients():
        return jsonify({"patients": get_patients(resolved_database_path)})

    @app.route("/patient")
    def patient():
        patient_id = request.args.get("patient_id", "P001")
        try:
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
        measured_at = datetime.now(timezone.utc)
        observation = record_observation(
            resolved_database_path,
            patient_id=patient_id,
            measured_at=measured_at,
            heart_rate_bpm=row["hr"],
            spo2_percent=row["spo2"],
            temperature_value=row["temp"],
            temperature_unit="F",
            source="synthetic_csv",
            assessment=risk_assessment.to_dict(),
        )
        recent_observations = get_recent_observations(resolved_database_path, patient_id)

        data = {
            "patient_id": patient["patient_id"],
            "age": patient["age"],
            "gender": patient["gender"],
            "data_source": patient["data_source"],
            "last_updated": int(row["time"]),
            "observed_at": observation["measured_at"],
            "hr": int(row["hr"]),
            "spo2": int(row["spo2"]),
            "temp": float(row["temp"]),
            "temperature_unit": observation["temperature_unit"],
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

        patient_state["previous_row"] = row
        patient_state["index"] += 1

        return jsonify(data)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
