# Aneeza's three tasks

Put all these files in the same folder as make_data.py (the folder that has shared/data/).

## Task 3: harder dataset (done, runs anywhere, ~1 s)
    python make_data_hard.py         # -> shared/data_hard/
Same sizes and checks, new wording on both sides (windbreaker, raven hair, "cut mark through left brow", "jacket (red)", blk, approx, more typos).

## Task 2: free-text extraction (run on Colab with a GPU)
    pip install -q transformers
    python extract_freetext.py --backend regex
    python extract_freetext.py --backend regex   --data shared/data_hard
    python extract_freetext.py --backend granite --n 300
    python extract_freetext.py --backend granite --n 300 --data shared/data_hard
Each Granite run reports three systems per field: granite, regex, granite+regex_fallback.
Results in results/extract_*.json (metrics) and results/extract_*.csv (every prediction).
Regex results already measured: original data clothing 98% / marks 99%, hard data clothing 16% / marks 44%.

## Task 1: text encoder on the accelerator (run on LinuxONE in a server slot)
    pip install -q transformers
    python embed_nnpa.py
Tries torch.device("nnpa"), records exactly what happened, then runs CPU for comparison.
Results: results/embed_timing.json (devices, timings, any error message = evidence) and
results/embed_matching.json (does text similarity alone find the right person, on all reports and on reports
where hair/marks/height are mostly blank).
If "nnpa" is not available in the installed PyTorch build, the error message is saved: that build is CPU-only,
and the accelerated build comes from IBM's AI Toolkit. Ask a mentor which build is installed.
