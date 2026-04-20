import pandas as pd
from risk_logic import calculate_risk
import time

df = pd.read_csv("data/critical.csv")  # change file here

prev_row = None

for i in range(len(df)):
    row = df.iloc[i]

    risk, reasons = calculate_risk(row, prev_row)

    print(f"\nTime: {row['time']}")
    print(f"HR: {row['hr']} | SpO2: {row['spo2']} | Temp: {row['temp']}")
    print(f"Risk Level: {risk}")
    print(f"Reason: {', '.join(reasons)}")

    prev_row = row

    time.sleep(2)