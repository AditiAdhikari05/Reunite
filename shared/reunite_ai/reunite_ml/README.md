# Reunite AI: how to run it on LinuxONE

Upload the zip to your Jupyter home, then run these cells in order. Each cell is one step.

## Cell 1: unzip
```python
!unzip -o -q reunite_ai.zip
%cd reunite_ai/reunite_ml
```

## Cell 2: matching model (about 1 minute)
Learns whether a missing report and a found report are the same person. Uses IBM Snap ML automatically.
```python
!python train_matcher.py
```

## Cell 3: location and risk models (seconds)
```python
!python train_location.py
!python train_risk.py
```

## Cell 4: check that Granite runs on the server (a few minutes)
Downloads Granite 4.0 350M and reads one Arabic report. Before fine-tuning the answer is usually messy. That's expected.
```python
!python check_granite.py
```

## Cell 5: start fine-tuning Granite in the background (the slow one)
It keeps running even if the notebook disconnects, and saves a checkpoint every 25 steps.
```python
!nohup python finetune_granite.py --limit 1200 > finetune.log 2>&1 &
```
Check progress anytime (it prints an ETA):
```python
!tail -5 finetune.log
```
If the ETA is too long, stop it and restart with fewer examples, for example `--limit 600 --max_len 320`.
To stop: `!pkill -f finetune_granite.py` (the last checkpoint stays saved).

## Cell 6: measure Granite before and after fine-tuning
```python
!python eval_extraction.py --n 60 --base     # before
!python eval_extraction.py --n 60            # after (uses the fine-tuned adapter)
```

## Cell 7: run the whole pipeline and time it
```python
!python pipeline.py            # matching + location + risk, timed per report
!python pipeline.py --llm --n 20   # including Granite reading the text
```

## Cell 8: all numbers for the slides
```python
import json, glob
for f in sorted(glob.glob("models/*metrics*.json")):
    d = json.load(open(f)); d.pop("features", None); print(f, json.dumps(d, indent=1))
```

## What each model is
| Step | Model | Library | Tested on |
|---|---|---|---|
| 1. Read any language → JSON | Granite 4.0 350M + LoRA fine-tune | PyTorch, PEFT | Morocco (Arabic, French) and Philippines (Taglish), never seen in training |
| 2. Same person? | Gradient boosting on 20 pair features | IBM Snap ML (scikit-learn fallback) | same |
| 3. Where are they likely to be? | Ranks every shelter and hospital | Snap ML | same |
| 4. Who is most at risk? | Risk of being found in critical condition | Snap ML | same |

## Results from our test run (scikit-learn, before running on LinuxONE)
- Matching: right person ranked first **91%**, in top 5 **96%**, versus **35%** for searching by name as typed. False alarms 10%.
- Location: right shelter or hospital in the top 3 for **64%** of cases, versus 30% calling at random and 61% nearest-first.
- Risk: AUC 0.59, a bit better than a simple "elderly or medical condition" rule (0.55). Treat this one as early.
- Speed: matching + location + risk take **7.5 ms per report** together.

## Honest notes for the pitch
- People and outcomes are simulated. The patterns (injured people go to hospitals, older people stay closer, risk rises with age, medical needs and time missing) are our assumptions. A real deployment learns them from real outcomes.
- Plain PyTorch from pip runs on the CPU. Using the on-chip AI accelerator (NNPA) for PyTorch needs IBM's AI Toolkit build. Ask a mentor if it's available. Snap ML is IBM's library for IBM Z and LinuxONE.
- Save your work to GitHub: the community cloud server has no backups.
