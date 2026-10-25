# GKS-CARE

GKS-CARE is a Flask dashboard that demonstrates monitoring synthetic patient vital signs. Its risk levels are produced by configurable, explainable rules; it does not use a trained or clinically validated AI model.

> **Demonstration only.** Do not use this application for clinical decisions or real patient care. Measurements, patient history, emergency-response details, vital indicators, and guidance are examples. The application does not contact a clinician, hospital, or emergency service.

## Features

- Live-style dashboard updates from a local synthetic CSV dataset.
- Heart rate, SpO₂, temperature, and simulated blood-pressure display.
- Configurable, explainable demonstration risk levels and explicit missing/invalid-data outcomes.
- Recent trend charts, a vital indicator, and monitoring statistics.
- Example medical history, emergency-response information, and a risk-change activity log.
- Visible error state and automatic retry when the patient endpoint is unavailable.
- Local SQLite storage for the synthetic patient, example history, observations, and audit events.
- Selection among three synthetic demo patients, each with isolated sample data and history.

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

Open <http://127.0.0.1:5000> in a browser. The application reads its sample datasets relative to the project, regardless of the current working directory.

On startup, the application initializes the version 1 schema from `schema.sql`, creates synthetic `P001`, `P002`, and `P003` demo records if they do not exist, and stores the local database at `instance/gks-care.sqlite3`. The database and `instance/` directory are ignored by Git. Each successful `GET /patient` records an observation and corresponding audit event for only the selected patient. Dashboard charts use the selected patient's recent stored observations, so they survive page reloads and application restarts.

Observation timestamps must include a timezone and are normalized to UTC. Heart rate must be a finite positive number, SpO₂ must be between 0 and 100 percent, and temperature must be finite and use `F` or `C`. These are storage/input constraints, not clinical thresholds or statements of normality. Patient identifiers are restricted to letters, digits, underscores, and hyphens.

The schema is initialized idempotently using `CREATE TABLE IF NOT EXISTS` and records its current version in `schema_migrations`. There is no automatic migration runner yet; future schema changes must add a documented migration before changing existing databases.

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
- `GET /patients` lists the available synthetic patient identifiers and demo metadata.
- `GET /patient` returns the next observation for the default `P001` patient, preserving the original single-patient request behavior.
- `GET /patient?patient_id=P002` returns the next observation for the selected patient. Malformed identifiers return `400`, unknown patients return `404`, missing/invalid datasets return `503`, and invalid vital ranges return `422` with a structured unavailable assessment.

Each CSV must contain numeric `time`, `hr`, `spo2`, and `temp` columns. A nonpositive heart rate or SpO₂ outside 0–100% returns an explicit `422` assessment-unavailable response and is not persisted as an observation. Missing columns or nonnumeric/non-finite CSV values keep the selected dataset unavailable with `503`. The bundled sample files are synthetic: `P001` uses `data/critical.csv`, `P002` uses `data/moderate.csv`, and `P003` uses `data/stable.csv`. Each patient has independent simulation progress, observations, history, and dashboard charts.

The rule and vital-indicator demonstration thresholds are centralized in `RiskThresholds`. Embedding applications can override selected values when constructing the Flask app, for example `create_app(risk_thresholds={"spo2_high_below": 91})`; unknown, non-finite, and inconsistent threshold configurations are rejected at startup. The API includes a structured `risk_assessment` with the method, severity, factors, next step, data-quality state, and explicit disclosure that the values are not clinically validated. A `Low` result means only that these configured demonstration rules did not flag a threshold; it is not a reassurance that a person is well. The application does not check measurement freshness or population-specific context.

## Project structure

```text
app.py
database.py
repository.py
risk_logic.py
requirements.txt
schema.sql
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
  test_repository.py
  test_risk_logic.py
```

## Current limitations

- Risk classification and the displayed vital indicator use deterministic demonstration logic, not diagnoses, validated predictions, or clinical scores. The inherited example rules use SpO₂ below 92% (high) or below 95% (medium), heart rate above 110 bpm (high) or above 95 bpm (medium), and a temperature note above 100°F. Temperature notes and sample-to-sample trends explain the sample but do not raise the risk level. The separate vital indicator also has its own demonstration scoring thresholds; it is not a clinical score. These example values have not been sourced from clinical guidance, validated for any population, or endorsed for care.
- Blood pressure, patient details, medical history, and emergency-response information are illustrative values, not observations from verified records or live integrations.
- The patient selector is a demo workflow, not an authentication or authorization boundary. All patient records remain synthetic.
- SQLite is a single-user local demonstration store. There is no multi-user access, authentication, authorization, backup/retention workflow, or real-time emergency integration.
- Each successful patient API request records another synthetic observation; the application does not deduplicate observations.
- Chart.js is loaded from a public CDN, so charts require network access to that CDN.

Do not enter real patient or other sensitive information.
