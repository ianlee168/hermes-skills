---
name: laya-decision-engine
description: "Use when installing or using Laya (typed-decision engine)."
tags: [laya, decision-model, pytorch, cuda, huggingface, inference, routing, calibration]
metadata:
  hermes:
    triggers:
      - "install laya"
      - "NandhaKishorM/laya"
      - "convaiinnovations/laya"
      - "typed decision engine"
      - "pip install laya"
      - "choice / score / noul question"
      - "laya Router multilingual routing"
    related_skills: [windows-software-install, huggingface-hub, llama-cpp, hermes-windows-bash-quirks]
---

# Laya: install + operate

Laya (github `NandhaKishorM/laya`, PyPI `laya`, Apache-2.0) answers **typed questions**
(`choice` / `score` / `noul`) over any state in ONE non-autoregressive forward pass (~15-35 ms on
consumer GPU, 0 output tokens). Weights are open on the hub; three checkpoints in one repo:

| router key | repo path | encoder | best at |
|---|---|---|---|
| `english` | repo root | ModernBERT-large | English |
| `multilingual` | `multilingual` | mmBERT-base | 45+/51 languages |
| `typed-decisions` | `typed-decisions` | (fine-tuned on typed-decisions) | real decision tasks |


> Layout on this machine (substitute equivalents elsewhere): project scripts `<PROJECT_DIR>`,
> dedicated venv `<VENV>`, HF weight cache `<HF_HOME>` and pip cache `<PIP_CACHE>` all live on a
> non-C: data drive - C: holds Hermes only.

## Install (dedicated venv, caches OFF C:)

Requirements: Python >= 3.10, CUDA GPU for the advertised latency. Never install into the Hermes
venv — it pins torch/transformers major versions that will collide with Hermes deps.

```bash
PY="<PYTHON310_EXE>"   # standalone base, NOT the hermes venv
VENV="<VENV>"; mkdir -p <VENV_PARENT>
"$PY" -m venv "$VENV"
VPY="$VENV/Scripts/python.exe"
"$VPY" -m pip install --upgrade pip setuptools wheel
# pin the +cuXXX local version AND add the pytorch index (see pitfalls)
"$VPY" -m pip install "torch==2.9.1+cu128" --extra-index-url https://download.pytorch.org/whl/cu128
"$VPY" -m pip install laya
```

Wrap every run in a launcher that keeps downloads off C: (weights are ~2.4 GB in total):

```bat
set "HF_HOME=<HF_HOME>"
set "PIP_CACHE_DIR=<PIP_CACHE>"
"<VENV>\Scripts\python.exe" %*
```

Model weights land under `%HF_HOME%\hub\models--convaiinnovations--laya\`. Pre-warm them with any
python that has `huggingface_hub`, using the same allow_patterns `Agent` uses so you never pull the
whole 3-checkpoint family:
`['rl_agent_config.json','model.safetensors','tokenizer/*','encoder/*']` (prefix `multilingual/` or
`typed-decisions/` for the subfolders).

## Verify (never report success without these)

```bash
"$VPY" -c "import torch,laya;print(laya.__version__,torch.__version__,torch.cuda.is_available(),torch.version.cuda)"
# then: load, predict, time it, read VRAM
```
Expected on an RTX 4070 SUPER (12 GB): load 5.9 s from local cache, 1 question p50 **15.3 ms**,
10 batched questions p50 **26.5 ms**, 1.6 GiB VRAM per checkpoint. Checkpoints are fp32 ModernBERT
sizes (843 MB / 644 MB / 843 MB on disk) — three resident fit comfortably in 12 GB.

## API cheatsheet

```python
import laya
agent = laya.load("convaiinnovations/laya")                            # english, auto-CUDA
agent = laya.load("convaiinnovations/laya", subfolder="multilingual")  # or typed-decisions
res   = agent.predict(state, questions)          # alias of system_one, one pass for all questions
res["answers"][qid]["choice"|"score"|"noul"]    # choice: label+probabilities+confidence
res["usage"]                                     # input_tokens, output_tokens=0
```

- `state` = str | dict | list; field names are free text.
- `confidence` = normalised entropy `1 - H(p)/log k`, NOT top-1 probability.
- Presets: `router_questions()`, `guard_questions()`, `moderation_questions()`, `triage_questions()`,
  `email_questions()`. Email cleaning: `clean_email_body`, `email_state`; free language detection:
  `detect_language`, `detect_script`, `is_english`.
- Router (recommended entry):
  `Router(preload=True, device="cuda")` keeps all three resident (lazy `max_loaded=1` reloads the
  model, 7-10 s, on every language switch); `router.route(state, q)` decides in <1 ms with no forward
  pass; pass `model=`/`task=`/`lang=` to override.
- >20 options in one `choice` question: raise `agent.cfg["head_max_len"]`/`["max_len"]`
  (defaults 192/512 english, 256/1024 multi), or `predict_shortlist(agent, state, qs,
  embed_fn=laya.embed_fn_from_agent(agent), k=20)`.

## Pitfalls (each one cost real time)

- **PyPI's Windows `torch` wheel is CPU-only** (~124 MB vs 2.86 GB for `+cu128`). And PyPI's newest
  version can outrank the pytorch-index build, so `pip install torch` silently gives you CPU torch.
  Always pin `torch==<ver>+cu128` together with `--extra-index-url https://download.pytorch.org/whl/cu128`.
