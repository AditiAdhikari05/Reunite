/* Authority portal: log in, request access and the staff dashboard.
   Shared helpers and the API/mock live in ../app.js. */

const STAFF_ROLES = ["authority", "admin"];

PAGES["authority-login"] = async function () {
  const box = $("#login-message");
  showExpiredNotice(box);
  if (USE_MOCK) $("#login-hint").textContent = "Demo admin: " + DEMO_ADMIN.email + " / " + DEMO_ADMIN.password + ".";

  const u = await currentUser();
  if (u && STAFF_ROLES.includes(u.role)) { location.replace("index.html"); return; }

  const form = $("#login-form");
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(box);
    const data = readForm(form, ["email", "password"]);
    const errors = validate(form, data, ["email", "password"]);
    if (errors.length) { showMessage(box, "error", errorSummary(form, errors)); return; }
    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        await api("POST", "/api/auth/login", { email: data.email, password: data.password, role: "authority" });
      } catch (e) {
        showMessage(box, "error", e.status === 401 ? "Email or password is incorrect." : e.message);
        return;
      }
      form.reset();
      location.assign("index.html");
    });
  });
};

PAGES["authority-request"] = function () {
  const form = $("#request-form");
  const box = $("#request-message");
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(box);
    const data = readForm(form, ["name", "email", "agency", "position", "staff_id", "reason", "password", "password2"]);
    const errors = validate(form, data, ["name", "email", "agency", "position", "reason", "password"]);
    checkNewPassword(form, data, errors);
    checkConsent(form, "consent", "Please tick the box to confirm you are authorised.", errors);
    if (errors.length) { showMessage(box, "error", errorSummary(form, errors)); return; }
    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        await api("POST", "/api/auth/authority/request", data);
        show(form, false);
        showMessage(box, "success", [
          el("strong", { text: "Request sent." }),
          el("p", { text: "The administrator will review it. Once approved, you can log in with " + data.email + " and the password you chose." }),
          el("a", { href: "login.html", text: "Go to authority log in" }),
        ]);
      } catch (e) { showMessage(box, "error", e.message); }
    });
  });
};

