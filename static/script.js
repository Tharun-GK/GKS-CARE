const REFRESH_INTERVAL_MS = 2000;
const MAX_HISTORY_LENGTH = 15;
const MAX_ACTIVITY_LOG_ITEMS = 20;

let hrHistory = [];
let spo2History = [];
let tempHistory = [];
let monitoringSeconds = 0;
let updateInProgress = false;
let lastLoggedRisk = null;
let selectedPatientId = "P001";
let selectionVersion = 0;
let patientsLoaded = false;

function createChart(canvasId, history, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") {
        return null;
    }

    return new Chart(canvas, {
        type: "line",
        data: {
            labels: new Array(MAX_HISTORY_LENGTH).fill(""),
            datasets: [{
                data: history,
                borderColor: color,
                backgroundColor: color,
                fill: true,
                tension: 0.35
            }]
        },
        options: {
            responsive: true,
            animation: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    grid: {
                        color: "#334155"
                    }
                },
                y: {
                    grid: {
                        color: "#334155"
                    }
                }
            }
        }
    });
}

const hrChart = createChart("hrChart", hrHistory, "#ff4d6d");
const spo2Chart = createChart("spo2Chart", spo2History, "#2dd4bf");
const tempChart = createChart("tempChart", tempHistory, "#fbbf24");

function updateClock() {
    const clock = document.getElementById("clock");
    if (clock) {
        const now = new Date();
        clock.innerText = now.toLocaleDateString() + " | " + now.toLocaleTimeString();
    }
}

function showDashboardError(message) {
    const errorMessage = document.getElementById("dashboardError");
    if (errorMessage) {
        errorMessage.innerText = message;
        errorMessage.hidden = false;
    }
}

function hideDashboardError() {
    const errorMessage = document.getElementById("dashboardError");
    if (errorMessage) {
        errorMessage.hidden = true;
    }
}

function validateRiskAssessment(assessment) {
    return assessment
        && assessment.method === "deterministic_demo_rules"
        && typeof assessment.risk === "string"
        && typeof assessment.severity === "string"
        && typeof assessment.status === "string"
        && typeof assessment.next_step === "string"
        && assessment.data_quality
        && typeof assessment.data_quality.status === "string"
        && Array.isArray(assessment.factors)
        && assessment.factors.every(factor =>
            factor
            && typeof factor.code === "string"
            && typeof factor.label === "string"
            && typeof factor.affects_risk === "boolean"
        );
}

function validatePatientData(data) {
    return data
        && typeof data.patient_id === "string"
        && Number.isInteger(data.age)
        && typeof data.gender === "string"
        && Number.isFinite(data.hr)
        && Number.isFinite(data.spo2)
        && Number.isFinite(data.temp)
        && Number.isFinite(data.health_score)
        && data.health_score >= 0
        && data.health_score <= 100
        && Number.isFinite(data.last_updated)
        && typeof data.observed_at === "string"
        && Number.isFinite(Date.parse(data.observed_at))
        && ["F", "C"].includes(data.temperature_unit)
        && ["Low", "Medium", "High"].includes(data.risk)
        && [
            "No Demo Threshold Flagged",
            "Demo Review Suggested",
            "Demo High Pattern — Review"
        ].includes(data.status)
        && validateRiskAssessment(data.risk_assessment)
        && data.risk_assessment.risk === data.risk
        && Array.isArray(data.reasons)
        && data.reasons.every(reason => typeof reason === "string")
        && typeof data.recommendation === "string"
        && Array.isArray(data.observations)
        && data.observations.every(observation =>
            observation
            && Number.isFinite(observation.id)
            && Number.isFinite(observation.hr)
            && Number.isFinite(observation.spo2)
            && Number.isFinite(observation.temp)
            && typeof observation.measured_at === "string"
            && typeof observation.temperature_unit === "string"
        )
        && Array.isArray(data.medical_history)
        && data.medical_history.every(record =>
            typeof record.record_type === "string"
            && typeof record.value === "string"
        );
}

function addLog(message) {
    const logContainer = document.getElementById("activityLog");
    if (!logContainer) {
        return;
    }

    const item = document.createElement("div");
    item.className = "log-item";

    const time = document.createElement("span");
    time.className = "log-time";
    time.innerText = new Date().toLocaleTimeString();

    const text = document.createElement("span");
    text.className = "log-text";
    text.innerText = message;

    item.append(time, text);
    logContainer.prepend(item);

    while (logContainer.children.length > MAX_ACTIVITY_LOG_ITEMS) {
        logContainer.removeChild(logContainer.lastChild);
    }
}