- **`pip`'s download staging and cache land on C:** — the CUDA wheel alone parks ~2.9 GB in
  `%TEMP%` then ~2.9 GB in the pip cache. Set `PIP_CACHE_DIR` (and `HF_HOME`) to a non-C: drive
  before installing; cleaning the cache afterwards is a delete and needs the user's explicit consent.
- **Native python needs Windows-form paths.** a native Windows path (`<DRIVE>:/dir/proj`) works; MSYS-style
  MSYS-style `/<drive>/dir/...` only works for bash builtins, not for the interpreter's own arguments.
- **`RuntimeWarning: temperatures outside [0.5,5] ... clamping choice:11+=...` on load** means those
  temperature buckets ship unfitted → treat that bucket's `confidence` as uncalibrated. The
  `multilingual` checkpoint ships NO fitted temperatures at all; refit per (question type, option
  count) on held-out data before using its probabilities as thresholds.
- **Zero-shot decision accuracy is near chance.** The base checkpoints score 0.36/0.34 on
  typed-decisions against a 0.318 random / 0.461 majority-class baseline; the 0.766 headline comes
  from the fine-tuned checkpoint. Treat Laya as a fast base to specialise (Kaggle 2xT4 notebook,
  ~4-5 h), not an out-of-the-box decision engine.
- **The English checkpoint fails silently on non-Latin scripts** (Khmer: 0.000 accuracy at 95%
  confidence), so never gate on the model's own confidence for language safety — route on
  `detect_script` BEFORE the forward pass (that is exactly what `Router` does).
- **Chinese check (measured):** department routing is solid (`han` → `multilingual`, billing at
  conf 0.999) but `noul` churn detection on a Chinese cancellation threat read 0.101 with English
  instructions / 0.360 with Chinese instructions, against 0.885 for the English control — i.e.
  noul on Chinese is unreliable on `multilingual`, while `typed-decisions` read the same state 0.789.
  Probe per primitive before trusting a preset on Chinese.
- **`guard_questions()` as a front-end guardrail: usable as ONE layer, never as the only gate.**
  Measured on 20 injection/jailbreak attacks vs 20 benign prompts, routed:
  `prompt_injection` ≥0.5 → recall **0.80** / FPR **0.05**; `jailbreak` ≥0.9 → recall **0.65** / FPR **0.00**;
  OR of both ≥0.5 → recall 0.80 / FPR 0.10; ~19 ms per prompt, 0 output tokens. It nails the loud,
  explicit patterns (~1.00): "ignore all previous instructions", DAN personas, "no restrictions",
  system-prompt echo by name, `[[system]]` override, base64 exfil, fake `User:/Assistant:` dialogue,
  explicit Chinese jailbreaks. It systematically MISSES the indirect/social-engineering classes:
  "repeat the text above starting with…" (0.14), grandma roleplay (0.27), developer/admin
  impersonation (0.22/0.44), credential or env-var extraction (0.75), indirect Chinese asks (0.66).
  Pair it with a deterministic rule layer for those classes and use two thresholds
  (≥0.9 block, 0.5-0.9 log + secondary check). `sensitive_data` (recall 0.10) and `harm_severity`
  (benign max 1.62 vs attack min 0.67) have **no** discriminative power - do not gate on them.
  Vendor's own held-out prompt-injections figure (0.698) agrees with this ballpark.
- **Route before judging Chinese.** On the English checkpoint benign Chinese scores `jailbreak=1.000`
  (100% false positives); on `multilingual` the same prompts score 0.001-0.008 while Chinese attacks
  score 0.66-0.999.
- Keep only the checkpoints you serve resident: guard duty needs `english`+`multilingual` (~3.2 GB);
  preloading all three (~5 GB) competes with local LLM inference on a 12 GB card.
- **`score` is the weakest primitive** (SST-5 0.372): do not build hard branches on it alone.
- First inference after load pays a one-off CUDA/warmup cost (seen ~345 ms); always warm up before
  quoting latency numbers.

## Reference

- Repo README carries an "Honest limits" section — read it before promising accuracy.
- Project layout convention used here: venv `<VENV>`, HF cache `<HF_HOME>`,
  launcher + demo scripts `<PROJECT_DIR>\`.
