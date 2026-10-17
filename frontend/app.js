const USE_MOCK = true;

/* DisasterBridge-AI frontend logic. Plain JavaScript, no build step.
   When USE_MOCK is true, every API call is answered by the synthetic mock
   below. Set it to false once the Flask backend serves /api/*. */

const PIN_KEY = "db_auth_pin";

const STATUS_LABELS = {
  searching: "Searching",
  under_review: "Possible match under review",
  reunited: "Reunited",
};

/* ---------- Small DOM helpers (never inject user text as HTML) ---------- */

function $(sel, root) { return (root || document).querySelector(sel); }

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
  }
  for (const c of [].concat(children || [])) {
    if (c === null || c === undefined) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function showMessage(box, kind, content) {
  box.className = "message " + kind;
  box.replaceChildren(...[].concat(content));
  box.focus();
}

function clearMessage(box) {
  box.className = "message";
  box.replaceChildren();
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function statusPill(status, big) {
  return el("span", {
    class: "status-pill status-" + status + (big ? " status-big" : ""),
    text: STATUS_LABELS[status] || status,
  });
}

/* ---------- API helper ---------- */

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

function getPin() {
  try { return sessionStorage.getItem(PIN_KEY) || ""; } catch (e) { return ""; }
}
function setPin(pin) {
  try { sessionStorage.setItem(PIN_KEY, pin); } catch (e) { /* ignore */ }
}
function clearPin() {
  try { sessionStorage.removeItem(PIN_KEY); } catch (e) { /* ignore */ }
}

async function api(method, path, body, opts) {
  const auth = opts && opts.auth;
  if (USE_MOCK) return mockApi(method, path, body, auth ? getPin() : null);

  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) headers["X-Auth-Pin"] = getPin();

  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError("We could not reach the server. Please check your connection and try again.", 0);
  }

  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON body */ }

  if (!res.ok) {
    const msg = (data && data.error) || "Something went wrong (error " + res.status + "). Please try again.";
    throw new ApiError(msg, res.status);
  }
  return data;
}

/* ---------- Mock backend (synthetic data only) ---------- */

const MOCK_KEY = "db_mock_state_v1";

function mockSeed() {
  return {
    nextMissing: 13,
    nextFound: 8,
    missing: {
      M10: {
        age_min: 6, age_max: 9, gender: "male", height_cm: 125,
        hair: "brown, short", clothing: "green school uniform",
        marks: "glasses with blue frames", last_seen_place: "North Primary School",
        last_seen_time: "2026-10-16T14:15",
        description: "Was waiting for the school bus when the water rose.",
        contact: "555-0101", status: "searching",
      },
      M11: {
        age_min: 70, age_max: 78, gender: "female", height_cm: 155,
        hair: "grey, tied back", clothing: "purple cardigan",
        marks: "uses a walking stick", last_seen_place: "Elm Street flats",
        last_seen_time: "2026-10-16T09:30",
        description: "Lives alone on the ground floor. May be confused.",
        contact: "555-0102", status: "searching",
      },
      M12: {
        age_min: 28, age_max: 34, gender: "female", height_cm: 165,
        hair: "black, shoulder length", clothing: "red jacket, jeans",
        marks: "scar above left eyebrow", last_seen_place: "Riverside Market",
        last_seen_time: "2026-10-16T18:00",
        description: "Last seen heading towards the bridge.",
        contact: "555-0100", status: "searching",
      },
    },
    found: {
      F5: {
        age_min: 65, age_max: 80, gender: "female", height_cm: 152,
        hair: "grey", clothing: "purple cardigan, slippers",
        marks: "walking stick", found_place: "Elm Street bus shelter",
        found_time: "2026-10-16T16:40", current_location: "General Hospital, Ward 3",
        description: "Disoriented, could not give her name.",
      },
      F6: {
        age_min: 25, age_max: 32, gender: "female", height_cm: 170,
        hair: "black, long", clothing: "grey hoodie",
        marks: "", found_place: "Station Square",
        found_time: "2026-10-16T22:00", current_location: "City Shelter 1",
        description: "Minor cuts, speaking normally.",
      },
      F7: {
        age_min: 30, age_max: 36, gender: "female", height_cm: 166,
        hair: "black", clothing: "blue coat",
        marks: "scar on forehead", found_place: "Bridge Road",
        found_time: "2026-10-17T00:10", current_location: "City Shelter 2",
        description: "Found near the bridge, wrapped in a borrowed coat.",
      },
    },
    rejected: {},   // { M12: ["F6"] }
    confirmed: {},  // { M12: "F7" }
    // Hand-written reasons from the team brief for the headline demo pair.
    canned: {
      "M12|F7": {
        score: 87,
        reasons: [
          { label: "Age ranges overlap", matched: true },
          { label: "Gender matches", matched: true },
          { label: "Scar above left eyebrow mentioned in both", matched: true },
          { label: "Clothing differs (red jacket vs blue coat)", matched: false },
          { label: "Found 4 km from last seen, 6 hours later", matched: true },
        ],
      },
    },
  };
}

