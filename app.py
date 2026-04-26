from flask import Flask, jsonify, render_template
import pandas as pd
from risk_logic import calculate_risk

app = Flask(__name__)

df = pd.read_csv("data/critical.csv")
index = 0
prev_row = None

@app.route('/')
def dashboard():
    return render_template("dashboard.html")

@app.route('/patient')
def patient():
    global index, prev_row

    if index >= len(df):
        index = 0
        prev_row = None

    row = df.iloc[index]
    risk, reasons = calculate_risk(row, prev_row)

    data = {
        "time": int(row["time"]),
        "hr": int(row["hr"]),
        "spo2": int(row["spo2"]),
        "temp": float(row["temp"]),
        "risk": risk,
        "reasons": reasons
    }

    prev_row = row
    index += 1

    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)