PAGES["authority-dashboard"] = async function () {
  const user = await requireUser(STAFF_ROLES, "login.html");
  if (!user) return;
  const isAdmin = user.role === "admin";
  let reports = [];
  let selected = null;

  $("#welcome-name").textContent = user.name + (isAdmin ? " · Administrator" : "");

  // Redirects to the login page when the session has ended.
  async function guarded(fn, box) {
    try { return await fn(); } catch (e) {
      if (e.status === 401) { goToLogin("login.html"); }
      else if (box) showMessage(box, "error", e.message);
      throw e;
    }
  }

  $("#logout-button").addEventListener("click", async () => {
    try { await api("POST", "/api/auth/logout"); } catch (e) { /* ignore */ }
    location.assign("login.html");
  });

  async function loadReports() {
    const box = $("#reports-message");
    clearMessage(box);
    reports = await guarded(() => api("GET", "/api/missing", undefined), box);
    // Reports the engine has flagged come first.
    reports.sort((a, b) => isFlagged(b) - isFlagged(a));
    renderReports();
  }

  function isFlagged(r) {
    return r.flagged === true || normalStatus(r.status) === "possible_match";
  }

  const REPORT_FILTERS = [
    ["open", "Open", r => normalStatus(r.status) !== "reunited"],
    ["reunited", "Reunited", r => normalStatus(r.status) === "reunited"],
  ];
  let reportFilter = "open";

  function renderReports() {
    $("#report-filters").replaceChildren(...REPORT_FILTERS.map(([key, label, test]) => el("button", {
      type: "button", class: "chip" + (key === reportFilter ? " active" : ""),
      "aria-pressed": key === reportFilter ? "true" : "false",
      text: label + " (" + reports.filter(test).length + ")",
      onclick: () => { reportFilter = key; renderReports(); },
    })));
    const shown = reports.filter(REPORT_FILTERS.find(x => x[0] === reportFilter)[2]);
    $("#reports-body").replaceChildren(...shown.map(r => el("tr", {
      class: [isFlagged(r) ? "flagged" : "", r.id === selected ? "selected" : ""].join(" ").trim() || null,
    }, [
      el("td", null, [el("button", {
        class: "link", text: r.id,
        "aria-label": "Review matches for report " + r.id + (isFlagged(r) ? ", flagged by the engine" : ""),
        onclick: () => openReview(r.id),
      })]),
      el("td", null, [
        isFlagged(r) ? el("span", { class: "flag-badge", text: "⚑ Flagged" }) : null,
        el("span", { text: r.summary || summarize(r) }),
      ]),
      el("td", null, [statusPill(r.status)]),
    ])));
    show($("#reports-empty"), shown.length === 0);
    const n = reports.filter(isFlagged).length;
    $("#flagged-count").textContent = n ? n + " report" + (n === 1 ? "" : "s") + " flagged by the matching engine, shown first." : "";
  }

  /* Found people board: one card per found person, newest first, with the
     missing reports they most resemble. */
  const FOUND_FILTERS = [
    ["open", "Open", f => !f.claimed_by],
    ["public", "Public reports", f => !f.claimed_by && f.source === "public"],
    ["staff", "Staff reports", f => !f.claimed_by && f.source !== "public"],
    ["likely", "Likely match", f => !f.claimed_by && topScore(f) >= 60],
    ["reunited", "Reunited", f => !!f.claimed_by],
  ];
  let found = [];
  let foundFilter = "open";

  // Suggestions staff have not rejected.
  function liveMatches(f) {
    return (f.top_matches || []).filter(m => !String(m.decision || "").startsWith("reject"));
  }

  function topScore(f) {
    return Math.max(0, ...liveMatches(f).map(m => m.score));
  }

  function matchBand(score) {
    if (score >= 80) return ["strong", "Strong"];
    if (score >= 60) return ["possible", "Possible"];
    return ["weak", "Weak"];
  }

  function reviewReport(id) {
    openReview(id);
    $("#review").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function matchRow(f, m) {
    const score = Math.max(0, Math.min(100, Math.round(m.score)));
    const [band, bandLabel] = matchBand(score);
    return el("li", { class: "match-row" }, [
      el("button", {
        type: "button", class: "link match-id", text: m.missing_id,
        "aria-label": "Review missing report " + m.missing_id + ", score " + score,
        onclick: () => reviewReport(m.missing_id),
      }),
      el("div", {
        class: "score-bar mini", role: "meter", "aria-valuemin": "0", "aria-valuemax": "100",
        "aria-valuenow": String(score), "aria-label": "Match score with " + m.missing_id,
      }, [el("div", { class: "score-fill " + band, style: "width:" + score + "%" })]),
      el("span", { class: "match-score", text: String(score) }),
      el("span", { class: "band " + band, text: bandLabel }),
    ]);
  }

  function foundCard(f) {
    const matches = liveMatches(f).slice(0, 3);
    const isPublic = f.source === "public";
    return el("article", { class: "found-card" + (f.claimed_by ? " reunited" : ""), "aria-labelledby": "fc-" + f.id }, [
      el("div", { class: "found-card-head" }, [
        el("h3", { id: "fc-" + f.id, text: f.id }),
        el("span", { class: "source-tag " + (isPublic ? "public" : "staff"),
          text: isPublic ? "Public · unverified" : "Staff record" }),
      ]),
      el("p", { class: "found-summary", text: f.summary || summarize(f) }),
      recordList([
        ["Found", [f.found_place, formatTime(f.found_time)].filter(Boolean).join(", ")],
        ["Now at", f.current_location],
      ]),
      f.claimed_by
        ? el("p", { class: "reunited-note" }, ["✓ Reunited with ",
            el("button", { type: "button", class: "link", text: f.claimed_by, onclick: () => reviewReport(f.claimed_by) })])
        : null,
      f.claimed_by ? null : el("h4", { text: "Closest missing reports" }),
      f.claimed_by ? null : matches.length
        ? el("ul", { class: "match-list" }, matches.map(m => matchRow(f, m)))
        : el("p", { class: "hint", text: "No likely matches yet. The engine checks again as reports arrive." }),
    ]);
  }

  function renderFound() {
    const pass = FOUND_FILTERS.find(x => x[0] === foundFilter)[2];
    const shown = found.filter(pass);
    $("#found-filters").replaceChildren(...FOUND_FILTERS.map(([key, label, test]) => el("button", {
      type: "button", class: "chip" + (key === foundFilter ? " active" : ""),
      "aria-pressed": key === foundFilter ? "true" : "false",
      text: label + " (" + found.filter(test).length + ")",
      onclick: () => { foundFilter = key; renderFound(); },
    })));
    $("#found-grid").replaceChildren(...shown.map(foundCard));
    show($("#found-empty"), found.length > 0 && shown.length === 0);
    const unverified = found.filter(f => f.source === "public").length;
    $("#found-count").textContent = found.length
      ? found.length + " found " + (found.length === 1 ? "person" : "people") +
        (unverified ? ", " + unverified + " from the public and not yet verified." : ".")
      : "No found people recorded yet.";
  }

  async function loadFound() {
    const box = $("#found-list-message");
    clearMessage(box);
    let list;
    try { list = await api("GET", "/api/found"); } catch (e) {
      if (e.status === 401) { goToLogin("login.html"); return; }
      found = [];
      $("#found-filters").replaceChildren();
      $("#found-grid").replaceChildren();
      $("#found-count").textContent = "";
      box.replaceChildren(e.status === 404 || e.status === 405
        ? "The found-people board is not available on this server yet. Found people still appear under each report's possible matches."
        : e.message);
      return;
    }
    found = list.slice().reverse();
    renderFound();
  }

  /* Admin: access requests and authority accounts */
  async function loadRequests() {
    let list;
    try { list = await guarded(() => api("GET", "/api/admin/requests"), $("#admin-message")); } catch (e) { return; }
    show($("#requests-empty"), list.length === 0);
    $("#requests-list").replaceChildren(...list.map(r => el("li", null, [
      el("strong", { text: r.name }),
      recordList([["Email", r.email], ["Agency", r.agency], ["Job title", r.position],
        ["Staff no.", r.staff_id], ["Reason", r.reason], ["Requested", formatTime(r.requested_at)]]),
      el("div", { class: "actions" }, [
        el("button", { type: "button", class: "confirm", text: "Approve", "aria-label": "Approve " + r.name,
          onclick: e => decide(r, "approve", e.currentTarget) }),
        el("button", { type: "button", class: "reject", text: "Decline", "aria-label": "Decline " + r.name,
          onclick: e => decide(r, "reject", e.currentTarget) }),
      ]),
    ])));

    async function decide(r, action, btn) {
      if (action === "reject" && !confirm("Decline the access request from " + r.name + "?")) return;
      await withBusy(btn, async () => {
        try {
          await guarded(() => api("POST", "/api/admin/requests/" + encodeURIComponent(r.email) + "/" + action), $("#admin-message"));
          showMessage($("#admin-message"), "success",
            action === "approve" ? r.name + " can now log in to the authority portal." : "Request from " + r.name + " declined.");
          await Promise.all([loadRequests(), loadAuthorities()]);
        } catch (e) { /* already shown */ }
      });
    }
  }

  async function loadAuthorities() {
    let list;
    try { list = await guarded(() => api("GET", "/api/admin/authorities"), $("#admin-message")); } catch (e) { return; }
    $("#authorities-body").replaceChildren(...list.map(u => el("tr", null, [
      el("td", { text: u.name }),
      el("td", { text: u.email }),
      el("td", { text: u.role === "admin" ? "Administrator" : "Authority" }),
      el("td", null, [u.role === "admin" ? null : el("button", {
        type: "button", class: "reject", text: "Remove",
        "aria-label": "Remove authority account " + u.email,
        onclick: async e => {
          if (!confirm("Remove access for " + u.name + " (" + u.email + ")?")) return;
          await withBusy(e.currentTarget, async () => {
            try {
              await guarded(() => api("DELETE", "/api/admin/authorities/" + encodeURIComponent(u.email)), $("#admin-message"));
              showMessage($("#admin-message"), "success", u.name + " can no longer log in.");
              await loadAuthorities();
            } catch (err) { /* already shown */ }
          });
        },
      })]),
    ])));
  }

  const aForm = $("#authority-form");
  aForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    const box = $("#admin-message");
    clearMessage(box);
    const data = readForm(aForm, ["name", "email", "password"]);
    const errors = validate(aForm, data, ["name", "email", "password"]);
    if (data.password && data.password.length < 8 && !errors.some(e => e.name === "password")) {
      errors.push({ name: "password", msg: "Temporary password must be at least 8 characters." });
      setFieldError(aForm, "password", "Temporary password must be at least 8 characters.");
    }
    if (errors.length) { showMessage(box, "error", errorSummary(aForm, errors)); return; }
    await withBusy(aForm.querySelector("button[type=submit]"), async () => {
      try {
        await guarded(() => api("POST", "/api/admin/authorities", data), box);
        aForm.reset();
        showMessage(box, "success", data.name + " can now log in as an authority with " + data.email + " and the temporary password you set. Share the password with them privately.");
        await loadAuthorities();
      } catch (e) { /* already shown */ }
    });
  });

  /* Found-person form */
  const fForm = $("#found-form");
  const fMsg = $("#found-message");
  const fFields = ["age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
    "found_place", "found_date", "found_clock", "current_location", "description"];
  const fRequired = ["age_min", "age_max", "gender", "found_place", "found_date", "current_location"];
  fForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(fMsg);
    const data = readForm(fForm, fFields);
    const errors = validate(fForm, data, fRequired);
    if (errors.length) { showMessage(fMsg, "error", errorSummary(fForm, errors)); return; }
    joinDateTime(data, "found", "found_time");
    await withBusy(fForm.querySelector("button[type=submit]"), async () => {
      try {
        const res = await guarded(() => api("POST", "/api/found", data), fMsg);
        fForm.reset();
        showMessage(fMsg, "success", "Found person saved as " + res.id + ". Match suggestions will update.");
        await Promise.all([loadReports(), loadFound()]);
        if (selected) await openReview(selected, true);
      } catch (e) { /* already shown */ }
    });
  });

  /* Match review */
  const review = $("#review");

  async function openReview(id, keepFocus) {
    selected = id;
    renderReports();
    show(review, true);
    const list = $("#candidates");
    const box = $("#review-message");
    clearMessage(box);
    $("#review-heading").textContent = "Possible matches for report " + id;
    list.replaceChildren(el("p", { text: "Loading suggestions…" }));
    let data;
    try {
      data = await guarded(() => api("GET", "/api/matches/" + encodeURIComponent(id), undefined), box);
    } catch (e) { list.replaceChildren(); return; }

    const report = data.missing || reports.find(r => r.id === id) || {};
    const all = data.candidates || [];
    const confirmed = all.filter(c => decisionOf(c) === "confirmed");
    const open = all.filter(c => !decisionOf(c) && !c.claimed_by);
    const rejected = all.filter(c => decisionOf(c) === "rejected").length;
    const taken = all.filter(c => !decisionOf(c) && c.claimed_by).length;
    const cands = confirmed.length ? confirmed : open.slice(0, 10);
    $("#review-heading").textContent = (confirmed.length ? "Confirmed match for report " : "Possible matches for report ") + id;
    const hidden = [];
    if (rejected) hidden.push(rejected + " rejected");
    if (taken) hidden.push(taken + " already reunited with another report");
    const note = confirmed.length
      ? "Other suggestions are hidden while this match is confirmed. Undo it to see them again."
      : hidden.length ? "Hidden: " + hidden.join(", ") + "." : "";
    list.replaceChildren(...[note ? el("p", { class: "hint", text: note }) : null].concat(cands.length
      ? cands.map((c, i) => candidateCard(id, report, c, i + 1))
      : [el("p", { text: "No suggested matches left to review. New suggestions appear as found people are added." })]));
    if (!keepFocus) $("#review-heading").focus();
  }

  function personRows(r, kind) {
    const age = r.age_min !== undefined ? r.age_min + "–" + r.age_max : undefined;
    const rows = [["Age", age], ["Gender", r.gender], ["Height", r.height_cm && r.height_cm + " cm"],
      ["Hair", r.hair], ["Clothing", r.clothing], ["Marks", r.marks]];
    if (kind === "missing") {
      rows.push(["Last seen", [r.last_seen_place, formatTime(r.last_seen_time)].filter(Boolean).join(", ")]);
    } else {
      rows.push(["Found", [r.found_place, formatTime(r.found_time)].filter(Boolean).join(", ")], ["Now at", r.current_location]);
    }
    rows.push(["Description", r.description]);
    return rows;
  }

  // Normalises the candidate's decision to "confirmed", "rejected" or null.
  function decisionOf(c) {
    const d = String(c.decision || "");
    if (d.startsWith("confirm")) return "confirmed";
    if (d.startsWith("reject")) return "rejected";
    return null;
  }

  function candidateCard(mid, report, c, rank) {
    const score = Math.max(0, Math.min(100, Math.round(c.score)));
    const headingId = "cand-" + c.found_id;
    const box = el("div", { class: "message", role: "status", tabindex: "-1" });
    const decision = decisionOf(c);

    async function decide(action, btn) {
      if (action === "confirm" && !confirm("Confirm that report " + mid + " and found person " + c.found_id +
          " are the same person? Only confirm after checking in person or with documents.")) return;
      await withBusy(btn, async () => {
        try {
          await api("POST", "/api/matches/" + encodeURIComponent(mid) + "/decision",
            { found_id: c.found_id, decision: action });
        } catch (e) {
          if (e.status === 401) { goToLogin("login.html"); return; }
          showMessage(box, "error", e.status === 409
            ? ["Cannot confirm: ", el("strong", { text: e.message }),
               " Check the other report first. If that match was wrong, undo it there."]
            : e.message);
          return;
        }
        try {
          await Promise.all([loadReports(), loadFound()]);
          await openReview(mid, true);
        } catch (e) { return; }
        const done = { confirm: "Match with " + c.found_id + " confirmed. The family will see “Reunited”, and report " + mid + " has moved to the Reunited list. You can still undo it here.",
          reject: "Suggestion " + c.found_id + " rejected and removed from this list.", undo: "Decision on " + c.found_id + " undone." };
        showMessage($("#review-message"), "success", done[action]);
      });
    }

    const buttons = decision
      ? [el("span", { class: "decision-tag " + decision, text: decision === "confirmed" ? "✓ Confirmed" : "Rejected" }),
         el("button", { type: "button", class: "secondary", text: "Undo", onclick: e => decide("undo", e.currentTarget) })]
      : [el("button", { type: "button", class: "confirm", text: "Confirm match", onclick: e => decide("confirm", e.currentTarget) }),
         el("button", { type: "button", class: "reject", text: "Reject", onclick: e => decide("reject", e.currentTarget) })];

    return el("article", { class: "card candidate" + (decision ? " decided-" + decision : ""), "aria-labelledby": headingId }, [
      el("div", { class: "candidate-head" }, [
        el("h3", { id: headingId, text: "#" + rank + " · Found person " + c.found_id }),
        el("span", { class: "score-label", text: "Score " + score + " / 100" }),
      ]),
      el("div", {
        class: "score-bar", role: "meter", "aria-valuemin": "0", "aria-valuemax": "100",
        "aria-valuenow": String(score), "aria-label": "Match score",
      }, [el("div", { class: "score-fill", style: "width:" + score + "%" })]),
      c.claimed_by ? el("p", { class: "claimed-note", text: "Already claimed by report " + c.claimed_by + "." }) : null,
      (c.found && c.found.source === "public")
        ? el("p", { class: "public-note", text: "Reported by a member of the public. Not yet verified by staff." }) : null,
      el("h4", { text: "Why this was suggested" }),
      el("ul", { class: "reasons" }, (c.reasons || []).map(r => el("li", null, [
        el("span", { class: "mark " + (r.matched ? "yes" : "no"), "aria-hidden": "true", text: r.matched ? "✓" : "–" }),
        el("span", { class: "sr-only", text: r.matched ? "Matches: " : "Does not match: " }),
        el("span", { text: r.label }),
      ]))),
      el("div", { class: "compare" }, [
        el("section", { "aria-label": "Missing report " + mid }, [el("h4", { text: "Missing report " + mid }), recordList(personRows(report, "missing"))]),
        el("section", { "aria-label": "Found record " + c.found_id }, [el("h4", { text: "Found record " + c.found_id }), recordList(personRows(c.found || {}, "found"))]),
      ]),
      el("div", { class: "actions" }, buttons),
      box,
    ]);
  }

  /* Hidden demo helper: fills the found form with a live-demo case. */
  renderDemoPanel($("#demo-panel"), "Fill found record", c => {
    fForm.reset();
    fillForm(fForm, c.found, { found_time: "__skip" });
    fillDateTime(fForm, "found", c.found.found_time);
    $("#found-title").scrollIntoView({ behavior: "smooth", block: "start" });
    showMessage(fMsg, "success", "Filled with demo case " + (c.title || c.id) + ". Check it, then press “Save found person”.");
  });
  fillPlaces($("#places"));

  const resetBtn = $("#mock-reset");
  if (USE_MOCK && resetBtn) {
    show(resetBtn, true);
    resetBtn.addEventListener("click", () => {
      if (!confirm("Reset all demo data, including accounts and requests you added?")) return;
      mockReset();
      location.reload();
    });
  }

  $("#refresh-reports").addEventListener("click", e => withBusy(e.currentTarget, async () => {
    try { await loadReports(); if (selected) await openReview(selected, true); } catch (err) { /* already shown */ }
  }));
  $("#refresh-found").addEventListener("click", e => withBusy(e.currentTarget, loadFound));
  onDataMaybeChanged(async () => {
    try {
      await Promise.all([loadReports(), loadFound()]);
      if (isAdmin) await loadRequests();
    } catch (e) { /* already shown */ }
  });

  try { await loadReports(); } catch (e) { return; }
  show($("#main"), true);
  show($("#admin-panel"), isAdmin);
  loadFound();
  if (isAdmin) await Promise.all([loadRequests(), loadAuthorities()]);
};
