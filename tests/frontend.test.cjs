const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
    path.join(__dirname, "..", "static", "script.js"),
    "utf8"
);

const samplePatient = {
    patient_id: "P001",
    age: 45,
    gender: "Male",
    data_source: "synthetic_demo",
    last_updated: 1,
    observed_at: "2026-01-02T03:04:05Z",
    hr: 112,
    spo2: 89,
    temp: 101.2,
    temperature_unit: "F",
    bp: "165/105",
    risk: "High",
    status: "Critical Condition",
    health_score: 20,
    reasons: ["Critical oxygen level"],
    recommendation: "Demo guidance",
    observations: [{
        id: 1,
        measured_at: "2026-01-02T03:04:05Z",
        hr: 112,
        hr_unit: "bpm",
        spo2: 89,
        spo2_unit: "%",
        temp: 101.2,
        temperature_unit: "F",
        source: "synthetic_csv"
    }],
    medical_history: [{
        record_type: "allergies",
        value: "Penicillin",
        source: "synthetic_demo",
        updated_at: "2026-01-02T03:04:05Z"
    }]
};

function createDashboard({ response, canvases = true, includeChart = true, fetchImpl } = {}) {
    class Element {
        constructor() {
            this.innerText = "--";
            this.hidden = false;
            this.style = {};
            this.children = [];
        }

        append(...elements) {
            this.children.push(...elements);
        }

        prepend(element) {
            this.children.unshift(element);
        }

        removeChild(element) {
            const index = this.children.indexOf(element);
            if (index >= 0) {
                this.children.splice(index, 1);
            }
        }
    }

    const elements = new Map();
    const charts = [];
    const scheduledTimeouts = [];
    const scheduledIntervals = [];
    const consoleErrors = [];

    const document = {
        getElementById(id) {
            if (!canvases && ["hrChart", "spo2Chart", "tempChart"].includes(id)) {
                return null;
            }
            if (!elements.has(id)) {
                const element = new Element();
                if (id === "dashboardError") {
                    element.hidden = true;
                }
                elements.set(id, element);
            }
            return elements.get(id);
        },
        createElement() {
            return new Element();
        }
    };

    class Chart {
        constructor(canvas, config) {
            this.canvas = canvas;
            this.config = config;
            this.updateCount = 0;
            charts.push(this);
        }

        update() {
            this.updateCount++;
        }
    }

    const context = {
        document,
        console: {
            error(...args) {
                consoleErrors.push(args);
            }
        },
        Date,
        Math,
        Number,
        Object,
        String,
        Array,
        setInterval(callback, delay) {
            scheduledIntervals.push({ callback, delay });
        },
        setTimeout(callback, delay) {
            scheduledTimeouts.push({ callback, delay });
        },
        fetch: fetchImpl || (async () => response || {
            ok: true,
            status: 200,
            json: async () => samplePatient
        })
    };

    if (includeChart) {
        context.Chart = Chart;
    }

    vm.createContext(context);
    vm.runInContext(script, context);

    return {
        context,
        elements,
        charts,
        scheduledTimeouts,
        scheduledIntervals,
        consoleErrors,
        async settle() {
            await new Promise(resolve => setImmediate(resolve));
        }
    };
}

test("successful updates render measurements, statistics, charts, and one risk log", async () => {
    const dashboard = createDashboard();
    await dashboard.settle();

    assert.equal(dashboard.elements.get("hr").innerText, 112);
    assert.equal(dashboard.elements.get("spo2").innerText, 89);
    assert.equal(dashboard.elements.get("avg_temp").innerText, "101.2°F");
    assert.equal(dashboard.elements.get("max_hr").innerText, 112);
    assert.equal(dashboard.elements.get("min_spo2").innerText, "89%");
    assert.equal(dashboard.context.document.getElementById("allergies").innerText, "Penicillin");
    assert.equal(dashboard.elements.get("dashboardError").hidden, true);
    assert.equal(dashboard.elements.get("alertBanner").style.display, "flex");
    assert.equal(dashboard.elements.get("activityLog").children.length, 1);
    assert.equal(dashboard.charts.length, 3);
    assert.equal(dashboard.charts.every(chart => chart.updateCount === 1), true);
    assert.equal(dashboard.scheduledTimeouts.length, 1);
    assert.equal(dashboard.scheduledTimeouts[0].delay, 2000);

    dashboard.scheduledTimeouts[0].callback();
    await dashboard.settle();
    assert.equal(dashboard.elements.get("activityLog").children.length, 1);

    dashboard.scheduledIntervals.at(-1).callback();
    assert.equal(dashboard.context.document.getElementById("monitor_time").innerText, "00:00:01");
});

test("failed requests show a controlled error and keep empty statistics finite", async () => {
    const dashboard = createDashboard({
        response: {
            ok: false,
            status: 503,
            json: async () => ({ error: "unavailable" })
        },
        canvases: false,
        includeChart: false
    });
    await dashboard.settle();

    assert.equal(dashboard.elements.get("dashboardError").hidden, false);
    assert.match(dashboard.elements.get("dashboardError").innerText, /may be out of date/);
    assert.equal(dashboard.context.document.getElementById("max_hr").innerText, "--");
    assert.equal(dashboard.context.document.getElementById("min_spo2").innerText, "--");
    assert.equal(dashboard.context.document.getElementById("avg_temp").innerText, "--");
    assert.equal(dashboard.charts.length, 0);
    assert.equal(dashboard.consoleErrors.length, 1);
    assert.equal(dashboard.scheduledTimeouts.length, 1);
});

test("invalid responses display an error instead of rendering missing values", async () => {
    const dashboard = createDashboard({
        response: {
            ok: true,
            status: 200,
            json: async () => ({ hr: null })
        }
    });
    await dashboard.settle();

    assert.equal(dashboard.elements.get("dashboardError").hidden, false);
    assert.equal(dashboard.context.document.getElementById("hr").innerText, "--");
    assert.equal(dashboard.context.document.getElementById("avg_temp").innerText, "--");
});

test("overlapping refresh calls are ignored while a request is in flight", async () => {
    let resolveResponse;
    let fetchCount = 0;
    const dashboard = createDashboard({
        fetchImpl() {
            fetchCount++;
            return new Promise(resolve => {
                resolveResponse = resolve;
            });
        }
    });

    vm.runInContext("updateDashboard()", dashboard.context);
    assert.equal(fetchCount, 1);

    await vm.runInContext("updateDashboard()", dashboard.context);
    assert.equal(fetchCount, 1);

    resolveResponse({
        ok: true,
        status: 200,
        json: async () => samplePatient
    });
    await dashboard.settle();
    assert.equal(dashboard.elements.get("hr").innerText, 112);
});
