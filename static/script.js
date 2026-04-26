async function loadData() {
    const res = await fetch('/patient');
    const data = await res.json();

    document.getElementById("hr").innerText = data.hr;
    document.getElementById("spo2").innerText = data.spo2;
    document.getElementById("temp").innerText = data.temp;
    document.getElementById("risk").innerText = data.risk;
    document.getElementById("reason").innerText = data.reasons.join(", ");

    let risk = document.getElementById("risk");

    if (data.risk === "Low") risk.style.color = "lightgreen";
    else if (data.risk === "Medium") risk.style.color = "yellow";
    else risk.style.color = "red";
}

setInterval(loadData, 2000);
loadData();