from flask import Flask, jsonify, render_template
import pandas as pd
from risk_logic import calculate_risk

app = Flask(__name__)

# ------------------------------------
# Load Patient Dataset
# ------------------------------------

df = pd.read_csv("data/critical.csv")

index = 0
prev_row = None


# ------------------------------------
# Helper Functions
# ------------------------------------

def calculate_health_score(row, risk):
    score = 100

    # Heart Rate
    if row["hr"] > 120:
        score -= 25
    elif row["hr"] > 100:
        score -= 10

    # Oxygen Saturation
    if row["spo2"] < 90:
        score -= 30
    elif row["spo2"] < 95:
        score -= 15

    # Temperature
    if row["temp"] > 101:
        score -= 15
    elif row["temp"] > 99.5:
        score -= 8

    # AI Risk Penalty
    if risk == "Medium":
        score -= 10
    elif risk == "High":
        score -= 20

    return max(score, 0)


def get_patient_status(risk):
    if risk == "Low":
        return "Stable"
    elif risk == "Medium":
        return "Under Observation"
    else:
        return "Critical Condition"


def get_confidence(risk):
    if risk == "Low":
        return 76
    elif risk == "Medium":
        return 89
    else:
        return 97


def generate_bp(risk):
    if risk == "Low":
        return "120/80"

    elif risk == "Medium":
        return "140/90"

    return "165/105"


# ------------------------------------
# Routes
# ------------------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/patient")
def patient():

    global index, prev_row

    if index >= len(df):
        index = 0
        prev_row = None

    row = df.iloc[index]

    # AI Risk Logic
    risk, reasons = calculate_risk(row, prev_row)

    # Extra AI Information
    health_score = calculate_health_score(row, risk)
    status = get_patient_status(risk)
    confidence = get_confidence(risk)

    recommendation = {
        "Low": "Patient is stable. Continue regular monitoring.",
        "Medium": "Observe patient closely. Repeat vital checks.",
        "High": "Immediate medical attention recommended."
    }

    data = {

        # Patient Information
        "patient_id": "P001",
        "age": 45,
        "gender": "Male",

        "last_updated": int(row["time"]),

        # Vitals
        "hr": int(row["hr"]),
        "spo2": int(row["spo2"]),
        "temp": float(row["temp"]),
        "bp": generate_bp(risk),

        # AI Analysis
        "risk": risk,
        "status": status,
        "confidence": get_confidence(risk),
        "health_score": health_score,

        "reasons": reasons,
        "recommendation": recommendation[risk]

    }

    prev_row = row
    index += 1

    return jsonify(data)


# ------------------------------------
# Run Flask
# ------------------------------------

if __name__ == "__main__":
    app.run(debug=True)