let mockState = null;

function mockLoad() {
  if (mockState) return mockState;
  try {
    const raw = localStorage.getItem(MOCK_KEY);
    if (raw) mockState = JSON.parse(raw);
  } catch (e) { /* storage unavailable */ }
  if (!mockState) mockState = mockSeed();
  return mockState;
}

function mockSave() {
  try { localStorage.setItem(MOCK_KEY, JSON.stringify(mockState)); } catch (e) { /* ignore */ }
}

function mockReset() {
  mockState = mockSeed();
  mockSave();
}

const STOP_WORDS = new Set(["the", "and", "with", "a", "an", "of", "on", "in", "above", "below", "left", "right"]);
function words(s) {
  return new Set(String(s || "").toLowerCase().split(/[^a-z]+/).filter(w => w.length > 2 && !STOP_WORDS.has(w)));
}
function shared(a, b) {
  const wb = words(b);
  return [...words(a)].filter(w => wb.has(w));
}

// Toy stand-in for the real matching engine. Results are synthetic.
function mockScore(m, f) {
  const reasons = [];
  let score = 0;

  const ageOk = m.age_min <= f.age_max && f.age_min <= m.age_max;
  reasons.push({ label: ageOk ? "Age ranges overlap" : "Age ranges do not overlap", matched: ageOk });
  if (ageOk) score += 30;

  const unknown = m.gender === "unknown" || f.gender === "unknown";
  const genderOk = m.gender === f.gender || unknown;
  reasons.push({ label: genderOk ? (unknown ? "Gender not ruled out" : "Gender matches") : "Gender differs", matched: genderOk });
  if (genderOk) score += unknown ? 10 : 20;

  if (m.height_cm && f.height_cm) {
    const diff = Math.abs(m.height_cm - f.height_cm);
    const ok = diff <= 8;
    reasons.push({ label: ok ? "Height similar (" + diff + " cm apart)" : "Height differs by " + diff + " cm", matched: ok });
    if (ok) score += 10;
  }

  if (m.marks && f.marks) {
    const common = shared(m.marks, f.marks);
    const ok = common.length > 0;
    reasons.push({ label: ok ? "Marks mention \"" + common.join(", ") + "\" in both" : "Marks differ", matched: ok });
    if (ok) score += 20;
  }

  if (m.clothing && f.clothing) {
    const common = shared(m.clothing, f.clothing);
    const ok = common.length > 0;
    reasons.push({
      label: ok ? "Clothing similar (" + common.join(", ") + ")" : "Clothing differs (" + m.clothing + " vs " + f.clothing + ")",
      matched: ok,
    });
    if (ok) score += 15;
  }

  const after = new Date(f.found_time) >= new Date(m.last_seen_time);
  reasons.push({ label: after ? "Found after last seen" : "Found before last seen time", matched: after });
  if (after) score += 5;

  return { score: Math.min(100, score), reasons };
}

function mockCandidates(state, mid) {
  const m = state.missing[mid];
  const rejected = state.rejected[mid] || [];
  const takenFound = new Set(Object.values(state.confirmed));
  const list = [];
  for (const [fid, f] of Object.entries(state.found)) {
    if (rejected.includes(fid)) continue;
    if (takenFound.has(fid) && state.confirmed[mid] !== fid) continue;
    const r = state.canned[mid + "|" + fid] || mockScore(m, f);
    if (r.score < 40) continue;
    list.push({ found_id: fid, score: r.score, reasons: r.reasons, found: f });
  }
  return list.sort((a, b) => b.score - a.score);
}

function mockStatus(state, mid) {
  if (state.confirmed[mid]) return "reunited";
  return mockCandidates(state, mid).some(c => c.score >= 60) ? "under_review" : "searching";
}

