import unittest

from risk_logic import calculate_risk


def vitals(hr=80, spo2=98, temp=98.6):
    return {"hr": hr, "spo2": spo2, "temp": temp}


class RiskLogicTests(unittest.TestCase):
    def test_normal_vitals_are_low_risk(self):
        risk, reasons = calculate_risk(vitals())

        self.assertEqual(risk, "Low")
        self.assertEqual(reasons, [])

    def test_oxygen_and_heart_rate_thresholds(self):
        cases = (
            (vitals(hr=95, spo2=95), "Low"),
            (vitals(spo2=94), "Medium"),
            (vitals(spo2=92), "Medium"),
            (vitals(spo2=91), "High"),
            (vitals(hr=110), "Medium"),
            (vitals(hr=111), "High"),
        )

        for patient_vitals, expected_risk in cases:
            with self.subTest(vitals=patient_vitals):
                risk, _ = calculate_risk(patient_vitals)
                self.assertEqual(risk, expected_risk)

    def test_temperature_and_measurement_trends_are_explained(self):
        risk, reasons = calculate_risk(
            vitals(hr=105, spo2=94, temp=100.1),
            prev_row=vitals(hr=100, spo2=96),
        )

        self.assertEqual(risk, "Medium")
        self.assertIn("High temperature", reasons)
        self.assertIn("Oxygen decreasing trend", reasons)
        self.assertIn("Heart rate increasing trend", reasons)

    def test_temperature_boundary_does_not_add_high_temperature_reason(self):
        _, reasons = calculate_risk(vitals(temp=100))

        self.assertNotIn("High temperature", reasons)


if __name__ == "__main__":
    unittest.main()
