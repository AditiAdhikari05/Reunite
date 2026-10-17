const USE_MOCK = false;

/* Reunite frontend logic. Plain JavaScript, no build step.
   When USE_MOCK is true, every API call is answered by the synthetic mock
   below. Set it to false once the Flask backend serves /api/*.

   Login uses a server session cookie (set by the backend on login), so the
   browser sends it automatically with every same-origin fetch. No password,
   token or access code is kept in JavaScript or browser storage. */

const STATUS_LABELS = {
  searching: "Searching",
  possible_match: "Possible match under review",
  reunited: "Reunited",
};

// Accepts older status names too, so the page never shows a raw code.
function normalStatus(s) {
  return s === "under_review" ? "possible_match" : s;
}

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
  status = normalStatus(status);
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

// Logged-in routes rely on the session cookie, which the browser sends itself.
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

const MOCK_KEY = "reunite_mock_state_v5";
const MOCK_SESSION_KEY = "db_mock_session";

const DEMO_ADMIN = { email: "admin@reunite.demo", password: "demo-admin-2026" };
const DEMO_FAMILY = { email: "family@reunite.demo", password: "demo-family-2026" };

function mockSeed() {
  return {
    nextMissing: 13,
    nextFound: 8,
    nextMember: 3,
    users: {
      [DEMO_ADMIN.email]: { name: "Demo Admin", role: "admin", password: DEMO_ADMIN.password },
      "officer@reunite.demo": { name: "Sam Officer", role: "authority", password: "demo-officer-2026" },
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
    decisions: {},  // { M12: { F7: "confirmed", F6: "rejected" } }
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

// Re-reads storage on every call so a report saved in another tab (for
// example the family portal) shows up here straight away.
function mockLoad() {
  try {
    const raw = localStorage.getItem(MOCK_KEY);
    if (raw) mockState = JSON.parse(raw);
  } catch (e) { /* storage unavailable: keep the in-memory copy */ }
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

const MOCK_PLACES = [
  "Bridge Road", "Central Library", "City Shelter 1", "City Shelter 2", "Elm Street bus shelter",
  "Elm Street flats", "General Hospital", "Harbour Station", "North Primary School",
  "Riverside Market", "Station Square",
];

// Synthetic live-demo pairs: submit the missing report (status stays
// "searching"), then add the found record (status flips to "possible_match").
const MOCK_DEMO_CASES = [
  {
    id: "D1", title: "Older man near the harbour", good_for_live_demo: true,
    missing: {
      age_min: 68, age_max: 74, gender: "male", height_cm: 170, hair: "white, short",
      clothing: "brown raincoat", marks: "white beard, hearing aid", last_seen_place: "Harbour Station",
      last_seen_time: "2026-10-17T07:30", description: "Went to check on his boat before the storm.",
      contact: "555-0140",
    },
    found: {
      age_min: 65, age_max: 75, gender: "male", height_cm: 172, hair: "white",
      clothing: "brown raincoat, wet", marks: "white beard", found_place: "Bridge Road",
      found_time: "2026-10-17T11:05", current_location: "General Hospital",
      description: "Hypothermic but awake. Says his name is Tom.",
    },
  },
  {
    id: "D2", title: "Girl with a pink backpack", good_for_live_demo: true,
    missing: {
      age_min: 10, age_max: 12, gender: "female", height_cm: 142, hair: "brown, braided",
      clothing: "school uniform, pink backpack", marks: "freckles", last_seen_place: "North Primary School",
      last_seen_time: "2026-10-16T15:00", description: "Walked home alone after school.",
      contact: "555-0141",
    },
    found: {
      age_min: 9, age_max: 12, gender: "female", height_cm: 140, hair: "brown braids",
      clothing: "pink backpack", marks: "freckles", found_place: "Station Square",
      found_time: "2026-10-16T19:40", current_location: "City Shelter 1",
      description: "Calm, knows her street name.",
    },
  },
  {
    id: "D3", title: "Ambiguous adult (not for live demo)", good_for_live_demo: false,
    missing: {
      age_min: 25, age_max: 45, gender: "unknown", clothing: "dark jacket", last_seen_place: "Station Square",
      last_seen_time: "2026-10-16T20:00", description: "Very little information.", contact: "555-0142",
    },
    found: {
      age_min: 30, age_max: 40, gender: "male", clothing: "black jacket", found_place: "Station Square",
      found_time: "2026-10-16T22:00", current_location: "City Shelter 1", description: "",
    },
  },
];

function mockDecision(state, mid, fid) {
  return (state.decisions[mid] || {})[fid] || null;
}

// Report that has confirmed this found person, if any.
function mockClaimedBy(state, fid) {
  for (const [mid, d] of Object.entries(state.decisions)) if (d[fid] === "confirmed") return mid;
  return null;
}

function mockCandidates(state, mid) {
  const m = state.missing[mid];
  const list = [];
  for (const [fid, f] of Object.entries(state.found)) {
    const r = state.canned[mid + "|" + fid] || mockScore(m, f);
    if (r.score < 40) continue;
    const claimed = mockClaimedBy(state, fid);
    list.push({
      found_id: fid, score: r.score, reasons: r.reasons, found: f,
      decision: mockDecision(state, mid, fid),
      claimed_by: claimed && claimed !== mid ? claimed : null,
    });
  }
  return list.sort((a, b) => b.score - a.score).slice(0, 10);
}

function mockStatus(state, mid) {
  if (Object.values(state.decisions[mid] || {}).includes("confirmed")) return "reunited";
  return mockCandidates(state, mid).some(c => c.score >= 60 && c.decision !== "rejected" && !c.claimed_by)
    ? "possible_match" : "searching";
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
  // Authority routes need a logged-in authority or admin account.
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
    return {
      id, status: mockStatus(state, id),
      authority_contact: "City Reunification Desk, phone 555-0199 (synthetic demo number)",
    };
  }

  if (method === "GET" && path === "/api/places") {
    return MOCK_PLACES;
  }

  if (method === "GET" && path === "/api/demo-cases") {
    return MOCK_DEMO_CASES;
  }

  // Found-person report from a member of the public, no account needed.
  if (method === "POST" && path === "/api/public/found") {
    const id = "F" + state.nextFound++;
    state.found[id] = Object.assign({}, body, { source: "public" });
    mockSave();
    return { id };
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
      Object.assign(cleanReport(id, r), {
        status: mockStatus(state, id), summary: summarize(r),
        flagged: mockStatus(state, id) === "possible_match",
      }));
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
    const fid = body.found_id;
    if (!state.found[fid]) fail(400, "Unknown found_id.");
    const d = state.decisions[id] = state.decisions[id] || {};
    if (body.decision === "confirm") {
      const other = mockClaimedBy(state, fid);
      if (other && other !== id) fail(409, "Found person " + fid + " is already claimed by report " + other + ".");
      if (Object.entries(d).some(([f, v]) => v === "confirmed" && f !== fid)) {
        fail(409, "Report " + id + " already has a confirmed match. Undo it first.");
      }
      d[fid] = "confirmed";
    } else if (body.decision === "reject") {
      d[fid] = "rejected";
    } else if (body.decision === "undo") {
      delete d[fid];
    } else fail(400, "decision must be \"confirm\", \"reject\" or \"undo\".");
    mockSave();
    return { missing_id: id, found_id: body.found_id, decision: body.decision, status: mockStatus(state, id) };
  }

  if (method === "GET" && path === "/api/benchmark") {
    return {
      note: "PLACEHOLDER NUMBERS — not measured results. Real values come from the team's benchmark run.",
      accuracy: {
        cases: 200,
        engine: { top1: 0.78, top5: 0.94 },
        keyword: { top1: 0.41, top5: 0.66 },
      },
      speed: { pairs: 40000, full_rescan_seconds: 1.9 },
      chip: {
        on: { seconds: 1.9 },
        off: { seconds: 2.0 },
        note: "Placeholder: in this run the accelerator made almost no difference.",
      },
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
  reporter_name: "Your name", reporter_phone: "Your phone number",
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
  if (!slot) return;
  const notes = [];
  if (location.protocol === "file:") {
    notes.push(el("div", { class: "message error", role: "alert", text:
      "This page was opened as a file, so the family and authority portals cannot share data. " +
      "In a terminal, run: cd frontend && python3 -m http.server 5500, then open http://localhost:5500/" }));
  }
  slot.replaceChildren(...notes);
}

// Calls `fn` whenever the data may have changed elsewhere: another tab saved
// demo data, or the user came back to this tab.
function onDataMaybeChanged(fn) {
  window.addEventListener("storage", e => { if (e.key === MOCK_KEY) fn(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) fn(); });
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

/* ---------- Places and demo helpers ---------- */

// Fills a <datalist> with place names from GET /api/places so place fields autocomplete.
// The list may be strings or objects with a name.
async function fillPlaces(datalist) {
  if (!datalist) return;
  try {
    const places = await api("GET", "/api/places");
    datalist.replaceChildren(...(places || []).map(p =>
      el("option", { value: typeof p === "string" ? p : (p.name || p.place || "") })));
  } catch (e) { /* free typing still works */ }
}

// The demo panel is hidden unless the page is opened with ?demo=1 (remembered
// for this tab). ?demo=0 hides it again.
function demoMode() {
  const q = new URLSearchParams(location.search).get("demo");
  try {
    if (q === "1") sessionStorage.setItem("db_demo", "1");
    if (q === "0") sessionStorage.removeItem("db_demo");
    return sessionStorage.getItem("db_demo") === "1";
  } catch (e) { return q === "1"; }
}

async function liveDemoCases() {
  const all = await api("GET", "/api/demo-cases");
  return (all || []).filter(c => c.good_for_live_demo === true);
}

// Puts a record's values into a form. `rename` maps record keys to form names.
function fillForm(form, record, rename) {
  for (const [key, value] of Object.entries(record || {})) {
    const name = (rename && rename[key]) || key;
    const input = form.elements[name];
    if (input && value !== null && value !== undefined) input.value = value;
  }
}

// Splits "2026-10-17T14:30" into the date and time inputs used by our forms.
function fillDateTime(form, prefix, iso) {
  if (!iso) return;
  const [date, time] = String(iso).split("T");
  if (form.elements[prefix + "_date"]) form.elements[prefix + "_date"].value = date;
  if (form.elements[prefix + "_clock"] && time) form.elements[prefix + "_clock"].value = time.slice(0, 5);
}

// Builds the hidden demo panel listing live-demo cases. `onPick(case)` runs on click.
async function renderDemoPanel(panel, label, onPick) {
  if (!panel || !demoMode()) return;
  show(panel, true);
  const list = el("div", { class: "actions" });
  panel.replaceChildren(
    el("strong", { text: "Demo helper" }),
    el("p", { class: "hint", text: "Only cases marked good for a live demo are shown. Open the page without ?demo=1 to hide this." }),
    list);
  try {
    const cases = await liveDemoCases();
    list.replaceChildren(...(cases.length ? cases.map(c => el("button", {
      type: "button", class: "secondary", text: label + ": " + (c.title || c.id),
      onclick: () => onPick(c),
    })) : [el("span", { text: "No live-demo cases available." })]));
  } catch (e) {
    list.replaceChildren(el("span", { class: "field-error", text: "Could not load demo cases. " + e.message }));
  }
}

/* ---------- Public status page (no login) ---------- */

const STATUS_EXPLAIN = {
  searching: "We are still looking. New information is checked as it arrives.",
  possible_match: "A trained person is checking a possible match. You will be contacted if it is confirmed.",
  reunited: "This report has been confirmed as a match. Officials will contact you with details.",
};

async function initStatus() {
  const form = $("#status-form");
  const box = $("#status-result");

  // quiet = background refresh: no loading text and no focus jump.
  async function lookUp(id, quiet) {
    if (!quiet) {
      clearMessage(box);
      box.replaceChildren(el("p", { class: "loading", text: "Checking status…" }));
    }
    try {
      const res = await api("GET", "/api/status/" + encodeURIComponent(id));
      const status = normalStatus(res.status);
      // Only the status and the authority contact line are shown. Never match details.
      const contact = res.authority_contact || res.contact_line || res.contact;
      const content = [
        el("p", { text: "Report " + (res.id || id) }),
        statusPill(status, true),
        el("p", { text: STATUS_EXPLAIN[status] || "" }),
        contact ? el("p", null, [el("strong", { text: "Contact: " }), contact]) : null,
        el("p", { class: "hint", text: "Last checked " + new Date().toLocaleTimeString() + ". This page refreshes by itself." }),
      ];
      if (quiet) { box.className = "message"; box.replaceChildren(...content); }
      else showMessage(box, "", content);
      history.replaceState(null, "", "?id=" + encodeURIComponent(res.id || id));
    } catch (e) {
      if (quiet) return;
      showMessage(box, "error", e.status === 404
        ? "We could not find a report with that number. Please check it and try again." : e.message);
    }
  }

  form.addEventListener("submit", ev => {
    ev.preventDefault();
    const id = form.elements.report_id.value.trim().toUpperCase();
    if (!id) { setFieldError(form, "report_id", "Please enter your report number."); form.elements.report_id.focus(); return; }
    setFieldError(form, "report_id", "");
    withBusy(form.querySelector("button[type=submit]"), () => lookUp(id));
  });

  const id = new URLSearchParams(location.search).get("id");
  if (id) { form.elements.report_id.value = id; lookUp(id.trim().toUpperCase()); }

  // Keep the status fresh while the page is open (useful during the live demo).
  setInterval(() => {
    const cur = form.elements.report_id.value.trim().toUpperCase();
    if (cur && !document.hidden && !box.classList.contains("error")) lookUp(cur, true);
  }, 15000);
}

/* ---------- Public "report a found person" page (no login) ---------- */

function initReportFound() {
  const form = $("#public-found-form");
  const box = $("#public-found-message");
  fillPlaces($("#places"));
  const fields = ["age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
    "found_place", "found_date", "found_clock", "current_location", "description",
    "reporter_name", "reporter_phone"];
  const required = ["age_min", "age_max", "gender", "found_place", "found_date", "current_location",
    "reporter_name", "reporter_phone"];
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(box);
    const data = readForm(form, fields);
    const errors = validate(form, data, required);
    if (errors.length) { showMessage(box, "error", errorSummary(form, errors)); return; }
    joinDateTime(data, "found", "found_time");
    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await api("POST", "/api/public/found", data);
        form.reset();
        show(form, false);
        showMessage(box, "success", [
          el("strong", { text: "Thank you. Your report has been sent to rescue staff." }),
          el("p", { text: "Reference: " + res.id + ". Staff will check it and may call you on the number you gave." }),
          el("a", { href: "index.html", text: "Back to home" }),
        ]);
      } catch (e) { showMessage(box, "error", e.message); }
    });
  });
}