function summarize(r) {
  const age = r.age_min === r.age_max ? r.age_min : r.age_min + "–" + r.age_max;
  return [r.gender, "age " + age, r.clothing, r.last_seen_place && "last seen " + r.last_seen_place]
    .filter(Boolean).join(", ");
}

async function mockApi(method, path, body, pin) {
  await new Promise(r => setTimeout(r, 250)); // feel like a network call
  const state = mockLoad();
  const fail = (status, error) => { throw new ApiError(error, status); };
  const needAuth = () => { if (!pin) fail(401, "Access code required."); };
  let m;

  if (method === "POST" && path === "/api/missing") {
    const id = "M" + state.nextMissing++;
    state.missing[id] = Object.assign({}, body, { status: "searching" });
    mockSave();
    return { id, status: "searching" };
  }

  if (method === "GET" && (m = path.match(/^\/api\/status\/([^/]+)$/))) {
    const id = decodeURIComponent(m[1]).trim().toUpperCase();
    if (!state.missing[id]) fail(404, "We could not find a report with that number.");
    return { id, status: mockStatus(state, id) };
  }

  if (method === "POST" && path === "/api/found") {
    needAuth();
    const id = "F" + state.nextFound++;
    state.found[id] = Object.assign({}, body);
    mockSave();
    return { id };
  }

  if (method === "GET" && path === "/api/missing") {
    needAuth();
    return Object.entries(state.missing).map(([id, r]) =>
      Object.assign({}, r, { id, status: mockStatus(state, id), summary: summarize(r) }));
  }

  if (method === "GET" && (m = path.match(/^\/api\/matches\/([^/]+)$/))) {
    needAuth();
    const id = decodeURIComponent(m[1]);
    if (!state.missing[id]) fail(404, "Report not found.");
    return { missing_id: id, candidates: mockCandidates(state, id) };
  }

  if (method === "POST" && (m = path.match(/^\/api\/matches\/([^/]+)\/decision$/))) {
    needAuth();
    const id = decodeURIComponent(m[1]);
    if (!state.missing[id]) fail(404, "Report not found.");
    if (!body || !state.found[body.found_id]) fail(400, "Unknown found_id.");
    if (body.decision === "confirm") state.confirmed[id] = body.found_id;
    else if (body.decision === "reject") {
      (state.rejected[id] = state.rejected[id] || []).push(body.found_id);
      if (state.confirmed[id] === body.found_id) delete state.confirmed[id];
    } else fail(400, "decision must be \"confirm\" or \"reject\".");
    mockSave();
    return { missing_id: id, found_id: body.found_id, decision: body.decision, status: mockStatus(state, id) };
  }

  if (method === "GET" && path === "/api/benchmark") {
    return {
      chip_on: { pairs_per_sec: 120000, seconds: 1.4 },
      chip_off: { pairs_per_sec: 45000, seconds: 3.7 },
      note: "ILLUSTRATIVE PLACEHOLDER — not measured results",
    };
  }

  fail(404, "Unknown endpoint " + method + " " + path);
}

/* ---------- Form helpers ---------- */

function readForm(form, fields) {
  const out = {};
  for (const name of fields) {
    const input = form.elements[name];
    if (!input) continue;
    const v = input.value.trim();
    if (input.type === "number") {
      if (v !== "") out[name] = Number(v);
    } else if (v !== "") {
      out[name] = v;
    }
  }
  return out;
}

function setFieldError(form, name, msg) {
  const input = form.elements[name];
  const box = $("#" + input.id + "-error", form);
  if (msg) input.setAttribute("aria-invalid", "true");
  else input.removeAttribute("aria-invalid");
  if (box) box.textContent = msg || "";
}

// Validates a person record. `required` lists required field names.
function validatePerson(form, data, required, labels) {
  const errors = [];
  const add = (name, msg) => { errors.push({ name, msg }); setFieldError(form, name, msg); };

  for (const input of form.querySelectorAll("[aria-invalid]")) setFieldError(form, input.name, "");

  for (const name of required) {
    if (data[name] === undefined) add(name, "Please fill in " + labels[name].toLowerCase() + ".");
  }
  for (const name of ["age_min", "age_max"]) {
    const v = data[name];
    if (v !== undefined && (!Number.isInteger(v) || v < 0 || v > 120)) {
      add(name, labels[name] + " must be a whole number from 0 to 120.");
    }
  }
  if (Number.isInteger(data.age_min) && Number.isInteger(data.age_max) && data.age_min > data.age_max &&
      !errors.some(e => e.name === "age_max")) {
    add("age_max", "Highest age must be the same as or more than the lowest age.");
  }
  if (data.height_cm !== undefined && (isNaN(data.height_cm) || data.height_cm < 30 || data.height_cm > 250)) {
    add("height_cm", "Height should be between 30 and 250 cm, or left empty.");
  }
  return errors;
}

