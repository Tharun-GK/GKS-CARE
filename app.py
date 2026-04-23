from flask import Flask, jsonify
import pandas as pd
from risk_logic import calculate_risk

app = Flask(__name__)

# Load default dataset
df = pd.read_csv("data/critical.csv")

index = 0
prev_row = None


# ✅ Home route (no more 404)
@app.route('/')
def home():
    return "GKS-CARE API is running"


# ✅ Get patient data (main API)
@app.route('/patient', methods=['GET'])
def get_patient_data():
    global index, prev_row

    if index >= len(df):
        index = 0
        prev_row = None

    row = df.iloc[index]

    risk, reasons = calculate_risk(row, prev_row)

    data = {
        "time": int(row['time']),
        "hr": int(row['hr']),
        "spo2": int(row['spo2']),
        "temp": float(row['temp']),
        "risk": risk,
        "reasons": reasons
    }

    prev_row = row
    index += 1

    return jsonify(data)


# ✅ Switch patient type (stable / moderate / critical)
@app.route('/set_patient/<ptype>')
def set_patient(ptype):
    global df, index, prev_row

    file_map = {
        "stable": "data/stable.csv",
        "moderate": "data/moderate.csv",
        "critical": "data/critical.csv"
    }

    if ptype in file_map:
        df = pd.read_csv(file_map[ptype])
        index = 0
        prev_row = None
        return jsonify({"message": f"{ptype} patient loaded"})

    return jsonify({"error": "Invalid patient type"})


if __name__ == '__main__':
    app.run(debug=True)