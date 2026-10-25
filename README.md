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
- Individual local accounts, authenticated dashboard/API access, CSRF protection, and SQLite backup/restore commands.

## Requirements

- Python 3.11 or later
- Node.js 18 or later for the frontend tests
- HTTPS is not configured; the server is intentionally restricted to localhost.

## Install and run

From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Generate a random session-signing key for this PowerShell session.
$env:GKS_CARE_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"

# Create one or more local accounts; enter a unique username and a 12+ character password.
$env:GKS_CARE_USERS = python .\configure_accounts.py

# Start the Waitress server, bound to 127.0.0.1.
python app.py
```

Open <http://127.0.0.1:5000> in a browser and sign in with one of the configured accounts. Keep the PowerShell window open while using the application; press Ctrl+C to stop the server. The account hashes and session key are held in the current shell environment, so configure them again in a new shell. Never commit account details, session keys, real patient information, or database backups.

On startup, the application initializes the version 1 schema from `schema.sql`, creates synthetic `P001`, `P002`, and `P003` demo records if they do not exist, and stores the local database at `instance/gks-care.sqlite3`. The database and `instance/` directory are ignored by Git. The dashboard's authenticated `POST /patient/advance` records an observation and corresponding audit event, including the account name, for only the selected patient. Dashboard charts use the selected patient's recent stored observations, so they survive page reloads and application restarts. A read-only `GET /patient` does not advance the simulation or write an observation.

To use another SQLite path, set `GKS_CARE_DATABASE` before starting the app. The optional `GKS_CARE_COOKIE_SECURE=true` setting is only for HTTPS deployments; this prototype does not configure HTTPS or permit network access.

### Backup and restore

Stop the application before restoring. Create a consistent backup at a new path (the commands refuse to overwrite existing files):

```powershell
python -m database backup .\instance\gks-care.sqlite3 .\backups\gks-care-backup.sqlite3
python -m database restore .\backups\gks-care-backup.sqlite3 .\instance\gks-care-restored.sqlite3
```

The restore command validates SQLite integrity and creates a new database file. To run against that restored file, set `$env:GKS_CARE_DATABASE = ".\instance\gks-care-restored.sqlite3"` in the same PowerShell session before `python app.py`. Keep backups outside the repository and protect them as sensitive files, even though this prototype is intended to contain synthetic data only.

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
- `GET /login` and `POST /login` provide local-account sign-in. `POST /logout` signs out and requires a CSRF token.
- `GET /healthz` returns minimal application/database status and does not require sign-in.
- Authenticated `GET /patients` lists the available synthetic patient identifiers and demo metadata.
- Authenticated `GET /patient` returns the current simulation sample for the default `P001` patient, preserving the original response shape without advancing or persisting it.
- Authenticated `GET /patient?patient_id=P002` reads the current sample for the selected patient without writing.
- Authenticated `POST /patient/advance` accepts a JSON object with an optional `patient_id` and a session CSRF token in `X-CSRF-Token`. It advances the selected demo stream and persists its observation and audit event. Malformed identifiers return `400`, unknown patients return `404`, missing/invalid datasets return `503`, and invalid vital ranges return `422` with a structured unavailable assessment; unavailable measurements are not persisted.

The dashboard and patient APIs require an account. `configure_accounts.py` prompts for usernames and passwords without echoing password input and prints a JSON object of Werkzeug password hashes for the `GKS_CARE_USERS` environment variable. The server binds to `127.0.0.1` and uses Waitress with debug mode disabled. It is not configured for LAN access, HTTPS termination, account recovery, access throttling, or a real-world pilot. Do not expose it to another device, a public network, or real patient data.

Each CSV must contain numeric `time`, `hr`, `spo2`, and `temp` columns. A nonpositive heart rate or SpO₂ outside 0–100% returns an explicit `422` assessment-unavailable response and is not persisted as an observation. Missing columns or nonnumeric/non-finite CSV values keep the selected dataset unavailable with `503`. The bundled sample files are synthetic: `P001` uses `data/critical.csv`, `P002` uses `data/moderate.csv`, and `P003` uses `data/stable.csv`. Each patient has independent simulation progress, observations, history, and dashboard charts.

The rule and vital-indicator demonstration thresholds are centralized in `RiskThresholds`. Embedding applications can override selected values when constructing the Flask app, for example `create_app(risk_thresholds={"spo2_high_below": 91})`; unknown, non-finite, and inconsistent threshold configurations are rejected at startup. The API includes a structured `risk_assessment` with the method, severity, factors, next step, data-quality state, and explicit disclosure that the values are not clinically validated. A `Low` result means only that these configured demonstration rules did not flag a threshold; it is not a reassurance that a person is well. The application does not check measurement freshness or population-specific context.

## Project structure

```text
app.py
configure_accounts.py
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
  login.html
tests/
  frontend.test.cjs
  test_app.py
  test_repository.py
  test_risk_logic.py
```

## Current limitations

- Risk classification and the displayed vital indicator use deterministic demonstration logic, not diagnoses, validated predictions, or clinical scores. The inherited example rules use SpO₂ below 92% (high) or below 95% (medium), heart rate above 110 bpm (high) or above 95 bpm (medium), and a temperature note above 100°F. Temperature notes and sample-to-sample trends explain the sample but do not raise the risk level. The separate vital indicator also has its own demonstration scoring thresholds; it is not a clinical score. These example values have not been sourced from clinical guidance, validated for any population, or endorsed for care.
- Blood pressure, patient details, medical history, and emergency-response information are illustrative values, not observations from verified records or live integrations.
- Local accounts authenticate users but do not provide patient-level permissions; all users can view all synthetic demo profiles. There is no account recovery, access throttling, multi-factor authentication, or externally managed identity.
- SQLite is a local demonstration store. Backup and restore commands are provided, but no automated backup schedule or retention policy is configured.
- Each successful `POST /patient/advance` records another synthetic observation; repeated posts are not deduplicated. The in-memory simulation position restarts from its first sample after an application restart, while stored observations and audit events remain persisted.
- Chart.js 4.4.7 is loaded from jsDelivr with Subresource Integrity; charts require network access to that CDN.
- The server is localhost-only and has not been configured or security-tested for a controlled network pilot. HTTPS, rate limiting, production secret management, and deployment hardening remain prerequisites for any network exposure.

Do not enter real patient or other sensitive information.
