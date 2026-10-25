import tempfile
import unittest
from pathlib import Path

from app import create_app
from repository import get_audit_events, get_recent_observations


VALID_CSV = """time,hr,spo2,bp,temp
1,80,98,120,98.4
2,105,92,110,99.5
"""


class PatientApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.dataset_path = Path(self.temp_directory.name) / "patient.csv"
        self.dataset_path.write_text(VALID_CSV, encoding="utf-8")

        self.database_path = Path(self.temp_directory.name) / "test.sqlite3"
        app = create_app(self.dataset_path, self.database_path)
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_dashboard_renders_existing_sections_and_demo_notice(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        for element_id in (
            "hr",
            "bp",
            "spo2",
            "temp",
            "max_hr",
            "min_spo2",
            "avg_temp",
            "monitor_time",
            "activityLog",
            "alertBanner",
            "hrChart",
            "spo2Chart",
            "tempChart",
            "dashboardError",
            "patientSelector",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', page)

        self.assertIn("Synthetic measurements", page)
        self.assertIn("not a trained or clinically validated AI model", page)
        self.assertNotIn('id="emergencyBanner"', page)

    def test_patient_endpoint_returns_expected_vitals_and_assessment(self):
        response = self.client.get("/patient")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            set(data),
            {
                "patient_id",
                "age",
                "gender",
                "data_source",
                "last_updated",
                "observed_at",
                "hr",
                "spo2",
                "temp",
                "temperature_unit",
                "bp",
                "risk",
                "status",
                "health_score",
                "reasons",
                "recommendation",
                "risk_assessment",
                "medical_history",
                "observations",
            },
        )
        self.assertEqual(data["patient_id"], "P001")
        self.assertEqual(data["data_source"], "synthetic_demo")
        self.assertEqual(data["temperature_unit"], "F")
        self.assertEqual(data["risk"], "Low")
        self.assertEqual(data["status"], "No Demo Threshold Flagged")
        self.assertIsInstance(data["reasons"], list)
        self.assertIsInstance(data["health_score"], int)
        self.assertEqual(data["risk_assessment"]["method"], "deterministic_demo_rules")
        self.assertFalse(data["risk_assessment"]["clinically_validated"])
        self.assertEqual(data["risk_assessment"]["data_quality"]["status"], "complete")
        self.assertEqual(len(data["observations"]), 1)
        self.assertEqual(data["observations"][0]["hr"], data["hr"])
        self.assertEqual(data["observations"][0]["temperature_unit"], "F")
        audit_event = get_audit_events(self.database_path, "P001")[-1]
        self.assertEqual(
            audit_event["details"]["risk_assessment"]["method"],
            "deterministic_demo_rules",
        )
        self.assertEqual(len(data["medical_history"]), 6)
        self.assertNotIn("confidence", data)

    def test_patient_list_returns_all_seeded_synthetic_profiles(self):
        response = self.client.get("/patients")

        self.assertEqual(response.status_code, 200)
        patients = response.get_json()["patients"]
        self.assertEqual(
            [patient["patient_id"] for patient in patients],
            ["P001", "P002", "P003"],
        )
        self.assertTrue(
            all(patient["data_source"] == "synthetic_demo" for patient in patients)
        )

    def test_patient_selection_isolated_for_datasets_history_and_observations(self):
        p002 = self.client.get("/patient?patient_id=P002").get_json()
        p001 = self.client.get("/patient?patient_id=P001").get_json()
        p003 = self.client.get("/patient?patient_id=P003").get_json()
        p002_again = self.client.get("/patient?patient_id=P002").get_json()

        self.assertEqual((p001["hr"], p002["hr"], p003["hr"]), (80, 85, 78))
        self.assertEqual(p002_again["hr"], 90)
        self.assertEqual(p001["age"], 45)
        self.assertEqual(p002["age"], 37)
        self.assertEqual(p003["age"], 62)
        p001_history = {
            item["record_type"]: item["value"] for item in p001["medical_history"]
        }
        self.assertEqual(p001_history["diabetes"], "Yes")
        self.assertNotEqual(
            p001["medical_history"],
            p002["medical_history"],
        )
        self.assertEqual([item["hr"] for item in p001["observations"]], [80])
        self.assertEqual([item["hr"] for item in p002_again["observations"]], [85, 90])
        self.assertEqual([item["hr"] for item in p003["observations"]], [78])

    def test_unknown_and_malformed_patient_identifiers_return_errors(self):
        unknown = self.client.get("/patient?patient_id=P999")
        malformed = self.client.get("/patient?patient_id=bad%20id")

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.get_json(), {"error": "Patient was not found."})
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(
            malformed.get_json(),
            {"error": "Patient identifier has an invalid format."},
        )

    def test_patient_endpoint_advances_and_restarts_simulation(self):
        first = self.client.get("/patient").get_json()
        second = self.client.get("/patient").get_json()
        third = self.client.get("/patient").get_json()

        self.assertEqual((first["hr"], second["hr"], third["hr"]), (80, 105, 80))
        self.assertEqual(second["risk"], "Medium")
        self.assertEqual(second["status"], "Demo Review Suggested")
        self.assertEqual(len(third["observations"]), 3)

    def test_invalid_vitals_return_unavailable_assessment_without_persisting(self):
        invalid_path = Path(self.temp_directory.name) / "invalid_range.csv"
        invalid_path.write_text(
            "time,hr,spo2,temp\n1,80,101,98.4\n",
            encoding="utf-8",
        )
        app = create_app(invalid_path, self.database_path)
        app.config["TESTING"] = True

        response = app.test_client().get("/patient")
        data = response.get_json()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(data["risk_assessment"]["risk"], "Unavailable")
        self.assertEqual(
            data["risk_assessment"]["data_quality"]["status"],
            "incomplete_or_invalid",
        )
        self.assertEqual(
            get_recent_observations(self.database_path, "P001"),
            [],
        )

    def test_risk_threshold_configuration_is_applied_to_assessment_and_health_score(self):
        app = create_app(
            self.dataset_path,
            self.database_path,
            risk_thresholds={"spo2_medium_below": 99},
        )
        app.config["TESTING"] = True

        data = app.test_client().get("/patient").get_json()

        self.assertEqual(data["risk"], "Medium")
        self.assertEqual(data["status"], "Demo Review Suggested")
        self.assertEqual(data["health_score"], 90)
        self.assertEqual(
            data["risk_assessment"]["factors"][0]["code"],
            "spo2_demo_medium",
        )

    def test_invalid_risk_threshold_configuration_fails_at_startup(self):
        with self.assertRaisesRegex(ValueError, "below its medium threshold"):
            create_app(
                self.dataset_path,
                self.database_path,
                risk_thresholds={
                    "spo2_high_below": 96,
                    "spo2_medium_below": 95,
                },
            )

    def test_observations_persist_across_app_restarts(self):
        self.client.get("/patient")

        restarted_app = create_app(self.dataset_path, self.database_path)
        restarted_app.config["TESTING"] = True
        response = restarted_app.test_client().get("/patient")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["observations"]), 2)
        self.assertEqual([item["hr"] for item in data["observations"]], [80, 80])

    def test_missing_dataset_returns_controlled_service_error(self):
        missing_path = Path(self.temp_directory.name) / "missing.csv"
        app = create_app(missing_path, self.database_path)
        app.config["TESTING"] = True

        response = app.test_client().get("/patient")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"error": "Patient simulation data is currently unavailable."},
        )

    def test_malformed_datasets_return_controlled_service_error(self):
        invalid_datasets = {
            "empty": "",
            "missing_columns": "time,hr\n1,80\n",
            "nonnumeric": "time,hr,spo2,temp\n1,invalid,98,98.4\n",
            "non_finite": "time,hr,spo2,temp\n1,80,inf,98.4\n",
        }

        for name, contents in invalid_datasets.items():
            with self.subTest(dataset=name):
                path = Path(self.temp_directory.name) / f"{name}.csv"
                path.write_text(contents, encoding="utf-8")
                app = create_app(path, self.database_path)
                app.config["TESTING"] = True

                response = app.test_client().get("/patient")

                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.get_json(),
                    {"error": "Patient simulation data is currently unavailable."},
                )


if __name__ == "__main__":
    unittest.main()
