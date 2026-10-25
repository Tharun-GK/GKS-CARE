import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

os.environ["GKS_CARE_SECRET_KEY"] = "test-secret-key-with-at-least-thirty-two-characters"
os.environ["GKS_CARE_USERS"] = json.dumps(
    {"test-user": generate_password_hash("test-password")}
)

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
        self.csrf_token = self._login()

    def _login(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        csrf_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            response.get_data(as_text=True),
        ).group(1)
        response = self.client.post(
            "/login",
            data={
                "username": "test-user",
                "password": "test-password",
                "csrf_token": csrf_token,
            },
        )
        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get("/")
        self.assertEqual(dashboard.status_code, 200)
        return re.search(
            r'<meta name="csrf-token" content="([^"]+)"',
            dashboard.get_data(as_text=True),
        ).group(1)

    def advance_patient(self, patient_id="P001"):
        return self.client.post(
            "/patient/advance",
            json={"patient_id": patient_id},
            headers={"X-CSRF-Token": self.csrf_token},
        )

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
        self.assertIn('name="csrf-token"', page)
        self.assertIn("test-user", page)
        self.assertIn("chart.js@4.4.7", page)
        self.assertIn(
            "integrity=\"sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC\"",
            page,
        )
        self.assertNotIn('id="emergencyBanner"', page)

    def test_patient_endpoint_returns_expected_vitals_and_assessment(self):
        response = self.client.post(
            "/patient/advance",
            json={"patient_id": "P001"},
            headers={"X-CSRF-Token": self.csrf_token},
        )

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
        self.assertEqual(audit_event["details"]["actor"], "test-user")
        self.assertEqual(len(data["medical_history"]), 6)
        self.assertNotIn("confidence", data)

    def test_patient_get_is_read_only_and_preserves_the_response_contract(self):
        first = self.client.get("/patient")
        second = self.client.get("/patient")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.get_json()["hr"], second.get_json()["hr"])
        self.assertEqual(first.get_json()["risk"], second.get_json()["risk"])
        self.assertEqual(first.get_json()["observations"], [])
        self.assertEqual(
            get_audit_events(self.database_path, "P001")[-1]["event_type"],
            "synthetic_patient_seeded",
        )

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
        p002 = self.advance_patient("P002").get_json()
        p001 = self.advance_patient("P001").get_json()
        p003 = self.advance_patient("P003").get_json()
        p002_again = self.advance_patient("P002").get_json()

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
        first = self.advance_patient().get_json()
        second = self.advance_patient().get_json()
        third = self.advance_patient().get_json()

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
        invalid_client = app.test_client()
        csrf_token = self._login_for(invalid_client)

        response = invalid_client.post(
            "/patient/advance",
            json={"patient_id": "P001"},
            headers={"X-CSRF-Token": csrf_token},
        )
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

        test_client = app.test_client()
        csrf_token = self._login_for(test_client)
        response = test_client.post(
            "/patient/advance",
            json={"patient_id": "P001"},
            headers={"X-CSRF-Token": csrf_token},
        )
        data = response.get_json()

        self.assertEqual(data["risk"], "Medium")
        self.assertEqual(data["status"], "Demo Review Suggested")
        self.assertEqual(data["health_score"], 90)
        self.assertEqual(
            data["risk_assessment"]["factors"][0]["code"],
            "spo2_demo_medium",
        )

    def _login_for(self, test_client):
        response = test_client.get("/login")
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            response.get_data(as_text=True),
        ).group(1)
        test_client.post(
            "/login",
            data={
                "username": "test-user",
                "password": "test-password",
                "csrf_token": token,
            },
        )
        dashboard = test_client.get("/")
        return re.search(
            r'<meta name="csrf-token" content="([^"]+)"',
            dashboard.get_data(as_text=True),
        ).group(1)

    def test_protected_routes_require_login_and_posts_require_csrf(self):
        app = create_app(self.dataset_path, self.database_path)
        app.config["TESTING"] = True
        anonymous_client = app.test_client()

        self.assertEqual(anonymous_client.get("/").status_code, 302)
        self.assertEqual(anonymous_client.get("/patients").status_code, 401)
        self.assertEqual(anonymous_client.get("/patient").status_code, 401)
        self.assertEqual(anonymous_client.get("/healthz").status_code, 200)
        self.assertEqual(
            self.client.post("/patient/advance", json={"patient_id": "P001"}).status_code,
            400,
        )

    def test_advance_rejects_missing_csrf_and_malformed_json_without_writing(self):
        missing_csrf = self.client.post(
            "/patient/advance",
            json={"patient_id": "P001"},
        )
        malformed_json = self.client.post(
            "/patient/advance",
            data="{",
            content_type="application/json",
            headers={"X-CSRF-Token": self.csrf_token},
        )

        self.assertEqual(missing_csrf.status_code, 400)
        self.assertEqual(
            missing_csrf.get_json(),
            {"error": "A valid CSRF token is required."},
        )
        self.assertEqual(malformed_json.status_code, 400)
        self.assertEqual(malformed_json.get_json(), {"error": "A JSON object is required."})
        self.assertEqual(get_recent_observations(self.database_path, "P001"), [])

    def test_invalid_login_and_logout_are_controlled_and_csrf_protected(self):
        anonymous_client = create_app(
            self.dataset_path,
            self.database_path,
        ).test_client()
        login_page = anonymous_client.get("/login").get_data(as_text=True)
        csrf_token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            login_page,
        ).group(1)
        invalid_login = anonymous_client.post(
            "/login",
            data={
                "username": "test-user",
                "password": "incorrect",
                "csrf_token": csrf_token,
            },
        )
        self.assertEqual(invalid_login.status_code, 401)
        self.assertIn("Username or password is incorrect.", invalid_login.get_data(as_text=True))
        self.assertEqual(self.client.post("/logout").status_code, 400)
        self.assertEqual(
            self.client.post(
                "/logout",
                data={"csrf_token": self.csrf_token},
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get("/patients").status_code, 401)

    def test_security_headers_and_sensitive_api_cache_policy(self):
        response = self.client.get("/patient")
        dashboard = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(dashboard.headers["Cache-Control"], "no-store")

    def test_authentication_configuration_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "GKS_CARE_SECRET_KEY"):
            create_app(
                self.dataset_path,
                self.database_path,
                secret_key="short",
                auth_users={"test-user": generate_password_hash("test-password")},
            )

    def test_invalid_account_hash_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "invalid password hash"):
            create_app(
                self.dataset_path,
                self.database_path,
                secret_key="test-secret-key-with-at-least-thirty-two-characters",
                auth_users={"test-user": "not-a-password-hash"},
            )

    def test_database_path_can_be_selected_for_restore(self):
        restored_path = Path(self.temp_directory.name) / "restored.sqlite3"
        with patch.dict(os.environ, {"GKS_CARE_DATABASE": str(restored_path)}):
            app = create_app(
                self.dataset_path,
                secret_key="test-secret-key-with-at-least-thirty-two-characters",
                auth_users={"test-user": generate_password_hash("test-password")},
            )

        self.assertEqual(app.config["DATABASE_PATH"], str(restored_path))
        self.assertTrue(restored_path.is_file())

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
        self.advance_patient()

        restarted_app = create_app(self.dataset_path, self.database_path)
        restarted_app.config["TESTING"] = True
        restarted_client = restarted_app.test_client()
        csrf_token = self._login_for(restarted_client)
        response = restarted_client.get("/patient")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data["observations"]), 1)
        self.assertEqual([item["hr"] for item in data["observations"]], [80])
        self.assertEqual(
            restarted_client.post(
                "/patient/advance",
                json={"patient_id": "P001"},
                headers={"X-CSRF-Token": csrf_token},
            ).status_code,
            200,
        )
        self.assertEqual(
            len(restarted_client.get("/patient").get_json()["observations"]),
            2,
        )

    def test_missing_dataset_returns_controlled_service_error(self):
        missing_path = Path(self.temp_directory.name) / "missing.csv"
        app = create_app(missing_path, self.database_path)
        app.config["TESTING"] = True
        client = app.test_client()
        self._login_for(client)

        response = client.get("/patient")

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
                client = app.test_client()
                self._login_for(client)

                response = client.get("/patient")

                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.get_json(),
                    {"error": "Patient simulation data is currently unavailable."},
                )


if __name__ == "__main__":
    unittest.main()
