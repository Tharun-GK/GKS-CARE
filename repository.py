from datetime import datetime, timezone
import json
import math
import re

from database import transaction


PATIENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
TEMPERATURE_UNITS = {"F", "C"}

DEMO_HISTORY = (
    ("blood_group", "O+"),
    ("allergies", "Penicillin"),
    ("diabetes", "Yes"),
    ("hypertension", "Yes"),
    ("surgery", "Angioplasty (2024)"),
    ("medicine", "Aspirin, Metformin"),
)


def validate_patient_id(patient_id):
    if not isinstance(patient_id, str) or not PATIENT_ID_PATTERN.fullmatch(patient_id):
        raise ValueError("Patient identifier has an invalid format.")
    return patient_id


def normalize_timestamp(value):
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Measurement timestamp must be a valid ISO 8601 value.") from error
    else:
        raise ValueError("Measurement timestamp must be a datetime or ISO 8601 string.")

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Measurement timestamp must include a timezone.")

    return (
        timestamp.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _validate_number(name, value):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number.") from error

    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def validate_observation(
    patient_id,
    measured_at,
    heart_rate_bpm,
    spo2_percent,
    temperature_value,
    temperature_unit,
    source,
):
    patient_id = validate_patient_id(patient_id)
    measured_at = normalize_timestamp(measured_at)
    heart_rate_bpm = _validate_number("Heart rate", heart_rate_bpm)
    spo2_percent = _validate_number("SpO2", spo2_percent)
    temperature_value = _validate_number("Temperature", temperature_value)

    if heart_rate_bpm <= 0:
        raise ValueError("Heart rate must be greater than zero.")
    if not 0 <= spo2_percent <= 100:
        raise ValueError("SpO2 must be between 0 and 100 percent.")
    if not isinstance(temperature_unit, str) or temperature_unit not in TEMPERATURE_UNITS:
        raise ValueError("Temperature unit must be 'F' or 'C'.")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Observation source must be a non-empty string.")

    return {
        "patient_id": patient_id,
        "measured_at": measured_at,
        "heart_rate_bpm": heart_rate_bpm,
        "spo2_percent": spo2_percent,
        "temperature_value": temperature_value,
        "temperature_unit": temperature_unit,
        "source": source.strip(),
    }


def _insert_audit_event(connection, patient_id, event_type, occurred_at, details):
    connection.execute(
        """
        INSERT INTO audit_events (patient_id, event_type, occurred_at, details_json)
        VALUES (?, ?, ?, ?)
        """,
        (
            patient_id,
            event_type,
            occurred_at,
            json.dumps(details, allow_nan=False, sort_keys=True),
        ),
    )


def seed_demo_patient(database_path):
    created_at = normalize_timestamp(datetime.now(timezone.utc))
    with transaction(database_path) as connection:
        inserted = connection.execute(
            """
            INSERT OR IGNORE INTO patients
                (patient_id, age, gender, data_source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("P001", 45, "Male", "synthetic_demo", created_at),
        ).rowcount

        for record_type, value in DEMO_HISTORY:
            connection.execute(
                """
                INSERT OR IGNORE INTO patient_history
                    (patient_id, record_type, value, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("P001", record_type, value, "synthetic_demo", created_at),
            )

        if inserted:
            _insert_audit_event(
                connection,
                "P001",
                "synthetic_patient_seeded",
                created_at,
                {"source": "synthetic_demo"},
            )


def get_patient(database_path, patient_id):
    patient_id = validate_patient_id(patient_id)
    with transaction(database_path) as connection:
        patient = connection.execute(
            """
            SELECT patient_id, age, gender, data_source, created_at
            FROM patients
            WHERE patient_id = ?
            """,
            (patient_id,),
        ).fetchone()
    return dict(patient) if patient else None


def get_patient_history(database_path, patient_id):
    patient_id = validate_patient_id(patient_id)
    with transaction(database_path) as connection:
        records = connection.execute(
            """
            SELECT record_type, value, source, updated_at
            FROM patient_history
            WHERE patient_id = ?
            ORDER BY record_type
            """,
            (patient_id,),
        ).fetchall()
    return [dict(record) for record in records]


def record_observation(
    database_path,
    patient_id,
    measured_at,
    heart_rate_bpm,
    spo2_percent,
    temperature_value,
    temperature_unit,
    source,
    assessment,
):
    observation = validate_observation(
        patient_id,
        measured_at,
        heart_rate_bpm,
        spo2_percent,
        temperature_value,
        temperature_unit,
        source,
    )
    occurred_at = normalize_timestamp(datetime.now(timezone.utc))

    with transaction(database_path) as connection:
        patient_exists = connection.execute(
            "SELECT 1 FROM patients WHERE patient_id = ?",
            (observation["patient_id"],),
        ).fetchone()
        if not patient_exists:
            raise LookupError("Patient identifier does not match a stored patient.")

        result = connection.execute(
            """
            INSERT INTO observations (
                patient_id,
                measured_at,
                heart_rate_bpm,
                spo2_percent,
                temperature_value,
                temperature_unit,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation["patient_id"],
                observation["measured_at"],
                observation["heart_rate_bpm"],
                observation["spo2_percent"],
                observation["temperature_value"],
                observation["temperature_unit"],
                observation["source"],
            ),
        )
        observation["id"] = result.lastrowid

        _insert_audit_event(
            connection,
            observation["patient_id"],
            "observation_recorded",
            occurred_at,
            {
                "observation_id": observation["id"],
                "risk": assessment["risk"],
                "reasons": assessment["reasons"],
                "source": observation["source"],
            },
        )

    return observation


def get_recent_observations(database_path, patient_id, limit=15):
    patient_id = validate_patient_id(patient_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Observation limit must be an integer between 1 and 100.")

    with transaction(database_path) as connection:
        observations = connection.execute(
            """
            SELECT
                id,
                measured_at,
                heart_rate_bpm,
                spo2_percent,
                temperature_value,
                temperature_unit,
                source
            FROM observations
            WHERE patient_id = ?
            ORDER BY measured_at DESC, id DESC
            LIMIT ?
            """,
            (patient_id, limit),
        ).fetchall()
    return [dict(observation) for observation in reversed(observations)]


def get_audit_events(database_path, patient_id, limit=100):
    patient_id = validate_patient_id(patient_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("Audit event limit must be an integer between 1 and 1000.")

    with transaction(database_path) as connection:
        events = connection.execute(
            """
            SELECT event_type, occurred_at, details_json
            FROM audit_events
            WHERE patient_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (patient_id, limit),
        ).fetchall()

    return [
        {
            "event_type": event["event_type"],
            "occurred_at": event["occurred_at"],
            "details": json.loads(event["details_json"]),
        }
        for event in reversed(events)
    ]