function errorSummary(form, errors) {
  return [
    el("strong", { text: "Please check " + (errors.length === 1 ? "1 thing" : errors.length + " things") + ":" }),
    el("ul", null, errors.map(e => el("li", null, [
      el("a", { href: "#" + form.elements[e.name].id, onclick: ev => { ev.preventDefault(); form.elements[e.name].focus(); }, text: e.msg }),
    ]))),
  ];
}

async function withBusy(button, fn) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Please wait…";
  try { return await fn(); } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function markMockMode() {
  const slot = $("#mock-indicator");
  if (slot && USE_MOCK) {
    slot.replaceChildren(el("span", { class: "mock-note", text: "Demo mode: showing synthetic sample responses, no server connected." }));
  }
}

/* ---------- Family page ---------- */

const PERSON_LABELS = {
  age_min: "Lowest age", age_max: "Highest age", gender: "Gender", height_cm: "Height",
  hair: "Hair", clothing: "Clothing", marks: "Distinguishing marks",
  last_seen_place: "Where they were last seen", last_seen_time: "When they were last seen",
  found_place: "Where found", found_time: "When found", current_location: "Current location",
  description: "Description", contact: "Your contact details",
};

function initFamily() {
  const form = $("#missing-form");
  const msg = $("#missing-message");
  const fields = ["age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
    "last_seen_place", "last_seen_time", "description", "contact"];
  const required = ["age_min", "age_max", "gender", "last_seen_place", "last_seen_time", "description", "contact"];

  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(msg);
    const data = readForm(form, fields);
    const errors = validatePerson(form, data, required, PERSON_LABELS);
    if (errors.length) { showMessage(msg, "error", errorSummary(form, errors)); return; }

    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await api("POST", "/api/missing", data);
        form.reset();
        showMessage(msg, "success", [
          el("strong", { text: "Your report has been received." }),
          el("p", { text: "Your report number is:" }),
          el("span", { class: "report-id", text: res.id }),
          el("p", null, [el("strong", { text: "Save this number." }), " You will need it to check the status of your report."]),
        ]);
        $("#status-id").value = res.id;
      } catch (e) {
        showMessage(msg, "error", e.message);
      }
    });
  });

  const sForm = $("#status-form");
  const sMsg = $("#status-message");
  sForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(sMsg);
    const id = sForm.elements.report_id.value.trim().toUpperCase();
    if (!id) {
      setFieldError(sForm, "report_id", "Please enter your report number.");
      showMessage(sMsg, "error", "Please enter your report number.");
      return;
    }
    setFieldError(sForm, "report_id", "");
    await withBusy(sForm.querySelector("button[type=submit]"), async () => {
      try {
        const res = await api("GET", "/api/status/" + encodeURIComponent(id));
        const explain = {
          searching: "We are still looking. New information is checked as it arrives.",
          under_review: "A trained person is checking a possible match. You will be contacted if it is confirmed.",
          reunited: "This report has been confirmed as a match. Officials will contact you with details.",
        };
        showMessage(sMsg, "", [
          el("p", { text: "Report " + res.id + ":" }),
          statusPill(res.status, true),
          el("p", { text: explain[res.status] || "" }),
        ]);
      } catch (e) {
        showMessage(sMsg, "error", e.status === 404 ? "We could not find a report with that number. Please check it and try again." : e.message);
      }
    });
  });
}

/* ---------- Authority page ---------- */

