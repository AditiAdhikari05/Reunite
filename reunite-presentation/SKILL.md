---
name: reunite-presentation
description: Facts, numbers and a slide outline for presenting the Reunite frontend (IBM Z Datathon). Use when building slides, speaker notes or a demo script about Reunite, its family and authority portals, or how it runs on IBM LinuxONE.
---

# Presenting Reunite

Reunite is a prototype for the IBM Z Datathon that helps reunite families after a disaster. 


## The one-line pitch

Families report who is missing. Rescue staff record who they have found. A matching engine suggests who might be the same person, and a trained human confirms every match before a family is told anything.



3. **Anyone can help.** A member of the public can report a person they found without an account. It takes about two minutes.
4. **Sensitive data stays in one place.** The website, the data and the matching engine all run on one LinuxONE server, so there are fewer copies and fewer places for the data to leak.
5. **It's designed for people under stress.** It uses plain language, few required fields, "it's fine to leave out what you don't know", and clear error messages.

## What the frontend does, page by page

**Welcome page.** Visitors choose who they are: "I am looking for a family member" (family portal), "I work for an emergency agency" (authority portal), or "Found someone? Report a person found" (no login). There's also a link to check a report's status.

**Family portal** (create an account, then log in)
- *My family*: save family members in advance (name, relationship, age, height, hair, marks, health notes). If someone goes missing, their details are already filled in.
- *Report a missing person*: pick someone from the family list or describe someone new. The form asks for an age range, gender, height, hair, clothing, distinguishing marks, where and when they were last seen, and a contact for officials.
- *My reports*: every report the family has made, with its current status.
- Sign-up asks for consent to share the information with authorised rescue staff.

**Status page** (no login). Enter a report number such as `M12` to see its status. It refreshes by itself every 15 seconds and explains what each status means.

**Report a person found** (no login). A form for the public. It warns "If someone is injured or in danger, call your local emergency number first". The reporter's name and phone go to staff only, never to families.

**Authority portal** (staff only)
- *Request access*: staff fill in their agency, job title, badge number and reason. **Nobody gets in until the administrator approves them.**
- *Log in* with work email and password. (An earlier version also asked for a shared access PIN. It was removed because personal accounts with admin approval are safer and less confusing.)
- *Missing-person reports*: a table where reports the engine has flagged (⚑) come first.
- *Possible matches*: for a selected report, the top 10 candidates, each with a score from 0 to 100 and the reasons ("age matches", "same clothing" and so on).
- *Confirm / Reject / Undo*: confirming asks "only confirm after checking in person or with documents". If that found person is already confirmed for another report, the app blocks it and says which one.
- *Add a found person*: for people in shelters and hospitals.
- *Manage authority accounts* (admin only): approve or decline access requests, add or remove staff.
- A banner on every staff page: "Scores are suggestions. A human must verify every match."

**How it works page** (`platform.html`). Explains the LinuxONE setup and shows the benchmark results live from the server, including the full raw output, so nothing is hidden or reworded.

## Technical points worth one slide

- **Frontend**: plain HTML, CSS and JavaScript. No framework and no build step, so it's quick to load on weak connections and easy to audit.
- **Backend**: Python Flask on IBM LinuxONE (`s390x`). The same server hosts the pages, the API and the matching engine.
- **Security**: personal accounts with hashed passwords, a session cookie (HttpOnly), and role checks on the server for every staff request. Staff access needs admin approval. Families can't see match details.
- **Accessibility**: skip links, labelled fields, error summaries and messages that screen readers announce.
- **Mock mode**: one switch (`USE_MOCK`) lets the whole frontend run with fake data and no server. That's how it was built and tested before the backend was ready.
- **All data is synthetic.** No real people.

## Numbers (measured on the LinuxONE server, Oct 2026)

Accuracy uses 122 held-out synthetic reports the model never trained on, matched against a pool of 600 found people.

| Method | Right person ranked 1st | Right person in top 5 |
|---|---|---|
| Keyword search (baseline) | 7.4% | 18.9% |
| Hand-written rules | 57.4% | 75.4% |
| **Learned scorer (deployed)** | **73.0%** | **92.6%** |

- In the top 10: 98.4% for the deployed scorer.
- When the engine flags a report, its top suggestion is correct **92%** of the time.
- What matters most: without appearance details (hair, clothing, marks), top-1 accuracy drops from 73% to 33%.
- **Speed**: a full re-scan compares every report with every found person. That's 235,025 pairs (395 reports × 595 found people) in about **0.4 seconds**. Scoring alone takes 0.02 s.

**The IBM Z AI accelerator: present this honestly.**
- On a stress test (a generic 4-layer neural network, *not* our matcher), the accelerator was **5.7× faster** (3.91 s → 0.69 s).
- On our actual matcher, which is a very small model, it was **slower (0.6×)**, because moving the data to the accelerator costs more than the maths saves.
- The takeaway: the accelerator pays off for bigger models. Ours is small enough that the plain CPU is already fast. The platform page shows both results, so say both on the slide too. Don't claim the accelerator sped up our matching.

Live figures can change after a re-run. Check `http://148.100.76.31:5000/platform.html` before presenting.

## Live demo

The live site is **http://148.100.76.31:5000/**. Ask Aditi for the authority login. Don't put passwords on slides.

Add `?demo=1` to a page address to show a **Demo helper** panel that fills in a ready-made case.

1. Family portal: open `/family/index.html?demo=1`, click **Fill missing report**, then **Send report**. Note the number, for example `M13`.
2. Open `/status.html?id=M13`. It shows **Searching**.
3. Authority portal: open `/authority/index.html?demo=1`, click **Fill found record** for the same case, then **Save found person**.
4. The status page changes to **Possible match under review** within 15 seconds. The report shows ⚑ in the staff table.
5. Open the report, show the score and the reasons, and click **Confirm**. The status becomes **Reunited**. **Undo** reverses it.

Practise it once beforehand. If the live site is down, the frontend can run on a laptop in mock mode (see the repository README).

## Suggested slide outline (8–10 slides)

1. **Title**: Reunite: reuniting families after disasters
2. **The problem**: after a disaster, families and rescue teams hold separate, messy lists, and matching them by hand is slow
3. **Our approach**: three users (families, staff, the public), one matching engine, a human confirms every match
4. **Family experience**: screenshots of the welcome page, the missing-person form and the status page
5. **Staff experience**: screenshots of the flagged report table, the match list with reasons, and confirm or undo
6. **Privacy and safety by design**: status-only for families, admin-approved staff, no PIN, data kept on one server
7. **Live demo** (or a recorded fallback)
8. **Results**: the accuracy table, the 0.4-second re-scan, and the honest accelerator finding
9. **Why LinuxONE**: sensitive data in one secure place, with the engine running next to the data
10. **Next steps**: password reset, email or SMS alerts, real-world data partners, a bigger model that would actually benefit from the accelerator

## Screenshots to take

The welcome page, the family *Report a missing person* form, the status page in each of its three states, the public found-person form, the authority reports table with ⚑ flags, the match list with scores and reasons, and the admin access-request panel. Use only synthetic demo data.
