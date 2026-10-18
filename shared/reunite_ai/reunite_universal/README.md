# Reunite universal dataset

Fictional people in 10 realistic disaster scenarios, written in 14 languages and scripts. Built to:
1. **Fine-tune a small LLM** (IBM Granite 4.0 350M) to read a report in any language and return one fixed JSON shape (`schema.json`).
2. **Train and test the matching model** that decides whether a missing report and a found report are the same person.

All people are fictional. Scenarios borrow real places and disaster types so the text looks real. Regenerate with `python3 generate_universal.py` (same output every time).

## Scenarios
| Code | Scenario | Report languages | Split |
|---|---|---|---|
| PK | Monsoon floods, Sindh | English, Urdu (Roman + Urdu script) | train |
| NP | Glacier flash flood, Rasuwa | English, Nepali (Roman + Devanagari) | train |
| MX | Hurricane, Guerrero | Spanish, English | train |
| BR | River floods, Rio Grande do Sul | Portuguese, English | train |
| IT | Earthquake, central Apennines | Italian, English | train |
| HT | Earthquake, southern Haiti | Haitian Creole, French, English | train |
| JP | Earthquake, Noto Peninsula | Japanese, English | train |
| TR | Earthquake, Hatay | Turkish, English | train |
| **MA** | Earthquake, Al Haouz | Arabic, French, English | **test (never seen in training)** |
| **PH** | Typhoon, Leyte | Filipino (Taglish), English | **test (never seen in training)** |

Testing on two countries the model never saw is how you show it works universally.

## Files
| File | Rows | Use |
|---|---|---|
| `llm_train.jsonl` | 9,169 | Fine-tuning pairs: report text → JSON. Has `messages` (chat format) and `input`/`output` |
| `llm_val.jsonl` | 1,018 | Validation during fine-tuning (same 8 countries) |
| `llm_test.jsonl` | 2,599 | Final test on unseen countries (Morocco, Philippines) |
| `missing_reports.csv` | 6,897 | What families submit: free text + form data (reporter phone, last-seen coordinates) |
| `found_reports.csv` | 5,889 | Shelters, hospitals and the public: free text + condition, consent, child flag, location |
| `families.csv` / `family_members.csv` | 1,145 / 2,824 | Registered families and their members |
| `ground_truth.csv` | 12,786 | record → person. **Evaluation only, never load into the app** |
| `people.csv` | 7,000 | The hidden true person behind each record. **Evaluation only** |
| `schema.json` | | The JSON shape the LLM must return |
| `meta.json` | | System prompt, vocabulary, scenarios, places and coordinates |

5,343 true missing ↔ found pairs exist for training and testing the matcher.

## What makes it realistic (and hard)
- Same name in different scripts and spellings: محمد / Mohammed / Mohd, 佐藤 茂 / SATO Shigeru / Shigeru Sato, Hernández / Hernandez
- Japanese family-name-first order, Spanish double surnames, "da Silva" vs "Silva", nicknames only (Pancho, Kancha, Inday)
- Typos, lowercase names, missing details, families reporting the same person 2–3 times
- Unidentified people ("cannot say their name"), estimated ages, children, deceased records

## Labelling rules (what the LLM learns)
- `name`: copied exactly as written. `name_latin`: standard Latin spelling, given name first.
- Missing reports state an exact age → `age_min` = `age_max`. Found reports say "about N" → N±5 (N±3 under 14).
- `clothing`, `marks`, `medical`, `languages`: always plain English from a fixed vocabulary (`meta.json`), whatever the input language.
- `place` and `location_now`: standard Latin place names.
- Anything not in the text is `null` or `[]`. The model should never guess.

## Known simplifications
Sentences come from templates, so wording is more regular than real messages. Some gender and colour agreements are simplified (for example in Urdu). Before a real deployment, add real-style messages reviewed by native speakers.
