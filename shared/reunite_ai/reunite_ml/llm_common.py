"""Shared helpers for the Granite LLM step (reading reports in any language -> JSON)."""
import json, os, re
import torch
from common import DATA, MODELS, load_jsonl

CANDIDATES = ["ibm-granite/granite-4.0-350m", "ibm-granite/granite-4.0-h-350m", "ibm-granite/granite-4.0-350m-base"]
MODEL_FILE = os.path.join(MODELS, "granite_model.txt")
ADAPTER_DIR = os.path.join(MODELS, "granite_lora")
torch.set_num_threads(os.cpu_count() or 1)

def system_prompt():
    with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as f:
        return json.load(f)["system_prompt"]

def model_id():
    if os.environ.get("GRANITE_MODEL"):
        return os.environ["GRANITE_MODEL"]
    if os.path.exists(MODEL_FILE):
        return open(MODEL_FILE).read().strip()
    return CANDIDATES[0]

def load_model(mid=None, adapter=None):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    mid = mid or model_id()
    tok = AutoTokenizer.from_pretrained(mid)
    try:
        model = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32)
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(mid, torch_dtype=torch.float32)
    if adapter and os.path.isdir(adapter):
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok, model

def prompt_text(tok, report):
    msgs = [{"role": "system", "content": system_prompt()}, {"role": "user", "content": report}]
    return tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)

@torch.no_grad()
def extract(tok, model, report, max_new_tokens=220):
    p = prompt_text(tok, report)
    ids = tok(p, return_tensors="pt", add_special_tokens=False)
    out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tok.pad_token_id)
    text = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    return parse_json(text), text

KEYS = ["report_type", "name", "name_latin", "age_min", "age_max", "gender", "clothing", "marks", "medical", "languages", "place", "location_now"]

def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    for k in KEYS:
        obj.setdefault(k, [] if k in ("clothing", "marks", "medical", "languages") else None)
    return {k: obj[k] for k in KEYS}

def split_rows(split):
    return load_jsonl(os.path.join(DATA, f"llm_{split}.jsonl"))