function initAuthority() {
  const gate = $("#pin-gate");
  const dash = $("#dashboard");
  const pinForm = $("#pin-form");
  const pinMsg = $("#pin-message");
  let reports = [];
  let selected = null;

  function lock(message) {
    clearPin();
    dash.classList.add("hidden");
    gate.classList.remove("hidden");
    if (message) showMessage(pinMsg, "error", message);
    pinForm.elements.pin.focus();
  }

  async function guarded(fn, box) {
    try { return await fn(); } catch (e) {
      if (e.status === 401 || e.status === 403) lock("That access code was not accepted. Please enter it again.");
      else if (box) showMessage(box, "error", e.message);
      throw e;
    }
  }

  pinForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    const pin = pinForm.elements.pin.value.trim();
    if (!pin) { showMessage(pinMsg, "error", "Please enter the access code."); return; }
    setPin(pin);
    pinForm.reset();
    clearMessage(pinMsg);
    await unlock();
  });

  $("#lock-button").addEventListener("click", () => lock());

  async function unlock() {
    try { await loadReports(); } catch (e) { return; }
    gate.classList.add("hidden");
    dash.classList.remove("hidden");
    $("#dash-heading").focus();
  }

  async function loadReports() {
    const box = $("#reports-message");
    clearMessage(box);
    reports = await guarded(() => api("GET", "/api/missing", undefined, { auth: true }), box);
    renderReports();
  }

  function renderReports() {
    const body = $("#reports-body");
    body.replaceChildren(...reports.map(r => el("tr", { class: r.id === selected ? "selected" : null }, [
      el("td", null, [el("button", {
        class: "link", text: r.id,
        "aria-label": "Review matches for report " + r.id,
        onclick: () => openReview(r.id),
      })]),
      el("td", { text: r.summary || summarize(r) }),
      el("td", null, [statusPill(r.status)]),
    ])));
    $("#reports-empty").classList.toggle("hidden", reports.length > 0);
  }

  // Found-person form
  const fForm = $("#found-form");
  const fMsg = $("#found-message");
  const fFields = ["age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
    "found_place", "found_time", "current_location", "description"];
  const fRequired = ["age_min", "age_max", "gender", "found_place", "found_time", "current_location"];
  fForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(fMsg);
    const data = readForm(fForm, fFields);
    const errors = validatePerson(fForm, data, fRequired, PERSON_LABELS);
    if (errors.length) { showMessage(fMsg, "error", errorSummary(fForm, errors)); return; }
    await withBusy(fForm.querySelector("button[type=submit]"), async () => {
      try {
        const res = await guarded(() => api("POST", "/api/found", data, { auth: true }), fMsg);
        fForm.reset();
        showMessage(fMsg, "success", "Found person saved as " + res.id + ". Match suggestions will update.");
        await loadReports();
        if (selected) await openReview(selected, true);
      } catch (e) { /* already shown */ }
    });
  });

  // Match review
  const review = $("#review");

  async function openReview(id, keepFocus) {
    selected = id;
    renderReports();
    review.classList.remove("hidden");
    const list = $("#candidates");
    const box = $("#review-message");
    clearMessage(box);
    $("#review-heading").textContent = "Possible matches for report " + id;
    list.replaceChildren(el("p", { text: "Loading suggestions…" }));
    let data;
    try {
      data = await guarded(() => api("GET", "/api/matches/" + encodeURIComponent(id), undefined, { auth: true }), box);
    } catch (e) { list.replaceChildren(); return; }

    const report = reports.find(r => r.id === id) || {};
    const cands = data.candidates || [];
    list.replaceChildren(...(cands.length
      ? cands.map((c, i) => candidateCard(id, report, c, i + 1))
      : [el("p", { text: "No suggested matches yet. Suggestions appear as found people are added." })]));
    if (!keepFocus) $("#review-heading").focus();
  }

  function recordList(rows) {
    return el("dl", null, rows.flatMap(([label, value]) =>
      value === undefined || value === null || value === "" ? [] : [el("dt", { text: label }), el("dd", { text: String(value) })]));
  }

  function personRows(r, kind) {
    const age = r.age_min !== undefined ? r.age_min + "–" + r.age_max : undefined;
    const rows = [["Age", age], ["Gender", r.gender], ["Height", r.height_cm && r.height_cm + " cm"],
      ["Hair", r.hair], ["Clothing", r.clothing], ["Marks", r.marks]];
    if (kind === "missing") {
      rows.push(["Last seen", r.last_seen_place], ["Last seen at", formatTime(r.last_seen_time)]);
    } else {
      rows.push(["Found at", r.found_place], ["Found on", formatTime(r.found_time)], ["Now at", r.current_location]);
    }
    rows.push(["Description", r.description]);
    return rows;
  }

  function candidateCard(mid, report, c, rank) {
    const score = Math.max(0, Math.min(100, Math.round(c.score)));
    const headingId = "cand-" + c.found_id;
    const box = el("div", { class: "message", role: "status", tabindex: "-1" });

    async function decide(decision, btn) {
      if (decision === "confirm" && !confirm("Confirm that report " + mid + " and found person " + c.found_id +
          " are the same person? Only confirm after checking in person or with documents.")) return;
      await withBusy(btn, async () => {
        try {
          await guarded(() => api("POST", "/api/matches/" + encodeURIComponent(mid) + "/decision",
            { found_id: c.found_id, decision }, { auth: true }), box);
          await loadReports();
          await openReview(mid, true);
          showMessage($("#review-message"), "success",
            decision === "confirm" ? "Match with " + c.found_id + " confirmed. The family will see “Reunited”."
              : "Suggestion " + c.found_id + " rejected.");
        } catch (e) { /* already shown */ }
      });
    }

    return el("article", { class: "card candidate", "aria-labelledby": headingId }, [
      el("div", { class: "candidate-head" }, [
        el("h3", { id: headingId, text: "#" + rank + " · Found person " + c.found_id }),
        el("span", { class: "score-label", text: "Score " + score + " / 100" }),
      ]),
      el("div", {
        class: "score-bar", role: "meter", "aria-valuemin": "0", "aria-valuemax": "100",
        "aria-valuenow": String(score), "aria-label": "Match score",
      }, [el("div", { class: "score-fill", style: "width:" + score + "%" })]),
      el("h4", { text: "Why this was suggested" }),
      el("ul", { class: "reasons" }, (c.reasons || []).map(r => el("li", null, [
        el("span", { class: "mark " + (r.matched ? "yes" : "no"), "aria-hidden": "true", text: r.matched ? "✓" : "✗" }),
        el("span", { class: "sr-only", text: r.matched ? "Matches: " : "Does not match: " }),
        el("span", { text: r.label }),
      ]))),
      el("div", { class: "compare" }, [
        el("section", { "aria-label": "Missing report " + mid }, [el("h4", { text: "Missing report " + mid }), recordList(personRows(report, "missing"))]),
        el("section", { "aria-label": "Found record " + c.found_id }, [el("h4", { text: "Found record " + c.found_id }), recordList(personRows(c.found || {}, "found"))]),
      ]),
      el("div", { class: "actions" }, [
        el("button", { type: "button", class: "confirm", text: "Confirm match", onclick: e => decide("confirm", e.currentTarget) }),
        el("button", { type: "button", class: "reject", text: "Reject", onclick: e => decide("reject", e.currentTarget) }),
      ]),
      box,
    ]);
  }

  const resetBtn = $("#mock-reset");
  if (USE_MOCK && resetBtn) {
    resetBtn.classList.remove("hidden");
    resetBtn.addEventListener("click", async () => {
      mockReset();
      selected = null;
      review.classList.add("hidden");
      await loadReports();
    });
  }

  if (USE_MOCK) $("#pin-hint").textContent = "Demo mode: any code is accepted. The real server checks the code.";
  if (getPin()) unlock();
}