function updateRiskStatus(data) {
    const risk = document.getElementById("risk");
    if (risk) {
        risk.innerText = data.risk;
        risk.style.color = {
            Low: "#00ff88",
            Medium: "#ffd000",
            High: "#ff3b3b",
            Unavailable: "#94a3b8"
        }[data.risk];
    }

    const banner = document.getElementById("alertBanner");
    if (banner) {
        banner.style.display = data.risk === "High" ? "flex" : "none";
    }

    if (data.risk !== lastLoggedRisk) {
        const messages = {
            Low: "Demo rules report no threshold flagged",
            Medium: "Demo rules flagged a moderate pattern",
            High: "Demo rules flagged a high-risk pattern",
            Unavailable: "Demo assessment unavailable"
        };
        addLog(messages[data.risk]);
        lastLoggedRisk = data.risk;
    }
}

function renderUnavailableAssessment(payload) {
    const assessment = payload.risk_assessment;
    const factors = assessment.factors.map(factor => factor.label);
    const displayFields = {
        hr: "--",
        bp: "--",
        spo2: "--",
        temp: "--",
        time: "--",
        health_score: "--",
        status: assessment.status,
        risk: assessment.risk,
        reason: factors.join(", "),
        recommendation: assessment.next_step,
        max_hr: "--",
        min_spo2: "--",
        avg_temp: "--"
    };
    Object.entries(displayFields).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) {
            element.innerText = value;
        }
    });

    const healthBar = document.getElementById("health_bar");
    if (healthBar) {
        healthBar.style.width = "0";
    }
    const status = document.getElementById("status");
    if (status) {
        status.style.color = "#94a3b8";
    }
    updateRiskStatus({ risk: "Unavailable" });

    hrHistory.length = 0;
    spo2History.length = 0;
    tempHistory.length = 0;
    [hrChart, spo2Chart, tempChart].forEach(chart => {
        if (chart) {
            chart.data.datasets[0].data = [];
            chart.update();
        }
    });

    showDashboardError(payload.error || assessment.next_step);
}

function updateStatistics() {
    if (hrHistory.length > 0) {
        const highestHeartRate = document.getElementById("max_hr");
        if (highestHeartRate) {
            highestHeartRate.innerText = Math.max(...hrHistory);
        }
    }

    if (spo2History.length > 0) {
        const lowestOxygen = document.getElementById("min_spo2");
        if (lowestOxygen) {
            lowestOxygen.innerText = Math.min(...spo2History) + "%";
        }
    }

    if (tempHistory.length > 0) {
        const averageTemperature = tempHistory.reduce((total, value) => total + value, 0)
            / tempHistory.length;
        const averageTemperatureElement = document.getElementById("avg_temp");
        if (averageTemperatureElement) {
            averageTemperatureElement.innerText = averageTemperature.toFixed(1) + "°F";
        }
    }
}

function clearSelectedPatientData() {
    hrHistory.length = 0;
    spo2History.length = 0;
    tempHistory.length = 0;
    lastLoggedRisk = null;

    [
        "patient_id",
        "age",
        "gender",
        "time",
        "hr",
        "bp",
        "spo2",
        "temp",
        "status",
        "risk",
        "reason",
        "recommendation",
        "health_score",
        "max_hr",
        "min_spo2",
        "avg_temp",
        "blood_group",
        "allergies",
        "diabetes",
        "hypertension",
        "surgery",
        "medicine"
    ].forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.innerText = "--";
            element.style.color = "";
        }
    });

    const healthBar = document.getElementById("health_bar");
    if (healthBar) {
        healthBar.style.width = "0";
    }

    const banner = document.getElementById("alertBanner");
    if (banner) {
        banner.style.display = "none";
    }

    const activityLog = document.getElementById("activityLog");
    if (activityLog) {
        while (activityLog.children.length > 0) {
            activityLog.removeChild(activityLog.lastChild);
        }
    }

    [
        [hrChart, hrHistory],
        [spo2Chart, spo2History],
        [tempChart, tempHistory]
    ].forEach(([chart, history]) => {
        if (chart) {
            chart.data.datasets[0].data = history;
            chart.update();
        }
    });
}

function populatePatientSelector(patients) {
    const selector = document.getElementById("patientSelector");
    if (!selector) {
        return;
    }

    while (selector.children.length > 0) {
        selector.removeChild(selector.lastChild);
    }

    patients.forEach(patient => {
        const option = document.createElement("option");
        option.value = patient.patient_id;
        option.innerText = `${patient.patient_id} · ${patient.gender}, age ${patient.age} · Synthetic`;
        selector.append(option);
    });

    if (!patients.some(patient => patient.patient_id === selectedPatientId)) {
        selectedPatientId = patients[0].patient_id;
    }

    selector.value = selectedPatientId;
    selector.disabled = false;
    selector.addEventListener("change", () => {
        if (!selector.value || selector.value === selectedPatientId) {
            return;
        }

        selectedPatientId = selector.value;
        selectionVersion++;
        clearSelectedPatientData();
        updateDashboard();
    });
}

