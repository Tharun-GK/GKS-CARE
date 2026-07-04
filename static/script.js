// =====================================
// Live Trend Data
// =====================================

let hrHistory = [];
let spo2History = [];
let tempHistory = [];

const labels = new Array(15).fill("");

// =====================================
// Charts
// =====================================

const hrChart = new Chart(document.getElementById("hrChart"), {
    type: "line",
    data: {
        labels: labels,
        datasets: [{
            data: hrHistory,
            borderColor: "#ff4d6d",
            backgroundColor: "rgba(255,77,109,0.15)",
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

const spo2Chart = new Chart(document.getElementById("spo2Chart"), {
    type: "line",
    data: {
        labels: labels,
        datasets: [{
            data: spo2History,
            borderColor: "#2dd4bf",
            backgroundColor: "rgba(45,212,191,0.15)",
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

const tempChart = new Chart(document.getElementById("tempChart"), {
    type: "line",
    data: {
        labels: labels,
        datasets: [{
            data: tempHistory,
            borderColor: "#fbbf24",
            backgroundColor: "rgba(251,191,36,0.15)",
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

// =====================================
// Clock
// =====================================

function updateClock() {

    const now = new Date();

    document.getElementById("clock").innerText =
        now.toLocaleDateString() + " | " +
        now.toLocaleTimeString();
}

updateClock();
setInterval(updateClock, 1000);

// =====================================
// Dashboard Update
// =====================================

async function updateDashboard() {

    try {

        const response = await fetch("/patient");
        const data = await response.json();

        // ---------------- Patient Info ----------------

        document.getElementById("patient_id").innerText = data.patient_id;
        document.getElementById("age").innerText = data.age;
        document.getElementById("gender").innerText = data.gender;
        document.getElementById("time").innerText = data.last_updated;

        // ---------------- Vitals ----------------

        document.getElementById("hr").innerText = data.hr;
        document.getElementById("bp").innerText = data.bp;
        document.getElementById("spo2").innerText = data.spo2;
        document.getElementById("temp").innerText = data.temp;

        // ---------------- AI Summary ----------------

        document.getElementById("health_score").innerText =
            data.health_score + "%";

        document.getElementById("confidence").innerText =
            data.confidence + "%";

        document.getElementById("status").innerText =
            data.status;

        // Progress Bars

        document.getElementById("health_bar").style.width =
            data.health_score + "%";

        document.getElementById("confidence_bar").style.width =
            data.confidence + "%";

        // ---------------- Risk ----------------

        document.getElementById("risk").innerText =
            data.risk;

        document.getElementById("reason").innerText =
            data.reasons.join(", ");

        document.getElementById("recommendation").innerText =
            data.recommendation;

        // ---------------- Risk Color ----------------

        const risk = document.getElementById("risk");

        if (data.risk === "Low") {

            risk.style.color = "#00ff88";

        } else if (data.risk === "Medium") {

            risk.style.color = "#ffd000";

        } else {

            risk.style.color = "#ff3b3b";
        }

        // ---------------- Status Color ----------------

        const status = document.getElementById("status");

        if (data.status === "Stable") {

            status.style.color = "#00ff88";

        } else if (data.status === "Under Observation") {

            status.style.color = "#ffd000";

        } else {

            status.style.color = "#ff3b3b";
        }

        // ---------------- Charts ----------------

        hrHistory.push(data.hr);
        spo2History.push(data.spo2);
        tempHistory.push(data.temp);

        if (hrHistory.length > 15) hrHistory.shift();
        if (spo2History.length > 15) spo2History.shift();
        if (tempHistory.length > 15) tempHistory.shift();

        hrChart.update();
        spo2Chart.update();
        tempChart.update();

    }

    catch (error) {

        console.error("Dashboard Error:", error);

    }

}

// =====================================
// Start Dashboard
// =====================================

updateDashboard();

setInterval(updateDashboard, 2000);