const USE_MOCK = true;

/* DisasterBridge-AI frontend logic. Plain JavaScript, no build step.
   When USE_MOCK is true, every API call is answered by the synthetic mock
   below. Set it to false once the Flask backend serves /api/*.

   Login uses a server session cookie (set by the backend on login), so the
   browser sends it automatically with every same-origin fetch. No password,
   token or access code is kept in JavaScript or browser storage. */

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

function show(node, visible) { node.classList.toggle("hidden", !visible); }

/* ---------- API helper ---------- */

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(method, path, body) {
  if (USE_MOCK) return mockApi(method, path, body);

  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
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

/* ---------- Mock backend (synthetic data only) ----------
   Demo logins below are fake and only exist in mock mode. The real backend
   must keep its own accounts with hashed passwords. */

const MOCK_KEY = "db_mock_state_v3";
const MOCK_SESSION_KEY = "db_mock_session";

const DEMO_ADMIN = { email: "admin@disasterbridge.demo", password: "demo-admin-2026" };
const DEMO_FAMILY = { email: "family@disasterbridge.demo", password: "demo-family-2026" };

function mockSeed() {
  return {
    nextMissing: 13,
    nextFound: 8,
    nextMember: 3,
    users: {
      [DEMO_ADMIN.email]: { name: "Demo Admin", role: "admin", password: DEMO_ADMIN.password },
      "officer@disasterbridge.demo": { name: "Sam Officer", role: "authority", password: "demo-officer-2026" },
      [DEMO_FAMILY.email]: { name: "Demo Family", role: "family", password: DEMO_FAMILY.password, phone: "555-0100" },
      "riya.chen@cityfire.demo": {
        name: "Riya Chen", role: "pending", password: "demo-pending-2026",
        agency: "City Fire Department", position: "Shelter coordinator", staff_id: "CFD-2291",
        reason: "Coordinating intake at City Shelter 2.", requested_at: "2026-10-17T08:20",
      },
    },
    members: {
      P1: {
        owner: DEMO_FAMILY.email, name: "Maya", relationship: "Sister", age: 31, gender: "female",
        height_cm: 165, hair: "black, shoulder length", marks: "scar above left eyebrow",
        notes: "Works at Riverside Market.", report_id: "M12",
      },
      P2: {
        owner: DEMO_FAMILY.email, name: "Leo", relationship: "Son", age: 8, gender: "male",
        height_cm: 128, hair: "brown, short", marks: "", notes: "Allergic to peanuts.", report_id: null,
      },
    },
    missing: {
      M10: {
        owner: "other", age_min: 6, age_max: 9, gender: "male", height_cm: 125,
        hair: "brown, short", clothing: "green school uniform",
        marks: "glasses with blue frames", last_seen_place: "North Primary School",
        last_seen_time: "2026-10-16T14:15",
        description: "Was waiting for the school bus when the water rose.",
        contact: "555-0101",
      },
      M11: {
        owner: "other", age_min: 70, age_max: 78, gender: "female", height_cm: 155,
        hair: "grey, tied back", clothing: "purple cardigan",
        marks: "uses a walking stick", last_seen_place: "Elm Street flats",
        last_seen_time: "2026-10-16T09:30",
        description: "Lives alone on the ground floor. May be confused.",
        contact: "555-0102",
      },
      M12: {
        owner: DEMO_FAMILY.email, member_id: "P1",
        age_min: 28, age_max: 34, gender: "female", height_cm: 165,
        hair: "black, shoulder length", clothing: "red jacket, jeans",
        marks: "scar above left eyebrow", last_seen_place: "Riverside Market",
        last_seen_time: "2026-10-16T18:00",
        description: "Last seen heading towards the bridge.",
        contact: "555-0100",
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

function mockSession() {
  try { return sessionStorage.getItem(MOCK_SESSION_KEY); } catch (e) { return null; }
}
function mockSetSession(email) {
  try {
    if (email) sessionStorage.setItem(MOCK_SESSION_KEY, email);
    else sessionStorage.removeItem(MOCK_SESSION_KEY);
  } catch (e) { /* ignore */ }
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

function publicUser(email, u) { return { email, name: u.name, role: u.role }; }

// Strips mock-only bookkeeping (owner) from a missing report before returning it.
function cleanReport(id, r) {
  const out = Object.assign({ id }, r);
  delete out.owner;
  return out;
}

async function mockApi(method, path, body) {
  await new Promise(r => setTimeout(r, 200)); // feel like a network call
  const state = mockLoad();
  const fail = (status, error) => { throw new ApiError(error, status); };
  const email = mockSession();
  const user = email && state.users[email];
  const needRole = (...roles) => {
    if (!user) fail(401, "Please log in.");
    if (!roles.includes(user.role)) fail(403, "You do not have access to this.");
  };
  const isStaff = () => needRole("authority", "admin");
  let m;
  body = body || {};

  /* Accounts */
  if (method === "POST" && path === "/api/auth/signup") {
    const key = String(body.email || "").trim().toLowerCase();
    if (state.users[key]) fail(409, "An account with this email already exists. Please log in instead.");
    state.users[key] = { name: body.name, role: "family", password: body.password, phone: body.phone };
    mockSave();
    mockSetSession(key);
    return { user: publicUser(key, state.users[key]) };
  }

  if (method === "POST" && path === "/api/auth/login") {
    const key = String(body.email || "").trim().toLowerCase();
    const u = state.users[key];
    const staffSide = body.role === "authority";
    if (u && u.password === body.password && staffSide && u.role === "pending") {
      fail(403, "Your access request is still waiting for administrator approval. You can log in once it is approved.");
    }
    const roleOk = u && (staffSide ? u.role === "authority" || u.role === "admin" : u.role === "family");
    if (!u || u.password !== body.password || !roleOk) fail(401, "Email or password is incorrect.");
    mockSetSession(key);
    return { user: publicUser(key, u) };
  }

  if (method === "POST" && path === "/api/auth/logout") {
    mockSetSession(null);
    return { ok: true };
  }

  if (method === "GET" && path === "/api/auth/me") {
    if (!user) fail(401, "Not logged in.");
    return { user: publicUser(email, user) };
  }

  /* Authority access requests (approved by the admin) */
  if (method === "POST" && path === "/api/auth/authority/request") {
    const key = String(body.email || "").trim().toLowerCase();
    if (state.users[key]) fail(409, "There is already an account or request for this email.");
    state.users[key] = {
      name: body.name, role: "pending", password: body.password, agency: body.agency,
      position: body.position, staff_id: body.staff_id, reason: body.reason,
      requested_at: new Date().toISOString().slice(0, 16),
    };
    mockSave();
    return { status: "pending" };
  }

  if (method === "GET" && path === "/api/admin/requests") {
    needRole("admin");
    return Object.entries(state.users).filter(([, u]) => u.role === "pending").map(([e, u]) => ({
      email: e, name: u.name, agency: u.agency, position: u.position, staff_id: u.staff_id,
      reason: u.reason, requested_at: u.requested_at,
    }));
  }

  if (method === "POST" && (m = path.match(/^\/api\/admin\/requests\/([^/]+)\/(approve|reject)$/))) {
    needRole("admin");
    const key = decodeURIComponent(m[1]);
    const u = state.users[key];
    if (!u || u.role !== "pending") fail(404, "Request not found.");
    if (m[2] === "approve") u.role = "authority";
    else delete state.users[key];
    mockSave();
    return { ok: true };
  }

  /* Admin: manage authority accounts */
  if (method === "GET" && path === "/api/admin/authorities") {
    needRole("admin");
    return Object.entries(state.users)
      .filter(([, u]) => u.role === "authority" || u.role === "admin")
      .map(([e, u]) => publicUser(e, u));
  }

  if (method === "POST" && path === "/api/admin/authorities") {
    needRole("admin");
    const key = String(body.email || "").trim().toLowerCase();
    if (state.users[key]) fail(409, "An account with this email already exists.");
    state.users[key] = { name: body.name, role: "authority", password: body.password };
    mockSave();
    return { user: publicUser(key, state.users[key]) };
  }

  if (method === "DELETE" && (m = path.match(/^\/api\/admin\/authorities\/([^/]+)$/))) {
    needRole("admin");
    const key = decodeURIComponent(m[1]);
    const u = state.users[key];
    if (!u || u.role !== "authority") fail(404, "Authority account not found.");
    delete state.users[key];
    mockSave();
    return { ok: true };
  }

  /* Family: members and own reports */
  if (method === "GET" && path === "/api/family/members") {
    needRole("family");
    return Object.entries(state.members)
      .filter(([, p]) => p.owner === email)
      .map(([id, p]) => {
        const out = Object.assign({ id }, p);
        delete out.owner;
        out.status = p.report_id ? mockStatus(state, p.report_id) : null;
        return out;
      });
  }

  if (method === "POST" && path === "/api/family/members") {
    needRole("family");
    const id = "P" + state.nextMember++;
    state.members[id] = Object.assign({}, body, { owner: email, report_id: null });
    mockSave();
    return { id };
  }

  if (method === "DELETE" && (m = path.match(/^\/api\/family\/members\/([^/]+)$/))) {
    needRole("family");
    const p = state.members[decodeURIComponent(m[1])];
    if (!p || p.owner !== email) fail(404, "Family member not found.");
    delete state.members[decodeURIComponent(m[1])];
    mockSave();
    return { ok: true };
  }

  if (method === "GET" && path === "/api/family/reports") {
    needRole("family");
    return Object.entries(state.missing)
      .filter(([, r]) => r.owner === email)
      .map(([id, r]) => ({
        id,
        status: mockStatus(state, id),
        member_name: r.member_id && state.members[r.member_id] ? state.members[r.member_id].name : null,
        last_seen_place: r.last_seen_place,
        last_seen_time: r.last_seen_time,
      }));
  }

  /* Original contract routes */
  if (method === "POST" && path === "/api/missing") {
    needRole("family");
    const id = "M" + state.nextMissing++;
    state.missing[id] = Object.assign({}, body, { owner: email });
    const p = body.member_id && state.members[body.member_id];
    if (p && p.owner === email) p.report_id = id;
    mockSave();
    return { id, status: "searching" };
  }

  if (method === "GET" && (m = path.match(/^\/api\/status\/([^/]+)$/))) {
    const id = decodeURIComponent(m[1]).trim().toUpperCase();
    if (!state.missing[id]) fail(404, "We could not find a report with that number.");
    return { id, status: mockStatus(state, id) };
  }

  if (method === "POST" && path === "/api/found") {
    isStaff();
    const id = "F" + state.nextFound++;
    state.found[id] = Object.assign({}, body);
    mockSave();
    return { id };
  }

  if (method === "GET" && path === "/api/missing") {
    isStaff();
    return Object.entries(state.missing).map(([id, r]) =>
      Object.assign(cleanReport(id, r), { status: mockStatus(state, id), summary: summarize(r) }));
  }

  if (method === "GET" && (m = path.match(/^\/api\/matches\/([^/]+)$/))) {
    isStaff();
    const id = decodeURIComponent(m[1]);
    if (!state.missing[id]) fail(404, "Report not found.");
    return { missing_id: id, candidates: mockCandidates(state, id) };
  }

  if (method === "POST" && (m = path.match(/^\/api\/matches\/([^/]+)\/decision$/))) {
    isStaff();
    const id = decodeURIComponent(m[1]);
    if (!state.missing[id]) fail(404, "Report not found.");
    if (!state.found[body.found_id]) fail(400, "Unknown found_id.");
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

const PERSON_LABELS = {
  age_min: "Lowest age", age_max: "Highest age", gender: "Gender", height_cm: "Height",
  hair: "Hair", clothing: "Clothing", marks: "Distinguishing marks",
  last_seen_place: "The place they were last seen", last_seen_date: "The date they were last seen",
  found_place: "Where they were found", found_date: "The date they were found",
  current_location: "Current location",
  description: "Description", contact: "Your contact details",
  name: "Name", email: "Email", password: "Password", phone: "Phone number",
  relationship: "Relationship", age: "Age",
  agency: "Agency or organisation", position: "Job title", staff_id: "Staff or badge number",
  reason: "Reason for access",
};

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

// Combines the "date" and optional "time" inputs into one ISO string like 2026-10-17T14:30.
function joinDateTime(data, prefix, target) {
  const date = data[prefix + "_date"], time = data[prefix + "_clock"];
  delete data[prefix + "_date"];
  delete data[prefix + "_clock"];
  if (date) data[target] = date + "T" + (time || "00:00");
}

function setFieldError(form, name, msg) {
  const input = form.elements[name];
  if (!input) return;
  const box = $("#" + input.id + "-error", form);
  if (msg) input.setAttribute("aria-invalid", "true");
  else input.removeAttribute("aria-invalid");
  if (box) box.textContent = msg || "";
}

function clearFieldErrors(form) {
  for (const input of form.querySelectorAll("[aria-invalid]")) setFieldError(form, input.name, "");
  for (const box of form.querySelectorAll(".field-error")) box.textContent = "";
}

// Checks required fields plus age, height and email rules. Returns a list of { name, msg }.
function validate(form, data, required) {
  const errors = [];
  const add = (name, msg) => { errors.push({ name, msg }); setFieldError(form, name, msg); };

  clearFieldErrors(form);

  for (const name of required) {
    if (data[name] === undefined) add(name, "Please fill in " + PERSON_LABELS[name].toLowerCase() + ".");
  }
  for (const name of ["age_min", "age_max", "age"]) {
    const v = data[name];
    if (v !== undefined && (!Number.isInteger(v) || v < 0 || v > 120)) {
      add(name, PERSON_LABELS[name] + " must be a whole number from 0 to 120.");
    }
  }
  if (Number.isInteger(data.age_min) && Number.isInteger(data.age_max) && data.age_min > data.age_max &&
      !errors.some(e => e.name === "age_max")) {
    add("age_max", "Highest age must be the same as or more than the lowest age.");
  }
  if (data.height_cm !== undefined && (isNaN(data.height_cm) || data.height_cm < 30 || data.height_cm > 250)) {
    add("height_cm", "Height should be between 30 and 250 cm, or left empty.");
  }
  if (data.email !== undefined && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email)) {
    add("email", "Please enter a valid email address, like name@example.com.");
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

// Sends the visitor to `loginUrl` unless they are logged in with one of `roles`.
async function requireUser(roles, loginUrl) {
  const u = await currentUser();
  if (u && roles.includes(u.role)) return u;
  location.replace(loginUrl);
  return null;
}

function goToLogin(loginUrl) {
  location.replace(loginUrl + "?expired=1");
}

function showExpiredNotice(box) {
  if (new URLSearchParams(location.search).has("expired")) {
    showMessage(box, "error", "Your session has ended. Please log in again.");
  }
}

// Adds Show/Hide to every password box that has a .pw-toggle button next to it.
function setupPasswordToggles() {
  for (const btn of document.querySelectorAll(".pw-toggle")) {
    const input = document.getElementById(btn.getAttribute("aria-controls"));
    btn.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      btn.textContent = showing ? "Show" : "Hide";
      btn.setAttribute("aria-pressed", String(!showing));
    });
  }
}

// Password rules shared by both sign-up forms. Adds errors to `errors`.
function checkNewPassword(form, data, errors) {
  if (data.password && data.password.length < 8 && !errors.some(e => e.name === "password")) {
    errors.push({ name: "password", msg: "Password must be at least 8 characters." });
    setFieldError(form, "password", "Password must be at least 8 characters.");
  }
  if (data.password && data.password !== data.password2) {
    errors.push({ name: "password2", msg: "The two passwords do not match." });
    setFieldError(form, "password2", "The two passwords do not match.");
  }
  delete data.password2;
}

// Requires a ticked consent checkbox called `name`.
function checkConsent(form, name, msg, errors) {
  const box = form.elements[name];
  const errBox = $("#" + box.id + "-error", form);
  if (!box.checked) {
    errors.push({ name, msg });
    box.setAttribute("aria-invalid", "true");
    if (errBox) errBox.textContent = msg;
  } else {
    box.removeAttribute("aria-invalid");
    if (errBox) errBox.textContent = "";
  }
}

async function currentUser() {
  try { return (await api("GET", "/api/auth/me")).user; } catch (e) { return null; }
}

// Wires up a login form. onDone(user) runs after a successful login.
function setupLogin(form, box, role, onDone) {
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(box);
    const data = readForm(form, ["email", "password"]);
    const errors = validate(form, data, ["email", "password"]);
    if (errors.length) { showMessage(box, "error", errorSummary(form, errors)); return; }
    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await api("POST", "/api/auth/login", Object.assign(data, { role }));
        form.reset();
        onDone(res.user);
      } catch (e) {
        showMessage(box, "error", e.status === 401 ? "Email or password is incorrect." : e.message);
      }
    });
  });
}

function recordList(rows) {
  return el("dl", null, rows.flatMap(([label, value]) =>
    value === undefined || value === null || value === "" ? [] : [el("dt", { text: label }), el("dd", { text: String(value) })]));
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

// Portal scripts (family/family.js, authority/authority.js) register their
// page setup functions here. Deferred scripts all run before DOMContentLoaded.
const PAGES = { platform: initPlatform };

document.addEventListener("DOMContentLoaded", () => {
  markMockMode();
  setupPasswordToggles();
  const init = PAGES[document.body.dataset.page];
  if (init) init();
});
