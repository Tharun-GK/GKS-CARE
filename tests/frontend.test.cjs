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

const samplePatients = [
    { patient_id: "P001", age: 45, gender: "Male", data_source: "synthetic_demo" },
    { patient_id: "P002", age: 37, gender: "Female", data_source: "synthetic_demo" },
    { patient_id: "P003", age: 62, gender: "Male", data_source: "synthetic_demo" }
];

function patientResponse(patientId) {
    if (patientId === "P001") {
        return samplePatient;
    }

    const isModerate = patientId === "P002";
    const hr = isModerate ? 85 : 78;
    const spo2 = isModerate ? 96 : 98;
    const temp = isModerate ? 98.6 : 98.4;
    return {
        ...samplePatient,
        patient_id: patientId,
        age: isModerate ? 37 : 62,
        gender: isModerate ? "Female" : "Male",
        hr,
        spo2,
        temp,
        bp: "120/80",
        risk: "Low",
        status: "Stable",
        health_score: 100,
        reasons: [],
        recommendation: "Demo guidance",
        observations: [{
            ...samplePatient.observations[0],
            id: isModerate ? 2 : 3,
            hr,
            spo2,
            temp
        }],
        medical_history: [{
            ...samplePatient.medical_history[0],
            value: isModerate ? "None recorded in demo" : "Latex (demo)"
        }]
    };
}

function createDashboard({ response, canvases = true, includeChart = true, fetchImpl } = {}) {
    class Element {
        constructor() {
            this.innerText = "--";
            this.hidden = false;
            this.style = {};
            this.children = [];
            this.listeners = {};
            this.value = "";
            this.disabled = false;
        }

        get lastChild() {
            return this.children[this.children.length - 1];
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

        addEventListener(eventName, callback) {
            this.listeners[eventName] = callback;
        }

        dispatch(eventName) {
            if (this.listeners[eventName]) {
                this.listeners[eventName]();
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
            this.data = config.data;
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
        fetch: async url => {
            if (url === "/patients") {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ patients: samplePatients })
                };
            }
            if (fetchImpl) {
                return fetchImpl(url);
            }
            return response || {
                ok: true,
                status: 200,
                json: async () => patientResponse("P001")
            };
        }
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
            for (let turn = 0; turn < 4; turn++) {
                await new Promise(resolve => setImmediate(resolve));
            }
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
        fetchImpl(url) {
            if (url === "/patients") {
                return Promise.resolve({
                    ok: true,
                    status: 200,
                    json: async () => ({ patients: samplePatients })
                });
            }
            fetchCount++;
            return new Promise(resolve => {
                resolveResponse = resolve;
            });
        }
    });

    await dashboard.settle();
    assert.equal(fetchCount, 1);

    await vm.runInContext("updateDashboard()", dashboard.context);
    assert.equal(fetchCount, 1);

    resolveResponse({
        ok: true,
        status: 200,
        json: async () => patientResponse("P001")
    });
    await dashboard.settle();
    assert.equal(dashboard.elements.get("hr").innerText, 112);
});

test("changing patient clears prior data and loads isolated patient metrics/history", async () => {
    const dashboard = createDashboard({
        fetchImpl: async url => {
            const patientId = new URL(url, "http://localhost").searchParams.get("patient_id");
            return {
                ok: true,
                status: 200,
                json: async () => patientResponse(patientId)
            };
        }
    });
    await dashboard.settle();

    const selector = dashboard.context.document.getElementById("patientSelector");
    assert.equal(selector.children.length, 3);
    assert.equal(selector.disabled, false);
    assert.equal(dashboard.elements.get("hr").innerText, 112);

    selector.value = "P002";
    selector.dispatch("change");
    assert.equal(dashboard.elements.get("hr").innerText, "--");
    await dashboard.settle();

    assert.equal(dashboard.elements.get("patient_id").innerText, "P002");
    assert.equal(dashboard.elements.get("hr").innerText, 85);
    assert.equal(dashboard.elements.get("spo2").innerText, 96);
    assert.equal(dashboard.elements.get("allergies").innerText, "None recorded in demo");
    assert.deepEqual(Array.from(dashboard.charts[0].data.datasets[0].data), [85]);
});

test("stale patient response cannot overwrite a newly selected patient", async () => {
    let resolveP001;
    const dashboard = createDashboard({
        fetchImpl: url => {
            const patientId = new URL(url, "http://localhost").searchParams.get("patient_id");
            if (patientId === "P001") {
                return new Promise(resolve => {
                    resolveP001 = resolve;
                });
            }
            return Promise.resolve({
                ok: true,
                status: 200,
                json: async () => patientResponse(patientId)
            });
        }
    });
    await dashboard.settle();

    const selector = dashboard.context.document.getElementById("patientSelector");
    selector.value = "P002";
    selector.dispatch("change");
    resolveP001({
        ok: true,
        status: 200,
        json: async () => patientResponse("P001")
    });
    await dashboard.settle();

    assert.equal(dashboard.elements.get("patient_id").innerText, "--");
    const pendingRefresh = dashboard.scheduledTimeouts.at(-1);
    pendingRefresh.callback();
    await dashboard.settle();
    assert.equal(dashboard.elements.get("patient_id").innerText, "P002");
    assert.equal(dashboard.elements.get("hr").innerText, 85);
});
