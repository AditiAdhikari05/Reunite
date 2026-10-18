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

  function renderReports() {
    $("#reports-body").replaceChildren(...reports.map(r => el("tr", {
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
    show($("#reports-empty"), reports.length === 0);
    const n = reports.filter(isFlagged).length;
    $("#flagged-count").textContent = n ? n + " report" + (n === 1 ? "" : "s") + " flagged by the matching engine, shown first." : "";
  }

  /* Found people (newest first) */
  async function loadFound() {
    const box = $("#found-list-message");
    clearMessage(box);
    let list;
    try { list = await api("GET", "/api/found"); } catch (e) {
      if (e.status === 401) { goToLogin("login.html"); return; }
      show($("#found-table"), false);
      show($("#found-empty"), false);
      $("#found-count").textContent = "";
      box.replaceChildren(e.status === 404 || e.status === 405
        ? "The found-people list is not available on this server yet. Found people still appear under each report's possible matches."
        : e.message);
      return;
    }
    show($("#found-table"), list.length > 0);
    show($("#found-empty"), list.length === 0);
    const unverified = list.filter(f => f.source === "public").length;
    $("#found-count").textContent = list.length
      ? list.length + " found " + (list.length === 1 ? "person" : "people") +
        (unverified ? ", " + unverified + " reported by the public and not yet verified." : ".")
      : "";
    $("#found-body").replaceChildren(...list.slice().reverse().map(f => el("tr", null, [
      el("td", { text: f.id }),
      el("td", null, [
        f.source === "public" ? el("span", { class: "flag-badge", text: "Public report, unverified" }) : null,
        el("span", { text: f.summary || summarize(f) }),
      ]),
      el("td", { text: [f.found_place, formatTime(f.found_time)].filter(Boolean).join(", ") }),
      el("td", { text: f.current_location || "" }),
      el("td", null, [f.claimed_by
        ? el("button", { class: "link", text: "Reunited with " + f.claimed_by,
            "aria-label": "Review report " + f.claimed_by, onclick: () => openReview(f.claimed_by) })
        : el("span", { text: "Not matched yet" })]),
    ])));
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
    const cands = (data.candidates || []).slice(0, 10);
    list.replaceChildren(...(cands.length
      ? cands.map((c, i) => candidateCard(id, report, c, i + 1))
      : [el("p", { text: "No suggested matches yet. Suggestions appear as found people are added." })]));
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
        const done = { confirm: "Match with " + c.found_id + " confirmed. The family will see “Reunited”.",
          reject: "Suggestion " + c.found_id + " rejected.", undo: "Decision on " + c.found_id + " undone." };
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
