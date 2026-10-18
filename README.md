# Reunite

Privacy-first family reunification after disasters, built on IBM LinuxONE for the IBM Z Datathon 2026 (Track 2: AI Secured – Innovation Without Exposure).

Families report people who are missing. Shelters, hospitals, rescue staff and members of the public record people they have found. An AI matching engine ranks likely matches with a score and the reasons behind it, and a trained person confirms every match before a family is contacted. Families only ever see a status: **Searching**, **Possible match under review** or **Reunited**.

All data in this repository is synthetic. No real people are involved.

## Features

- **Family portal:** sign up, save family members in advance, report someone missing and follow each report's status.
- **Public found-person report:** anyone can report a person they found, without an account.
- **Authority portal:** admin-approved staff accounts, a report queue with flagged likely matches, ranked suggestions with reasons, and Confirm / Reject / Undo.
- **Matching engine:** scores every missing report against every found person using 33 clues (age, gender, height, hair, clothing, marks, place and time).
- **Free-text reading:** IBM Granite extracts hair, clothing and marks from one-line reports, and a grounding check keeps only details that appear in the original text.
- **Privacy by design:** all data, models and AI stay on one LinuxONE server. No outside AI service is called.

## Architecture

See [architecture.html](architecture.html) for the architecture diagram and solution flowchart.

```
Browser (families · public · staff)
        │  HTTP / JSON
        ▼
IBM LinuxONE (s390x) — Docker container
  ├── Web front end (HTML, CSS, JavaScript)
  ├── Flask API (session login, role checks, hashed passwords)
  ├── Records (reports, found people, decisions)
  ├── Matching engine (scikit-learn logistic regression, TensorFlow + IBM zDNN)
  └── Telum on-chip AI accelerator (NNPA): IBM Granite 350M, MiniLM embeddings via PyTorch
```

## Results

Measured on the LinuxONE server with held-out synthetic data:

| Measure | Result |
|---|---|
| Right person in the top 5 suggestions | 92.6% (keyword search: 18.9%) |
| Right person ranked first | 73.0% (keyword search: 7.4%) |
| Full re-scan of all report pairs | 235,025 pairs in 0.4 s |
| MiniLM embeddings on the AI chip vs CPU | 9.4× faster, identical output |
| Granite 350M on the AI chip vs CPU | 6.9× faster, identical output |
| Clothing read correctly from unfamiliar wording | 75% (rules alone: 14%) |

## Repository structure

```
shared/
  backend/        Flask API, matching engine, training and test scripts, trained models
  frontend/       Web pages: welcome, family portal, authority portal, public report, status, platform
  data/           Main synthetic dataset (missing, found, places, truth)
  data_hard/      Harder dataset with new vocabulary and typos
  reunite_ai/     Multilingual matching, location and risk models
  docs/           AI chip benchmark results
tasks/            Text embeddings and Granite extraction experiments on the AI chip
architecture.html Architecture diagram and solution flowchart
*.ipynb           IBM AI on LinuxONE lab notebooks and experiment notebooks
```

## Running it

The backend serves the web pages and the API from the same address, on port 5000. Python 3.12 is recommended.

```bash
cd shared/backend
pip install -r requirements.txt
python3 train.py --data ../data --out models     # retrain on this machine (about 30 s)
python3 selftest.py                              # automated API checks; should end with "0 failed"
python3 create_admin.py <admin-email> '<a-long-password>'
nohup python3 app.py > app.log 2>&1 &
```

Then open `http://<server-address>:5000/`. Check that it is running at `http://<server-address>:5000/api/health`. Stop it with `python3 stop_app.py`.

To try the web pages on their own with built-in sample data, set `const USE_MOCK = true;` on the first line of `shared/frontend/app.js`, then run `python3 -m http.server 5500` inside `shared/frontend` and open <http://localhost:5500/>.

Add `?demo=1` to a page address to show a demo helper that fills in ready-made cases.

## Privacy and safety

- Families never see scores, found-person details or other people's reports.
- Staff accounts must be approved by an administrator. Passwords are stored only as salted hashes.
- Scores are suggestions. The software never confirms a match by itself.
- Saved reports and accounts (`shared/backend/state/`) are created at run time and are not part of this repository.

## Open-source tools

[Python](https://www.python.org/) · [Flask](https://flask.palletsprojects.com/) · [scikit-learn](https://scikit-learn.org/) · [NumPy](https://numpy.org/) · [pandas](https://pandas.pydata.org/) · [PyTorch](https://pytorch.org/) · [TensorFlow](https://www.tensorflow.org/) · [Hugging Face Transformers](https://huggingface.co/docs/transformers) · [IBM Granite 4.0 350M](https://huggingface.co/ibm-granite/granite-4.0-350m) · [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
