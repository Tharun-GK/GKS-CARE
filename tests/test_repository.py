import tempfile
import unittest
from pathlib import Path

from database import (
    backup_database,
    initialize_database,
    restore_database,
    transaction,
)
from repository import (
    get_audit_events,
    get_patient,
    get_patient_history,
    get_patients,
    get_recent_observations,
    record_observation,
    seed_demo_patient,
    validate_observation,
    validate_patient_id,
)


def observation_values(**overrides):
    values = {
        "patient_id": "P001",
        "measured_at": "2026-01-02T03:04:05+05:30",
        "heart_rate_bpm": 80,
        "spo2_percent": 98,
        "temperature_value": 98.4,
        "temperature_unit": "F",
        "source": "synthetic_csv",
    }
    values.update(overrides)
    return values


class PatientRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.database_path = Path(self.temp_directory.name) / "nested" / "test.sqlite3"
        initialize_database(self.database_path)
        seed_demo_patient(self.database_path)

    def test_database_initializes_schema_version_and_synthetic_patient_records(self):
        patient = get_patient(self.database_path, "P001")
        history = get_patient_history(self.database_path, "P001")
        with transaction(self.database_path) as connection:
            version = connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchone()["version"]

        self.assertEqual(version, 1)
        self.assertEqual(patient["data_source"], "synthetic_demo")
        self.assertEqual(len(history), 6)
        self.assertTrue(all(item["source"] == "synthetic_demo" for item in history))
        self.assertEqual(
            [patient["patient_id"] for patient in get_patients(self.database_path)],
            ["P001", "P002", "P003"],
        )

    def test_demo_seeding_is_idempotent_and_keeps_patient_records_separate(self):
        with transaction(self.database_path) as connection:
            connection.execute(
                """
                UPDATE patient_history
                SET value = ?
                WHERE patient_id = ? AND record_type = ?
                """,
                ("Existing demo value", "P001", "allergies"),
            )

        seed_demo_patient(self.database_path)

        p001_history = {
            item["record_type"]: item["value"]
            for item in get_patient_history(self.database_path, "P001")
        }
        p002_history = {
            item["record_type"]: item["value"]
            for item in get_patient_history(self.database_path, "P002")
        }
        self.assertEqual(p001_history["allergies"], "Existing demo value")
        self.assertEqual(p002_history["allergies"], "None recorded in demo")

    def test_observation_validation_normalizes_timezone_and_units(self):
        observation = validate_observation(**observation_values())

        self.assertEqual(
            observation["measured_at"],
            "2026-01-01T21:34:05.000000Z",
        )
        self.assertEqual(observation["temperature_unit"], "F")
        self.assertEqual(observation["source"], "synthetic_csv")

    def test_invalid_observation_values_are_rejected(self):
        invalid_cases = (
            {"patient_id": "invalid id"},
            {"heart_rate_bpm": 0},
            {"heart_rate_bpm": float("nan")},
            {"spo2_percent": -1},
            {"spo2_percent": 101},
            {"temperature_value": float("inf")},
            {"temperature_unit": "K"},
            {"source": "  "},
            {"measured_at": "2026-01-02T03:04:05"},
            {"measured_at": "not-a-timestamp"},
        )

        for invalid_values in invalid_cases:
            with self.subTest(invalid_values=invalid_values):
                with self.assertRaises(ValueError):
                    validate_observation(**observation_values(**invalid_values))

    def test_patient_identifier_validation(self):
        self.assertEqual(validate_patient_id("demo_patient-1"), "demo_patient-1")
        with self.assertRaises(ValueError):
            validate_patient_id("P/001")
        with self.assertRaises(ValueError):
            validate_patient_id(123)

    def test_observations_and_audit_events_are_saved_and_retrieved(self):
        values = observation_values()
        observation = record_observation(
            self.database_path,
            **values,
            assessment={"risk": "Medium", "reasons": ["Oxygen dropping"]},
        )

        stored = get_recent_observations(self.database_path, "P001")
        events = get_audit_events(self.database_path, "P001")

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["id"], observation["id"])
        self.assertEqual(stored[0]["heart_rate_bpm"], 80)
        self.assertEqual(stored[0]["spo2_percent"], 98)
        self.assertEqual(stored[0]["temperature_unit"], "F")
        self.assertEqual(events[-1]["event_type"], "observation_recorded")
        self.assertEqual(events[-1]["details"]["risk"], "Medium")
        self.assertEqual(events[-1]["details"]["reasons"], ["Oxygen dropping"])
        self.assertNotIn("risk_assessment", events[-1]["details"])

    def test_recent_observations_are_limited_and_chronological(self):
        for day in (3, 1, 2):
            record_observation(
                self.database_path,
                **observation_values(
                    measured_at=f"2026-01-0{day}T03:04:05Z",
                    heart_rate_bpm=70 + day,
                ),
                assessment={"risk": "Low", "reasons": []},
            )

        recent = get_recent_observations(self.database_path, "P001", limit=2)

        self.assertEqual([item["heart_rate_bpm"] for item in recent], [72, 73])
        with self.assertRaises(ValueError):
            get_recent_observations(self.database_path, "P001", limit=0)

    def test_unknown_patients_cannot_receive_observations(self):
        with self.assertRaises(LookupError):
            record_observation(
                self.database_path,
                **observation_values(patient_id="P999"),
                assessment={"risk": "Low", "reasons": []},
            )

    def test_backup_and_restore_preserve_schema_observations_and_audit(self):
        record_observation(
            self.database_path,
            **observation_values(),
            assessment={"risk": "Low", "reasons": []},
            actor="backup-test",
        )
        backup_path = self.database_path.parent / "backup.sqlite3"
        restored_path = self.database_path.parent / "restored.sqlite3"

        self.assertEqual(backup_database(self.database_path, backup_path), backup_path)
        self.assertEqual(restore_database(backup_path, restored_path), restored_path)

        with transaction(restored_path) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            version = connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchone()["version"]
            audit = connection.execute(
                "SELECT details_json FROM audit_events "
                "WHERE event_type = 'observation_recorded'"
            ).fetchone()

        self.assertEqual(integrity, "ok")
        self.assertEqual(version, 1)
        self.assertEqual(len(get_recent_observations(restored_path, "P001")), 1)
        self.assertIn("backup-test", audit["details_json"])
        self.assertEqual(len(get_audit_events(restored_path, "P001")), 2)

    def test_backup_and_restore_refuse_to_overwrite_existing_files(self):
        backup_path = self.database_path.parent / "backup.sqlite3"
        restored_path = self.database_path.parent / "restored.sqlite3"
        backup_database(self.database_path, backup_path)
        with self.assertRaises(FileExistsError):
            backup_database(self.database_path, backup_path)
        with self.assertRaises(FileExistsError):
            restore_database(backup_path, self.database_path)
        with self.assertRaises(ValueError):
            backup_database(self.database_path, self.database_path)
        with self.assertRaises(FileNotFoundError):
            backup_database(self.database_path.parent / "missing.sqlite3", restored_path)


if __name__ == "__main__":
    unittest.main()
