import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template

from database import initialize_database
from repository import (
    get_patient,
    get_patient_history,
    get_recent_observations,
    record_observation,
    seed_demo_patient,
)
from risk_logic import calculate_risk


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


def calculate_health_score(row, risk):
    score = 100

    if row["hr"] > 120:
        score -= 25
    elif row["hr"] > 100:
        score -= 10

    if row["spo2"] < 90:
        score -= 30
    elif row["spo2"] < 95:
        score -= 15

    if row["temp"] > 101:
        score -= 15
    elif row["temp"] > 99.5:
        score -= 8

    if risk == "Medium":
        score -= 10
    elif risk == "High":
        score -= 20

    return max(score, 0)


def get_patient_status(risk):
    if risk == "Low":
        return "Stable"
    if risk == "Medium":
        return "Under Observation"
    return "Critical Condition"


def generate_bp(risk):
    if risk == "Low":
        return "120/80"
    if risk == "Medium":
        return "140/90"
    return "165/105"


def create_app(dataset_path=None, database_path=None):
    app = Flask(__name__)
    resolved_dataset_path = Path(dataset_path) if dataset_path else DATA_DIRECTORY / "critical.csv"
    resolved_database_path = (
        Path(database_path)
        if database_path
        else Path(app.instance_path) / "gks-care.sqlite3"
    )
    initialize_database(resolved_database_path)
    seed_demo_patient(resolved_database_path)
    app.config["DATABASE_PATH"] = str(resolved_database_path)

    try:
        patient_dataset = load_dataset(resolved_dataset_path)
        dataset_error = None
    except DatasetError as error:
        app.logger.error("Patient simulation data is unavailable: %s", error)
        patient_dataset = None
        dataset_error = error

    patient_state = {"index": 0, "previous_row": None}

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/patient")
    def patient():
        if dataset_error is not None or patient_dataset is None:
            return jsonify({"error": "Patient simulation data is currently unavailable."}), 503

        if patient_state["index"] >= len(patient_dataset):
            patient_state["index"] = 0
            patient_state["previous_row"] = None

        row = patient_dataset.iloc[patient_state["index"]]
        risk, reasons = calculate_risk(row, patient_state["previous_row"])

        recommendation = {
            "Low": "Demo rules did not flag a threshold in this sample. This does not rule out illness.",
            "Medium": "Demo rules detected a changing pattern. Review the measurements with a qualified clinician.",
            "High": "Demo rules detected a concerning pattern. This is not a diagnosis; consult a qualified clinician.",
        }
        patient_id = "P001"
        measured_at = datetime.now(timezone.utc)
        patient = get_patient(resolved_database_path, patient_id)
        observation = record_observation(
            resolved_database_path,
            patient_id=patient_id,
            measured_at=measured_at,
            heart_rate_bpm=row["hr"],
            spo2_percent=row["spo2"],
            temperature_value=row["temp"],
            temperature_unit="F",
            source="synthetic_csv",
            assessment={"risk": risk, "reasons": reasons},
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
            "status": get_patient_status(risk),
            "health_score": calculate_health_score(row, risk),
            "reasons": reasons,
            "recommendation": recommendation[risk],
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