async function loadPatients() {
    const response = await fetch("/patients");
    if (!response.ok) {
        throw new Error("Patient list endpoint returned HTTP " + response.status);
    }

    const data = await response.json();
    if (!data || !Array.isArray(data.patients) || data.patients.length === 0) {
        throw new Error("Patient list endpoint returned no patients.");
    }

    const validPatients = data.patients.every(patient =>
        patient
        && typeof patient.patient_id === "string"
        && Number.isInteger(patient.age)
        && typeof patient.gender === "string"
        && patient.data_source === "synthetic_demo"
    );
    if (!validPatients) {
        throw new Error("Patient list endpoint returned invalid patient data.");
    }

    populatePatientSelector(data.patients);
    patientsLoaded = true;
}

async function updateDashboard() {
    if (updateInProgress || !patientsLoaded) {
        return;
    }

    const requestedPatientId = selectedPatientId;
    const requestedSelectionVersion = selectionVersion;
    updateInProgress = true;

    try {
        const response = await fetch(
            "/patient?patient_id=" + encodeURIComponent(requestedPatientId)
        );
        const data = await response.json();
        if (requestedSelectionVersion !== selectionVersion) {
            return;
        }
        if (
            response.status === 422
            && data
            && validateRiskAssessment(data.risk_assessment)
            && data.risk_assessment.risk === "Unavailable"
        ) {
            renderUnavailableAssessment(data);
            return;
        }
        if (!response.ok) {
            throw new Error("Patient endpoint returned HTTP " + response.status);
        }

        if (!validatePatientData(data) || data.patient_id !== requestedPatientId) {
            throw new Error("Patient endpoint returned an invalid response.");
        }

        hideDashboardError();

        const patientFields = {
            patient_id: data.patient_id,
            age: data.age,
            gender: data.gender,
            time: new Date(data.observed_at).toLocaleString(),
            hr: data.hr,
            bp: data.bp,
            spo2: data.spo2,
            temp: data.temp,
            health_score: data.health_score + "%",
            status: data.status,
            reason: data.reasons.join(", "),
            recommendation: data.recommendation
        };

        Object.entries(patientFields).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.innerText = value;
            }
        });

        const healthBar = document.getElementById("health_bar");
        if (healthBar) {
            healthBar.style.width = data.health_score + "%";
        }

        updateRiskStatus(data);

        const status = document.getElementById("status");
        if (status) {
            status.style.color = {
                "No Demo Threshold Flagged": "#00ff88",
                "Demo Review Suggested": "#ffd000",
                "Demo High Pattern — Review": "#ff3b3b"
            }[data.status] || "";
        }

        const recentObservations = data.observations.slice(-MAX_HISTORY_LENGTH);
        hrHistory.splice(0, hrHistory.length, ...recentObservations.map(item => item.hr));
        spo2History.splice(0, spo2History.length, ...recentObservations.map(item => item.spo2));
        tempHistory.splice(0, tempHistory.length, ...recentObservations.map(item => item.temp));

        const historyFields = {
            blood_group: "blood_group",
            allergies: "allergies",
            diabetes: "diabetes",
            hypertension: "hypertension",
            surgery: "surgery",
            medicine: "medicine"
        };
        data.medical_history.forEach(record => {
            const fieldId = historyFields[record.record_type];
            const element = fieldId ? document.getElementById(fieldId) : null;
            if (element) {
                element.innerText = record.value;
            }
        });

        [hrChart, spo2Chart, tempChart].forEach(chart => {
            if (chart) {
                chart.update();
            }
        });

        updateStatistics();
    } catch (error) {
        if (requestedSelectionVersion !== selectionVersion) {
            return;
        }
        console.error("Dashboard update failed:", error);
        const message =
            "Live measurements are unavailable. Displayed readings may be out of date; retrying automatically.";
        renderUnavailableAssessment({
            error: message,
            risk_assessment: {
                risk: "Unavailable",
                severity: "unknown",
                status: "Assessment Unavailable",
                method: "deterministic_demo_rules",
                factors: [{
                    code: "data_quality",
                    label: "No current valid assessment is available.",
                    affects_risk: true
                }],
                next_step: "Check data availability before interpreting this demonstration.",
                data_quality: { status: "unavailable" }
            }
        });
    } finally {
        updateInProgress = false;
        setTimeout(updateDashboard, REFRESH_INTERVAL_MS);
    }
}

async function initializeDashboard() {
    try {
        await loadPatients();
        updateDashboard();
    } catch (error) {
        console.error("Patient list load failed:", error);
        showDashboardError(
            "Synthetic patient choices are unavailable. Retrying automatically."
        );
        setTimeout(initializeDashboard, REFRESH_INTERVAL_MS);
    }
}

updateClock();
setInterval(updateClock, 1000);
initializeDashboard();

setInterval(() => {
    monitoringSeconds++;

    const hours = Math.floor(monitoringSeconds / 3600);
    const minutes = Math.floor((monitoringSeconds % 3600) / 60);
    const seconds = monitoringSeconds % 60;
    const monitoringTime = document.getElementById("monitor_time");

    if (monitoringTime) {
        monitoringTime.innerText = [
            String(hours).padStart(2, "0"),
            String(minutes).padStart(2, "0"),
            String(seconds).padStart(2, "0")
        ].join(":");
    }
}, 1000);
