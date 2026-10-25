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
    status: "Demo High Pattern — Review",
    health_score: 20,
    reasons: ["Critical oxygen level"],
    recommendation: "Demo guidance",
    risk_assessment: {
        risk: "High",
        severity: "high",
        status: "Demo High Pattern — Review",
        method: "deterministic_demo_rules",
        factors: [{
            code: "spo2_demo_high",
            label: "Critical oxygen level",
            observed_value: 89,
            threshold: 92,
            unit: "%",
            affects_risk: true
        }],
        next_step: "Demo guidance",
        data_quality: { status: "complete" },
        threshold_source: "inherited_demo_configuration_not_clinical_guidance",
        clinically_validated: false
    },
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

function getRequestedPatientId(url, options) {
    if (options && options.body) {
        return JSON.parse(options.body).patient_id;
    }
    return new URL(url, "http://localhost").searchParams.get("patient_id");
}

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
        status: "No Demo Threshold Flagged",
        health_score: 100,
        reasons: [],
        recommendation: "Demo guidance",
        risk_assessment: {
            ...samplePatient.risk_assessment,
            risk: "Low",
            severity: "low",
            status: "No Demo Threshold Flagged",
            factors: []
        },
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
    const requests = [];

    const document = {
        querySelector(selector) {
            return selector === 'meta[name="csrf-token"]'
                ? { content: "test-csrf-token" }
                : null;
        },
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
        fetch: async (url, options) => {
            requests.push({ url, options });
            if (url === "/patients") {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ patients: samplePatients })
                };
            }
            if (fetchImpl) {
                return fetchImpl(url, options);
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
        requests,
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
    const advanceRequest = dashboard.requests.find(
        request => request.url === "/patient/advance"
    );
    assert.equal(advanceRequest.options.method, "POST");
    assert.equal(advanceRequest.options.headers["X-CSRF-Token"], "test-csrf-token");
    assert.deepEqual(
        JSON.parse(advanceRequest.options.body),
        { patient_id: "P001" }
    );
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
    assert.equal(dashboard.elements.get("risk").innerText, "Unavailable");
    assert.equal(dashboard.elements.get("status").innerText, "Assessment Unavailable");
    assert.equal(dashboard.context.document.getElementById("max_hr").innerText, "--");
    assert.equal(dashboard.context.document.getElementById("min_spo2").innerText, "--");
    assert.equal(dashboard.context.document.getElementById("avg_temp").innerText, "--");
    assert.equal(dashboard.charts.length, 0);
    assert.equal(dashboard.consoleErrors.length, 1);
    assert.equal(dashboard.scheduledTimeouts.length, 1);
});

test("a failed refresh does not leave a prior low assessment visible", async () => {
    let failRequest = false;
    const dashboard = createDashboard({
        fetchImpl: async () => {
            if (failRequest) {
                return {
                    ok: false,
                    status: 503,
                    json: async () => ({ error: "unavailable" })
                };
            }
            return {
                ok: true,
                status: 200,
                json: async () => patientResponse("P002")
            };
        }
    });
    await dashboard.settle();
    const selector = dashboard.context.document.getElementById("patientSelector");
    selector.value = "P002";
    selector.dispatch("change");
    await dashboard.settle();
    assert.equal(dashboard.elements.get("risk").innerText, "Low");

    failRequest = true;
    await vm.runInContext("updateDashboard()", dashboard.context);
    await dashboard.settle();

    assert.equal(dashboard.elements.get("risk").innerText, "Unavailable");
    assert.equal(dashboard.elements.get("status").innerText, "Assessment Unavailable");
    assert.equal(dashboard.elements.get("hr").innerText, "--");
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

test("unavailable assessment clears stale measurements and explains invalid data", async () => {
    const dashboard = createDashboard({
        response: {
            ok: false,
            status: 422,
            json: async () => ({
                error: "SpO2 must be between 0 and 100 percent.",
                risk_assessment: {
                    risk: "Unavailable",
                    severity: "unknown",
                    status: "Assessment Unavailable",
                    method: "deterministic_demo_rules",
                    factors: [{
                        code: "data_quality",
                        label: "SpO2 must be between 0 and 100 percent.",
                        observed_value: null,
                        threshold: null,
                        unit: null,
                        affects_risk: true
                    }],
                    next_step: "Check the measurements.",
                    data_quality: { status: "incomplete_or_invalid" },
                    threshold_source: "inherited_demo_configuration_not_clinical_guidance",
                    clinically_validated: false
                }
            })
        }
    });
    await dashboard.settle();

    assert.equal(dashboard.elements.get("risk").innerText, "Unavailable");
    assert.equal(dashboard.elements.get("status").innerText, "Assessment Unavailable");
    assert.equal(dashboard.elements.get("hr").innerText, "--");
    assert.equal(dashboard.elements.get("spo2").innerText, "--");
    assert.equal(dashboard.elements.get("dashboardError").hidden, false);
    assert.match(dashboard.elements.get("dashboardError").innerText, /SpO2 must be between/);
    assert.equal(dashboard.elements.get("alertBanner").style.display, "none");
    assert.deepEqual(Array.from(dashboard.charts[0].data.datasets[0].data), []);
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
        fetchImpl: async (url, options) => {
            const patientId = getRequestedPatientId(url, options);
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
        fetchImpl: (url, options) => {
            const patientId = getRequestedPatientId(url, options);
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

test("stale failed patient response cannot mark a newly selected patient unavailable", async () => {
    let rejectP001;
    const dashboard = createDashboard({
        fetchImpl: (url, options) => {
            const patientId = getRequestedPatientId(url, options);
            if (patientId === "P001") {
                return new Promise((resolve, reject) => {
                    rejectP001 = reject;
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
    rejectP001(new Error("stale request failed"));
    await dashboard.settle();

    assert.equal(dashboard.elements.get("status").innerText, "--");
    assert.equal(dashboard.elements.get("risk").innerText, "--");
    dashboard.scheduledTimeouts.at(-1).callback();
    await dashboard.settle();
    assert.equal(dashboard.elements.get("patient_id").innerText, "P002");
    assert.equal(dashboard.elements.get("risk").innerText, "Low");
});
