# GKS-CARE

GKS-CARE is a Flask dashboard that demonstrates monitoring synthetic patient vital signs. Its risk levels are produced by fixed, explainable rules; it does not use a trained or clinically validated AI model.

> **Demonstration only.** Do not use this application for clinical decisions or real patient care. Measurements, patient history, emergency-response details, vital indicators, and guidance are examples. The application does not contact a clinician, hospital, or emergency service.

## Features

- Live-style dashboard updates from a local synthetic CSV dataset.
- Heart rate, SpO₂, temperature, and simulated blood-pressure display.
- Rule-based risk levels with contributing reasons.
- Recent trend charts, a vital indicator, and monitoring statistics.
- Example medical history, emergency-response information, and a risk-change activity log.
- Visible error state and automatic retry when the patient endpoint is unavailable.

## Requirements

- Python 3.10 or later
- Node.js 18 or later for the frontend tests

## Install and run

From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> in a browser. The application reads `data/critical.csv` relative to the project, regardless of the current working directory.

## Tests and validation

Run the Flask route and risk-rule tests:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run the JavaScript dashboard tests and syntax check:

```powershell
node --test tests/frontend.test.cjs
node --check static/script.js
```

## API

- `GET /` serves the dashboard.
- `GET /patient` returns the next synthetic observation and rule-based assessment as JSON. When the configured CSV is missing or invalid, it returns HTTP `503` with a non-sensitive error message.

The CSV must contain numeric `time`, `hr`, `spo2`, and `temp` columns. The bundled sample files are synthetic. The running demo uses `data/critical.csv`.

## Project structure

```text
app.py
risk_logic.py
requirements.txt
data/
  critical.csv
  moderate.csv
  stable.csv
static/
  script.js
  style.css
templates/
  dashboard.html
tests/
  frontend.test.cjs
  test_app.py
  test_risk_logic.py
```

## Current limitations

- Risk classification and the displayed vital indicator are simple demonstration logic, not diagnoses, validated predictions, or clinical scores.
- Blood pressure, patient details, medical history, and emergency-response information are illustrative values, not observations from verified records or live integrations.
- The application has no persistent storage, multi-user access, authentication, authorization, or real-time emergency integration.
- Chart.js is loaded from a public CDN, so charts require network access to that CDN.

Do not enter real patient or other sensitive information.
