import math
import unittest

from risk_logic import RiskThresholds, assess_vitals, calculate_risk


def vitals(hr=80, spo2=98, temp=98.6):
    return {"hr": hr, "spo2": spo2, "temp": temp}


class RiskLogicTests(unittest.TestCase):
    def test_normal_vitals_are_low_with_an_explicit_demo_assessment(self):
        assessment = assess_vitals(vitals())

        self.assertEqual(assessment.risk, "Low")
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(assessment.data_quality, "complete")
        self.assertEqual(assessment.reasons, [])
        payload = assessment.to_dict()
        self.assertEqual(payload["method"], "deterministic_demo_rules")
        self.assertFalse(payload["clinically_validated"])

    def test_threshold_boundaries_preserve_the_existing_demo_rules(self):
        cases = (
            (vitals(hr=95, spo2=95), "Low"),
            (vitals(spo2=94.99), "Medium"),
            (vitals(spo2=92), "Medium"),
            (vitals(spo2=91.99), "High"),
            (vitals(hr=95), "Low"),
            (vitals(hr=95.01), "Medium"),
            (vitals(hr=110), "Medium"),
            (vitals(hr=110.01), "High"),
        )

        for patient_vitals, expected_risk in cases:
            with self.subTest(vitals=patient_vitals):
                self.assertEqual(assess_vitals(patient_vitals).risk, expected_risk)

    def test_combined_rules_use_the_highest_severity_and_explain_each_factor(self):
        assessment = assess_vitals(vitals(hr=111, spo2=91, temp=100.1))

        self.assertEqual(assessment.risk, "High")
        self.assertEqual(
            [factor["code"] for factor in assessment.factors],
            ["spo2_demo_high", "heart_rate_demo_high", "temperature_demo_note"],
        )
        self.assertTrue(assessment.factors[0]["affects_risk"])
        self.assertFalse(assessment.factors[-1]["affects_risk"])

    def test_temperature_and_trends_are_explained_without_changing_risk(self):
        assessment = assess_vitals(
            vitals(hr=95, spo2=95, temp=100.1),
            previous_row=vitals(hr=90, spo2=96),
        )

        self.assertEqual(assessment.risk, "Low")
        self.assertEqual(
            [factor["code"] for factor in assessment.factors],
            ["temperature_demo_note", "spo2_demo_trend", "heart_rate_demo_trend"],
        )
        self.assertTrue(all(not factor["affects_risk"] for factor in assessment.factors))

    def test_temperature_note_boundary_is_exclusive(self):
        assessment = assess_vitals(vitals(temp=100))

        self.assertEqual(assessment.risk, "Low")
        self.assertEqual(assessment.factors, ())

    def test_missing_or_invalid_vitals_never_become_low_risk(self):
        invalid_rows = (
            {"hr": 80, "spo2": 98},
            {"hr": None, "spo2": 98, "temp": 98.6},
            vitals(hr="not-a-number"),
            vitals(spo2=math.nan),
            vitals(temp=math.inf),
            vitals(hr=0),
            vitals(spo2=-1),
            vitals(spo2=100.1),
        )

        for patient_vitals in invalid_rows:
            with self.subTest(vitals=patient_vitals):
                assessment = assess_vitals(patient_vitals)
                self.assertEqual(assessment.risk, "Unavailable")
                self.assertEqual(assessment.severity, "unknown")
                self.assertEqual(assessment.data_quality, "incomplete_or_invalid")
                self.assertTrue(assessment.factors)
                self.assertEqual(assessment.to_dict()["status"], "Assessment Unavailable")

    def test_invalid_previous_sample_is_ignored_without_hiding_current_risk(self):
        assessment = assess_vitals(
            vitals(),
            previous_row={"hr": "invalid", "spo2": math.nan},
        )

        self.assertEqual(assessment.risk, "Low")
        self.assertEqual(assessment.factors, ())

    def test_thresholds_can_be_overridden_and_configuration_is_validated(self):
        custom = RiskThresholds.from_mapping({"spo2_medium_below": 99})

        self.assertEqual(assess_vitals(vitals(), thresholds=custom).risk, "Medium")
        self.assertEqual(
            RiskThresholds.from_mapping({"spo2_high_below": 90}).spo2_high_below,
            90,
        )
        with self.assertRaisesRegex(ValueError, "below its medium threshold"):
            RiskThresholds.from_mapping({"spo2_high_below": 96})
        with self.assertRaisesRegex(ValueError, "finite number"):
            RiskThresholds.from_mapping({"heart_rate_high_above": math.inf})
        with self.assertRaisesRegex(ValueError, "score SpO2"):
            RiskThresholds.from_mapping({"score_spo2_low_below": 96})
        with self.assertRaisesRegex(ValueError, "Unknown risk threshold"):
            RiskThresholds.from_mapping({"unknown": 1})

    def test_legacy_calculate_risk_wrapper_remains_available(self):
        risk, reasons = calculate_risk(vitals(hr=111))

        self.assertEqual(risk, "High")
        self.assertEqual(len(reasons), 1)
        self.assertIn("Heart rate", reasons[0])


if __name__ == "__main__":
    unittest.main()
