# GKS-CARE

**AI-Based Real-Time Patient Deterioration Monitoring System (Simulated)**

---

## Overview

GKS-CARE is an AI-based patient monitoring system that simulates real-time hospital vital tracking.
It continuously reads patient data, analyzes risk level, and displays alerts through a live dashboard.

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

* Real-time patient vital monitoring
* Live dashboard interface
* Auto-refreshing data every few seconds
* Risk prediction (Low / Medium / High)
* Alert reasons shown instantly
* Simulated stable / moderate / critical patients

---

## Tech Stack

* Python
* Flask
* HTML
* CSS
* JavaScript
* Pandas


---

## Project Structure

GKS-CARE/
│── app.py
│── risk_logic.py
│── README.md

├── data/
│   ├── stable.csv
│   ├── moderate.csv
│   └── critical.csv

├── templates/
│   └── dashboard.html

├── static/
│   ├── style.css
│   └── script.js


---

## How to Run

```bash
git clone https://github.com/Tharun-GK/GKS-CARE.git
cd GKS-CARE
pip install flask pandas
python app.py
```

Then open:

http://127.0.0.1:5000


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
## Dashboard Preview

<img width="1802" height="854" alt="image" src="https://github.com/user-attachments/assets/5f98bddf-ef02-4c95-8069-48321b911f04" />


## Note

This project is only for learning purposes and not for real medical use.

---

## Author

Tharun G K