/* ---------- Platform page ---------- */

// Renders GET /api/benchmark. Shows whatever the results say, including chip
// results that did not help. The raw output is always shown in full as well.
async function initPlatform() {
  const box = $("#bench-message");
  let b;
  try {
    b = await api("GET", "/api/benchmark");
  } catch (e) {
    show($("#bench-loading"), false);
    showMessage(box, "error", "Benchmark results are not available right now. " + e.message);
    return;
  }
  show($("#bench-loading"), false);

  const pct = v => (typeof v === "number" ? (v <= 1 ? v * 100 : v) : null);
  const fmtPct = v => (v === null ? "–" : (Math.round(v * 10) / 10) + "%");
  const bar = (label, value, cls) => el("div", { class: "bench-row" }, [
    el("div", { class: "bench-label" }, [el("span", { text: label }), el("span", { text: fmtPct(value) })]),
    el("div", { class: "bench-track", role: "meter", "aria-label": label, "aria-valuemin": "0", "aria-valuemax": "100",
      "aria-valuenow": value === null ? "0" : String(value) },
      [el("div", { class: "bench-fill " + cls, style: "width:" + (value || 0) + "%" })]),
  ]);

  if (b.note) { $("#bench-note").textContent = b.note; show($("#bench-note"), true); }

  // Accuracy: engine vs keyword matching, top-1 and top-5.
  const acc = b.accuracy;
  if (acc) {
    const engine = acc.engine || acc.model || acc.ours || {};
    const keyword = acc.keyword || acc.baseline || {};
    $("#accuracy-intro").textContent = "How often the right person was ranked 1st, or in the top 5, " +
      "compared with simple keyword matching" + (acc.cases ? ", over " + acc.cases + " test cases." : ".");
    $("#accuracy-bars").replaceChildren(
      el("h3", { text: "Ranked 1st" }),
      bar("Our matching engine", pct(engine.top1), "on"),
      bar("Keyword matching", pct(keyword.top1), "off"),
      el("h3", { text: "In the top 5" }),
      bar("Our matching engine", pct(engine.top5), "on"),
      bar("Keyword matching", pct(keyword.top5), "off"));
    show($("#accuracy"), true);
  }

  // Speed: full re-scan time.
  const speed = b.speed;
  if (speed) {
    const secs = speed.full_rescan_seconds !== undefined ? speed.full_rescan_seconds : speed.seconds;
    $("#speed-text").replaceChildren(
      el("strong", { text: secs !== undefined ? secs + " seconds" : "–" }),
      el("span", { text: " to re-check every missing report against every found person" +
        (speed.pairs ? " (" + Number(speed.pairs).toLocaleString() + " pairs)." : ".") }));
    show($("#speed"), true);
  }

  // Chip results: shown as reported, even if the chip did not help.
  const chip = b.chip || b.linuxone || b.telum;
  const body = $("#chip-body");
  if (chip) {
    const on = chip.on || chip.chip_on || {}, off = chip.off || chip.chip_off || {};
    const parts = [];
    if (on.seconds !== undefined && off.seconds !== undefined) {
      const max = Math.max(on.seconds, off.seconds) || 1;
      const timeBar = (label, v, cls) => el("div", { class: "bench-row" }, [
        el("div", { class: "bench-label" }, [el("span", { text: label }), el("span", { text: v + " s" })]),
        el("div", { class: "bench-track", role: "meter", "aria-label": label + " time in seconds",
          "aria-valuemin": "0", "aria-valuemax": String(max), "aria-valuenow": String(v) },
          [el("div", { class: "bench-fill " + cls, style: "width:" + Math.round(v / max * 100) + "%" })]),
      ]);
      parts.push(el("p", { text: "Time for the same job with the accelerator on and off. Shorter bars are faster." }),
        timeBar("Accelerator on", on.seconds, "on"), timeBar("Accelerator off", off.seconds, "off"));
    }
    if (chip.note) parts.push(el("p", { class: "chip-note" }, [el("strong", { text: "Result: " }), chip.note]));
    if (!parts.length) parts.push(el("p", { text: "Chip results are listed in the full results below." }));
    body.replaceChildren(...parts);
  } else {
    body.replaceChildren(el("p", { text: "Chip results are not available yet." }));
  }
  show($("#chip"), true);

  $("#raw-json").textContent = JSON.stringify(b, null, 2);
  show($("#raw"), true);
}

/* ---------- Boot ---------- */

// Portal scripts (family/family.js, authority/authority.js) register their
// page setup functions here. Deferred scripts all run before DOMContentLoaded.
const PAGES = { platform: initPlatform, status: initStatus, "report-found": initReportFound };

document.addEventListener("DOMContentLoaded", () => {
  markMockMode();
  setupPasswordToggles();
  const init = PAGES[document.body.dataset.page];
  if (init) init();
});
