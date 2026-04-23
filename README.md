# GKS-CARE

**AI-Based Real-Time Patient Deterioration Monitoring System (Simulated)**

---

## Overview

This project is about building a system that can monitor patient health continuously and detect if their condition is getting worse. Instead of checking patients only at intervals, this system simulates real-time monitoring and gives alerts based on the patient’s vitals.

---

## Why I built this

In real hospitals, patients are not monitored every second. Because of this, early signs of deterioration can be missed, and by the time action is taken, the situation may become critical.

So I wanted to build a system that can track patient vitals continuously and give early warnings before things get serious.

---

## What this system does

* Reads patient data (heart rate, oxygen level, etc.)
* Simulates real-time monitoring using stored data
* Calculates risk level (Low / Medium / High)
* Gives reasons for the risk (like low oxygen, high heart rate)
* Shows how the condition changes over time

---

## Features

* Simulated real-time data streaming
* Risk detection based on vitals
* Explanation for each alert
* Different patient scenarios (stable, moderate, critical)
- Flask API for real-time data streaming
---

## Tech Used

* Python
* Pandas

(More features like Flask and UI will be added later)

---

## Project Structure

GKS-CARE/
│── app.py
│── risk_logic.py
│
├── data/
│   ├── stable.csv
│   ├── moderate.csv
│   └── critical.csv

---

## How to run

Clone the repo:

```id="t4f3r1"
git clone https://github.com/Tharun-GK/GKS-CARE.git
cd GKS-CARE
```

Install dependencies:

```id="2n7jkl"
pip install pandas
```

Run the project:

```id="h3z9xp"
python app.py
```

---

## Output

The system prints:

* Patient vitals
* Risk level
* Reasons for the risk

It updates every few seconds to simulate real-time monitoring.

---

## Future plans

* Build a dashboard UI
* Convert this into a real-time API
* Improve prediction logic

---

## Note

This project is only for learning purposes and not for real medical use.

---

## Author

Tharun G K
