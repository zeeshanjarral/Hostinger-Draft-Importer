let rows = [];
let lastResults = [];

const $ = (id) => document.getElementById(id);

function showNotice(message, type) {
  const el = $("validation");
  el.textContent = message;
  el.className = "notice " + type;
}

function hideNotice() {
  $("validation").className = "notice hidden";
}

function setConnection(message, ok = null) {
  const el = $("connectionResult");
  el.textContent = message;
  el.className = "status-text" + (ok === true ? " ok" : ok === false ? " bad" : "");
}

function validateRows(data) {
  const issues = [];
  const required = ["To", "Subject", "Body"];

  if (!data.length) {
    issues.push("The worksheet is empty.");
    return issues;
  }

  for (const name of required) {
    if (!(name in data[0])) {
      issues.push(`Missing required column: ${name}`);
    }
  }
  if (issues.length) return issues;

  data.forEach((row, i) => {
    if (!String(row.To ?? "").trim()) issues.push(`Row ${i + 2}: To is empty.`);
    if (!String(row.Subject ?? "").trim()) issues.push(`Row ${i + 2}: Subject is empty.`);
    if (!String(row.Body ?? "").trim()) issues.push(`Row ${i + 2}: Body is empty.`);
  });

  return issues;
}

function renderPreview() {
  const table = $("previewTable");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");

  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (!rows.length) return;

  const columns = Object.keys(rows[0]);
  const trh = document.createElement("tr");
  columns.forEach(c => {
    const th = document.createElement("th");
    th.textContent = c;
    trh.appendChild(th);
  });
  thead.appendChild(trh);

  rows.slice(0, 25).forEach(row => {
    const tr = document.createElement("tr");
    columns.forEach(c => {
      const td = document.createElement("td");
      td.textContent = row[c] ?? "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function renderResults(results) {
  const table = $("resultsTable");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");

  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (!results.length) return;

  const columns = ["row", "to", "subject", "status", "error"];
  const labels = ["Excel Row", "To", "Subject", "Status", "Error"];

  const trh = document.createElement("tr");
  labels.forEach(label => {
    const th = document.createElement("th");
    th.textContent = label;
    trh.appendChild(th);
  });
  thead.appendChild(trh);

  results.forEach(r => {
    const tr = document.createElement("tr");
    columns.forEach(c => {
      const td = document.createElement("td");
      td.textContent = r[c] ?? "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

$("includeSignature").addEventListener("change", () => {
  $("signaturePreview").style.opacity = $("includeSignature").checked ? "1" : ".35";
});

$("fileInput").addEventListener("change", async (e) => {
  hideNotice();
  rows = [];
  renderPreview();

  const file = e.target.files?.[0];
  if (!file) {
    $("fileMeta").textContent = "No file selected.";
    return;
  }

  $("fileMeta").textContent = `${file.name} — reading…`;

  try {
    const buffer = await file.arrayBuffer();
    const workbook = XLSX.read(buffer, { type: "array" });
    const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
    rows = XLSX.utils.sheet_to_json(firstSheet, { defval: "" });

    $("fileMeta").textContent = `${file.name} — ${rows.length} row(s) detected`;
    renderPreview();

    const issues = validateRows(rows);
    if (issues.length) {
      showNotice(issues.slice(0, 30).join("\n"), "error");
    } else {
      showNotice("Excel file looks ready.", "success");
    }
  } catch (err) {
    showNotice(`Could not read Excel file: ${err.message || err}`, "error");
  }
});

$("testBtn").addEventListener("click", async () => {
  const email = $("email").value.trim();
  const password = $("password").value;

  if (!email || !password) {
    setConnection("Enter email and mailbox password first.", false);
    return;
  }

  setConnection("Testing…");

  try {
    const res = await fetch("/api/test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password })
    });

    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "Connection failed.");

    setConnection(`Connected. Drafts folder: ${data.draftsFolder}`, true);
  } catch (err) {
    setConnection(err.message || String(err), false);
  }
});

$("confirm").addEventListener("change", () => {
  $("importBtn").disabled = !$("confirm").checked;
});

$("importBtn").addEventListener("click", async () => {
  const email = $("email").value.trim();
  const password = $("password").value;

  if (!email || !password) {
    alert("Enter your Hostinger email and mailbox password.");
    return;
  }

  const issues = validateRows(rows);
  if (issues.length) {
    showNotice(issues.slice(0, 30).join("\n"), "error");
    return;
  }

  $("importBtn").disabled = true;
  $("progressWrap").classList.remove("hidden");
  $("summary").classList.add("hidden");
  $("progressBar").style.width = "30%";
  $("progressText").textContent = `Uploading ${rows.length} row(s) to the Worker…`;

  try {
    const res = await fetch("/api/import", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        includeSignature: $("includeSignature").checked,
        rows
      })
    });

    $("progressBar").style.width = "85%";
    $("progressText").textContent = "Finalizing results…";

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Import failed.");

    lastResults = data.results || [];
    renderResults(lastResults);

    const created = lastResults.filter(x => x.status === "Created").length;
    const failed = lastResults.filter(x => x.status === "Failed").length;

    $("progressBar").style.width = "100%";
    $("progressText").textContent = "Finished.";

    const summary = $("summary");
    summary.textContent =
      `Drafts folder: ${data.draftsFolder} — ${created} created, ${failed} failed.`;
    summary.classList.remove("hidden");

  } catch (err) {
    $("progressBar").style.width = "100%";
    $("progressText").textContent = "Failed.";
    const summary = $("summary");
    summary.textContent = err.message || String(err);
    summary.classList.remove("hidden");
  } finally {
    $("importBtn").disabled = !$("confirm").checked;
  }
});
