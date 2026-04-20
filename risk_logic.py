def calculate_risk(row, prev_row=None):
    hr = row['hr']
    spo2 = row['spo2']
    temp = row['temp']

    risk = "Low"
    reasons = []

    if spo2 < 92:
        risk = "High"
        reasons.append("Critical oxygen level")
    elif spo2 < 95:
        risk = "Medium"
        reasons.append("Oxygen dropping")

    if hr > 110:
        risk = "High"
        reasons.append("Very high heart rate")
    elif hr > 95:
        if risk != "High":
            risk = "Medium"
        reasons.append("Elevated heart rate")

    if temp > 100:
        reasons.append("High temperature")

    if prev_row is not None:
        if spo2 < prev_row['spo2']:
            reasons.append("Oxygen decreasing trend")
        if hr > prev_row['hr']:
            reasons.append("Heart rate increasing trend")

    return risk, reasons