/* ---------- Platform page ---------- */

async function initPlatform() {
  const box = $("#bench-message");
  const fmt = n => Number(n).toLocaleString();
  try {
    const b = await api("GET", "/api/benchmark");
    const on = b.chip_on, off = b.chip_off;
    const max = Math.max(on.pairs_per_sec, off.pairs_per_sec) || 1;
    for (const [key, v] of [["on", on], ["off", off]]) {
      const pct = Math.round((v.pairs_per_sec / max) * 100);
      $("#bench-" + key + "-value").textContent = fmt(v.pairs_per_sec) + " pairs/sec · " + v.seconds + " s";
      const track = $("#bench-" + key + "-track");
      track.setAttribute("aria-valuenow", String(v.pairs_per_sec));
      track.setAttribute("aria-valuemax", String(max));
      requestAnimationFrame(() => { $("#bench-" + key).style.width = pct + "%"; });
    }
    const speedup = off.pairs_per_sec ? (on.pairs_per_sec / off.pairs_per_sec).toFixed(1) : "–";
    $("#bench-summary").textContent = "Accelerator on handles about " + speedup + "× as many pairs per second in this comparison.";
    $("#bench-note").textContent = b.note || "";
  } catch (e) {
    showMessage(box, "error", "Benchmark numbers are not available right now. " + e.message);
  }
}

/* ---------- Boot ---------- */

document.addEventListener("DOMContentLoaded", () => {
  markMockMode();
  const page = document.body.dataset.page;
  if (page === "family") initFamily();
  else if (page === "authority") initAuthority();
  else if (page === "platform") initPlatform();
});
