import tempfile
import unittest
from pathlib import Path

from app import create_app


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

        app = create_app(self.dataset_path)
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
                "last_updated",
                "hr",
                "spo2",
                "temp",
                "bp",
                "risk",
                "status",
                "health_score",
                "reasons",
                "recommendation",
            },
        )
        self.assertEqual(data["patient_id"], "P001")
        self.assertEqual(data["risk"], "Low")
        self.assertEqual(data["status"], "Stable")
        self.assertIsInstance(data["reasons"], list)
        self.assertIsInstance(data["health_score"], int)
        self.assertNotIn("confidence", data)

    def test_patient_endpoint_advances_and_restarts_simulation(self):
        first = self.client.get("/patient").get_json()
        second = self.client.get("/patient").get_json()
        third = self.client.get("/patient").get_json()

        self.assertEqual((first["hr"], second["hr"], third["hr"]), (80, 105, 80))
        self.assertEqual(second["risk"], "Medium")

    def test_missing_dataset_returns_controlled_service_error(self):
        missing_path = Path(self.temp_directory.name) / "missing.csv"
        app = create_app(missing_path)
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
                app = create_app(path)
                app.config["TESTING"] = True

                response = app.test_client().get("/patient")

                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.get_json(),
                    {"error": "Patient simulation data is currently unavailable."},
                )


if __name__ == "__main__":
    unittest.main()
