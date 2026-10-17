/* Family portal: log in, sign up and the family dashboard.
   Shared helpers and the API/mock live in ../app.js. */

PAGES["family-login"] = async function () {
  const box = $("#login-message");
  showExpiredNotice(box);
  if (USE_MOCK) $("#login-hint").textContent = "Demo account: " + DEMO_FAMILY.email + " / " + DEMO_FAMILY.password;

  const u = await currentUser();
  if (u && u.role === "family") { location.replace("index.html"); return; }

  setupLogin($("#login-form"), box, "family", () => location.assign("index.html"));
};

PAGES["family-signup"] = function () {
  const form = $("#signup-form");
  const box = $("#signup-message");
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(box);
    const data = readForm(form, ["name", "email", "phone", "password", "password2"]);
    const errors = validate(form, data, ["name", "email", "phone", "password"]);
    checkNewPassword(form, data, errors);
    checkConsent(form, "consent", "Please tick the box to agree before creating your account.", errors);
    if (errors.length) { showMessage(box, "error", errorSummary(form, errors)); return; }
    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        await api("POST", "/api/auth/signup", data);
        location.assign("index.html");
      } catch (e) { showMessage(box, "error", e.message); }
    });
  });
};

PAGES["family-dashboard"] = async function () {
  const user = await requireUser(["family"], "login.html");
  if (!user) return;
  let members = [];

  $("#welcome-name").textContent = user.name;
  $("#welcome-first").textContent = user.name.split(" ")[0];
  show($("#main"), true);

  $("#logout-button").addEventListener("click", async () => {
    try { await api("POST", "/api/auth/logout"); } catch (e) { /* ignore */ }
    location.assign("login.html");
  });

  // Returns true (after redirecting) when the session has ended.
  function kickOut(e) {
    if (e.status === 401 || e.status === 403) { goToLogin("login.html"); return true; }
    return false;
  }

  /* My family */
  async function loadMembers() {
    try { members = await api("GET", "/api/family/members"); } catch (e) {
      if (!kickOut(e)) showMessage($("#members-message"), "error", e.message);
      return;
    }
    renderMembers();
  }

  function renderMembers() {
    show($("#members-empty"), members.length === 0);
    $("#members-list").replaceChildren(...members.map(p => el("li", { class: "card member" }, [
      el("div", { class: "candidate-head" }, [
        el("h3", { text: p.name }),
        p.status ? statusPill(p.status) : null,
      ]),
      recordList([["Relationship", p.relationship], ["Age", p.age], ["Gender", p.gender],
        ["Height", p.height_cm && p.height_cm + " cm"], ["Hair", p.hair], ["Marks", p.marks], ["Notes", p.notes]]),
      el("div", { class: "actions" }, [
        p.report_id
          ? el("span", { class: "hint", text: "Reported missing as " + p.report_id })
          : el("button", { type: "button", text: "Report " + p.name + " missing", onclick: () => startReport(p) }),
        p.report_id ? null : el("button", {
          type: "button", class: "reject", text: "Remove",
          "aria-label": "Remove " + p.name + " from my family",
          onclick: async e => {
            if (!confirm("Remove " + p.name + " from your family list?")) return;
            await withBusy(e.currentTarget, async () => {
              try { await api("DELETE", "/api/family/members/" + encodeURIComponent(p.id)); await loadMembers(); }
              catch (err) { if (!kickOut(err)) showMessage($("#members-message"), "error", err.message); }
            });
          },
        }),
      ]),
    ])));
    fillWhoSelect();
  }

  const mForm = $("#member-form");
  const mMsg = $("#member-message");
  $("#add-member-toggle").addEventListener("click", e => {
    const open = mForm.classList.contains("hidden");
    show(mForm, open);
    e.currentTarget.setAttribute("aria-expanded", String(open));
    if (open) mForm.elements.name.focus();
  });
  mForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(mMsg);
    const data = readForm(mForm, ["name", "relationship", "age", "gender", "height_cm", "hair", "marks", "notes"]);
    const errors = validate(mForm, data, ["name", "relationship"]);
    if (errors.length) { showMessage(mMsg, "error", errorSummary(mForm, errors)); return; }
    await withBusy(mForm.querySelector("button[type=submit]"), async () => {
      try {
        await api("POST", "/api/family/members", data);
        mForm.reset();
        showMessage(mMsg, "success", data.name + " has been added to your family.");
        await loadMembers();
      } catch (e) { if (!kickOut(e)) showMessage(mMsg, "error", e.message); }
    });
  });

  /* Report a missing person */
  const form = $("#missing-form");
  const msg = $("#missing-message");
  const who = form.elements.member_id;

  function fillWhoSelect() {
    const keep = who.value;
    who.replaceChildren(
      el("option", { value: "", text: "Someone not in my family list" }),
      ...members.filter(p => !p.report_id).map(p => el("option", { value: p.id, text: p.name + " (" + p.relationship + ")" })));
    who.value = members.some(p => p.id === keep && !p.report_id) ? keep : "";
  }

  // Copies what we already know about a family member into the report form.
  function prefill(p) {
    const set = (name, v) => { if (v !== undefined && v !== null && v !== "") form.elements[name].value = v; };
    if (typeof p.age === "number") { set("age_min", Math.max(0, p.age - 1)); set("age_max", p.age + 1); }
    set("gender", p.gender);
    set("height_cm", p.height_cm);
    set("hair", p.hair);
    set("marks", p.marks);
  }

  who.addEventListener("change", () => {
    const p = members.find(x => x.id === who.value);
    if (p) prefill(p);
  });

  function startReport(p) {
    who.value = p.id;
    prefill(p);
    $("#report-title").scrollIntoView({ behavior: "smooth", block: "start" });
    who.focus();
  }

  const fields = ["member_id", "age_min", "age_max", "gender", "height_cm", "hair", "clothing", "marks",
    "last_seen_place", "last_seen_date", "last_seen_clock", "description", "contact"];
  const required = ["age_min", "age_max", "gender", "last_seen_place", "last_seen_date", "description", "contact"];

  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    clearMessage(msg);
    const data = readForm(form, fields);
    const errors = validate(form, data, required);
    if (errors.length) { showMessage(msg, "error", errorSummary(form, errors)); return; }
    joinDateTime(data, "last_seen", "last_seen_time");

    await withBusy(form.querySelector("button[type=submit]"), async () => {
      try {
        const res = await api("POST", "/api/missing", data);
        form.reset();
        showMessage(msg, "success", [
          el("strong", { text: "Your report has been received." }),
          el("p", { text: "Your report number is:" }),
          el("span", { class: "report-id", text: res.id }),
          el("p", null, [el("strong", { text: "Save this number." }), " You can also see this report under “My reports” whenever you log in."]),
          el("a", { class: "button", href: "../status.html?id=" + encodeURIComponent(res.id), text: "View status page" }),
        ]);
        await Promise.all([loadMembers(), loadReports()]);
      } catch (e) {
        if (!kickOut(e)) showMessage(msg, "error", e.message);
      }
    });
  });

  /* My reports */
  async function loadReports() {
    let reports;
    try { reports = await api("GET", "/api/family/reports"); } catch (e) {
      if (!kickOut(e)) showMessage($("#reports-message"), "error", e.message);
      return;
    }
    show($("#reports-empty"), reports.length === 0);
    show($("#reports-table"), reports.length > 0);
    $("#reports-body").replaceChildren(...reports.map(r => el("tr", null, [
      el("td", null, [el("a", { href: "../status.html?id=" + encodeURIComponent(r.id), text: r.id,
        "aria-label": "Status page for report " + r.id })]),
      el("td", { text: r.member_name || "—" }),
      el("td", { text: [r.last_seen_place, formatTime(r.last_seen_time)].filter(Boolean).join(", ") }),
      el("td", null, [statusPill(r.status)]),
    ])));
  }

  /* Hidden demo helper: fills the report form with a live-demo case. */
  renderDemoPanel($("#demo-panel"), "Fill missing report", c => {
    form.reset();
    fillForm(form, c.missing, { last_seen_time: "__skip" });
    fillDateTime(form, "last_seen", c.missing.last_seen_time);
    $("#report-title").scrollIntoView({ behavior: "smooth", block: "start" });
    showMessage(msg, "success", "Filled with demo case " + (c.title || c.id) + ". Check it, then press “Send report”.");
  });
  fillPlaces($("#places"));

  // Statuses change when staff confirm a match, so refresh when that may have happened.
  onDataMaybeChanged(() => Promise.all([loadMembers(), loadReports()]));
  await Promise.all([loadMembers(), loadReports()]);
};
