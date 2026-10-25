const REFRESH_INTERVAL_MS = 2000;
const MAX_HISTORY_LENGTH = 15;
const MAX_ACTIVITY_LOG_ITEMS = 20;

let hrHistory = [];
let spo2History = [];
let tempHistory = [];
let monitoringSeconds = 0;
let updateInProgress = false;
let lastLoggedRisk = null;

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

function validatePatientData(data) {
    return data
        && Number.isFinite(data.hr)
        && Number.isFinite(data.spo2)
        && Number.isFinite(data.temp)
        && Number.isFinite(data.health_score)
        && Number.isFinite(data.last_updated)
        && ["Low", "Medium", "High"].includes(data.risk)
        && Array.isArray(data.reasons)
        && typeof data.recommendation === "string";
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
            High: "#ff3b3b"
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
            High: "Demo rules flagged a high-risk pattern"
        };
        addLog(messages[data.risk]);
        lastLoggedRisk = data.risk;
    }
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

async function updateDashboard() {
    if (updateInProgress) {
        return;
    }

    updateInProgress = true;

    try {
        const response = await fetch("/patient");
        if (!response.ok) {
            throw new Error("Patient endpoint returned HTTP " + response.status);
        }

        const data = await response.json();
        if (!validatePatientData(data)) {
            throw new Error("Patient endpoint returned an invalid response.");
        }

        hideDashboardError();

        const patientFields = {
            patient_id: data.patient_id,
            age: data.age,
            gender: data.gender,
            time: data.last_updated,
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
                Stable: "#00ff88",
                "Under Observation": "#ffd000",
                "Critical Condition": "#ff3b3b"
            }[data.status] || "";
        }

        hrHistory.push(data.hr);
        spo2History.push(data.spo2);
        tempHistory.push(data.temp);

        if (hrHistory.length > MAX_HISTORY_LENGTH) hrHistory.shift();
        if (spo2History.length > MAX_HISTORY_LENGTH) spo2History.shift();
        if (tempHistory.length > MAX_HISTORY_LENGTH) tempHistory.shift();

        [hrChart, spo2Chart, tempChart].forEach(chart => {
            if (chart) {
                chart.update();
            }
        });

        updateStatistics();
    } catch (error) {
        console.error("Dashboard update failed:", error);
        showDashboardError(
            "Live measurements are unavailable. Displayed readings may be out of date; retrying automatically."
        );
    } finally {
        updateInProgress = false;
        setTimeout(updateDashboard, REFRESH_INTERVAL_MS);
    }
}

updateClock();
setInterval(updateClock, 1000);
updateDashboard();

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
