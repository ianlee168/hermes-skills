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

## Install (dedicated venv, caches OFF C:)

Requirements: Python >= 3.10, CUDA GPU for the advertised latency. Never install into the Hermes
venv — it pins torch/transformers major versions that will collide with Hermes deps.

```bash
PY="C:/Users/<user>/AppData/Local/Programs/Python/Python310/python.exe"   # standalone base, NOT the hermes venv
VENV="H:/dev/venvs/laya"; mkdir -p /h/dev/venvs
"$PY" -m venv "$VENV"
VPY="$VENV/Scripts/python.exe"
"$VPY" -m pip install --upgrade pip setuptools wheel
# pin the +cuXXX local version AND add the pytorch index (see pitfalls)
"$VPY" -m pip install "torch==2.9.1+cu128" --extra-index-url https://download.pytorch.org/whl/cu128
"$VPY" -m pip install laya
```

Wrap every run in a launcher that keeps downloads off C: (weights are ~2.4 GB in total):

```bat
set "HF_HOME=H:\dev\models\hf"
set "PIP_CACHE_DIR=H:\dev\cache\pip"
"H:\dev\venvs\laya\Scripts\python.exe" %*
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
- **Native python needs Windows-form paths.** `H:/dev/...` or `C:/Users/...` works; MSYS-style
  `/h/dev/...` only works for bash builtins, not for the interpreter's own arguments.
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

## Fine-tuning on your own traffic (RLCD, single card is enough)

The official Kaggle notebook (`notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb`) is the only
public recipe; it is a self-contained ~220-line training script, not a config flag. Its shape:

1. **Data**: rows of `state` / `questions` / `gold`, each a JSON *string* (dataset
   `LocalLLaMA/typed-decisions`: `id, workflow, split, state, questions, gold, factors,
   label_agreement, n_questions`). `gold` is a **teacher probability distribution** per question
   (`{"action": {"probabilities": {"continue": 0.283, "human_review": 0.433, ...}, ...}}`), not a hard
   label. Hard labels alone cap quality - get a distribution (sample a strong teacher k times and use
   the frequencies; direct LLM self-reported probabilities are poorly calibrated).
2. **Preprocess**: `laya.common.build_sequence(tokenizer, state, {t, ins, crit}, max_len, head_max_len)`
   produces `[CLS] <type> instructions [SEP] [MASK] opt0 [MASK] opt1 ... [SEP] state [SEP]` plus the
   option `markers`; pad to a batch with `pad_token_id`.
3. **Train**: `laya.common.build_model(cfg, encoder_dir=...)` + `proper_reward(q, target, qtype, mask,
   w_sph=0.75, w_rps=1.0)`; GRPO-style policy gradient - sample G=4 noisy logit sets with sigma 0.4→0.1
   (zero-mean projected, masked), group-normalised advantage, plus a 1.0-weighted soft cross-entropy;
   encoder lr 2.5e-5 / head lr 1e-4, AdamW wd 0.01, cosine, fp16 AMP + GradScaler, gradient
   checkpointing, grad clip 1.0, 4 epochs.
4. **Calibrate**: after training, fit one temperature per question type with LBFGS on
   `-(T * log_softmax(Z/T))` and write it into `rl_agent_config.json`. That is where usable
   confidence comes from - do it per (question type, option count), and clamp to a sane range: the
   shipped English config has `choice:11+` = 0.1006, which is exactly the bucket the loader warns
   about.
5. **Artifacts**: `model.safetensors` (fp16) + `encoder/` + `tokenizer/` + `rl_agent_config.json`
   (`fine_tuned: true`, `temperature: [...]`). `laya.Agent("<local output dir>")` loads it directly.

**VRAM/time measured on one 12 GB RTX 4070 SUPER** (`ft_feasibility.py`, real training step, gradient
checkpointing, seq filled to ~max_len):

| max_len / head_max_len | micro batch | s per micro-batch | peak alloc | 60k decisions, 4 epochs |
|---|---|---|---|---|
| 1024 / 256 | 8 | 0.82 | 5564 MiB (6120 reserved) | ~6.8 h |
| 512 / 192 | 8 | 0.35 | 4661 MiB (5332 reserved) | ~2.9 h |
| 1024 / 256 | 16 | 1.61 | 7134 MiB (7706 reserved) | ~6.7 h (no speedup, nearly OOM) |

So a single 12 GB card trains the 421 M-parameter model with micro batch 8; Kaggle is optional. The
throughput matches the vendor's own 2xT4 run (`training` block in their shipped config: 7313 updates,
1 epoch, 1.96 h) - extrapolating 60k decisions gives ~1.7 h/epoch locally.

Pitfalls: warm up before quoting numbers; **toy-length batches lie** (69-token sequences peaked at
4 GB and looked 3x faster than realistic ~930-token ones, so always fill sequences to max_len when
measuring memory/time); the teacher's own self-agreement is the ceiling (the public set's
`label_agreement` shows teacher argmax disagreement on whole rows); a guardrail on Chinese needs
Chinese-labelled data. First milestone: run the public dataset end-to-end before touching your own.

## Jev (cloud) deployed alongside Laya - verified

Both engines are installed side by side in one venv (`typesafe-sdk` 0.7.1 + `laya`), so a question set
can be run against either. Two calling routes, both verified working:

- **SDK**: `from typesafe_sdk import TypeSafeClient; client.system_one(state=..., questions={...})`
  reads `TYPESAFE_API_KEY`; response objects carry `.noul` / `.choice` / `.confidence` / `.usage`.
- **Raw HTTP** (good for a copy-paste self-check): `POST https://api.typesafe.ai/v1/systemone`,
  `Authorization: Bearer <key>`, body `{"state": ..., "model": "jev-latest", "questions": {...}}`,
  response `{"model": "jev-1.13.0", "answers": {...}, "usage": {...}}`. Available models:
  `jev-latest`, `jev-preview`.

**Key handling** (learned the hard way - a masked/stale copy looks identical in chat but 401s):
keep one canonical raw-key file on the machine, never echo the value, never write it into a repo or
skill, and **re-verify with the raw-HTTP call after storing it** (expect HTTP 200 - and confirm the
endpoint is not blanket-200 by checking a bogus key returns 401). This org's key is shared across
agents, so quota is pooled; the raw key file path convention is a `secrets/` dir under the Hermes home.

### Measured: Chinese, same 9 states x 5 questions (ground truth = unambiguous labels)

| engine | department (choice) | urgency (score) | churn | jailbreak | phishing | total | p50 latency |
|---|---|---|---|---|---|---|---|
| **Jev `jev-latest` (API)** | 7/9 | **9/9** | **9/9** | **9/9** | 8/9 | **42/45 (93%)** | 300 ms |
| Laya `multilingual` (local) | 4/9 | 7/9 | 7/9 | 7/9 | **9/9** | 34/45 (76%) | 30 ms |
| Laya `english` (local) | 2/9 | 7/9 | 7/9 | 7/9 | 5/9 | 27/45 (60%) | 25 ms |

So on Chinese the cloud model is clearly ahead (as the vendor's own routing story implies), the local
`multilingual` checkpoint is respectable on detection tasks but weak on Chinese `choice` routing, and
`english` is unusable on Chinese (it read a Chinese jailbreak as 0.91 churn). Cost measured: ~4901
input tokens for those 9 calls = **$0.0002**; at ~550 tokens/call that is roughly **$23 per million
classifications** ($0.042/1M input, output billed but trivial). Local Laya stays $0.

**Guardrail thresholds are official but profile-specific.** In `llms-full.txt` TypeSafe ships a strict
profile `{"review_threshold": 0.35, "action_threshold": 0.70, "severity_block": 2.0}` and a
permissive one (`action_threshold: 0.85`); the confidence-routing pattern instead demonstrates a 0.6
floor with per-action thresholds. Cite the profile you actually adopt, and remember the numbers are
not portable to Laya's entropy confidence.

## Interop with TypeSafe Jev (same category, measured)

Jev (`docs.typesafe.ai`, `pip install typesafe-sdk`, `client.system_one(state=..., questions=...)`)
is the same product class: identical `choice`/`score`/`noul` primitives, identical question schema
(`type` / `instructions` / `criteria`), same RLCD training, same "no text generation" contract. The
request/response JSON is **1:1 portable** - the published Jev request bodies run unmodified on a
local Laya check point (adapter pattern: `<PROJECT_DIR>\jev_compat.py`).

But three measured gaps make a blind swap unsafe:

1. **`confidence` is a different statistic.** Laya = normalised entropy `1 - H(p)/log k`; the TypeSafe
   docs demo `(3*max(p) - 1)/2`. Same field name, different number (0.39 vs 0.67 on one measured
   distribution). Re-calibrate every threshold; never carry one over.
2. **Schema variants that Jev accepts crash Laya.** `criteria: {}` or `criteria: []` →
   `RuntimeError: selected index k out of range`; a missing `criteria` key →
   `AttributeError: 'NoneType' object has no attribute 'items'`. Validate questions before calling.
3. **`criteria` on a `noul` is silently ignored** (Laya's noul options are always `[false, true]`), so
   the Jev idiom of defining what true/false mean buys nothing and fails silently.

Values track in direction but Laya is more conservative on the same inputs (urgency noul 0.76 vs
0.999; category 0.78 vs 0.97; quality score 1.40 vs 1.9), consistent with Jev's better soft
probability matching. Reverse direction: Jev has type-safety guarantees, an SDK + LangChain
middleware ecosystem (model routing, tool-risk gating) and cookbooks worth copying - notably
`typesafe-ai/system-one-adapter-python`, which constrains any LLM to emit Jev-compatible structured
decisions and is a ready-made teacher labeller for the fine-tuning pipeline above.

## laya-guard: three-layer front-end guard, deployed and verified on 50.110

A **Hermes plugin + local service** (not a standalone program) that screens agent input before the
model sees it. Two hooks, both native Hermes plugin hooks - no core patching:

| hook | fires on | action |
|---|---|---|
| `pre_gateway_dispatch` | inbound messages into the **gateway** (Telegram/WeChat/...) | annotate (rewrite with warning prefix) or skip |
| `transform_tool_result` | results of untrusted tools (`web_extract`, `browser_exec`, `mcp_call`, ...) | append a warning block; never blocks the tool |

Layers: ① local Laya `multilingual` gate -> ② narrow regex net (catches Chinese/mild wording the
model scores ambiguously) -> ③ **cloud Jev review only when ①/② are unsure** (grey band or regex hit),
and Jev can also *withdraw* a regex false positive. Service listens on `127.0.0.1:8799` only
(`server.py`), fail-open on every error, `LAYA_GUARD_DISABLE=1` / `enabled: false` as kill switches,
audit log stores `sha8` + scores, never the text.

Measured on 50.110 (RTX 4070 SUPER / Win11), all green:

| check | result |
|---|---|
| `tests/test_hooks.py` | 34 pass / 0 fail / 0 skip |
| `calibrate.py` | false positives 0 / misses 0 |
| `tests/jev_live_check.py` | "all as expected" (Jev round trip 695-753 ms) |
| real end-to-end | a CLI agent fetched an injection page -> `agent.log: annotated web_extract result (prompt_injection=1.00, 343ms)` |
| fail-open, real fault | service killed -> same query still completed (only +1.2 s = the 1.5 s client timeout), no annotation, no error |
| cold start | 7.4 s load (cuda, bfloat16), 13-52 ms/screen afterwards |

The design's real value is layer ②+③, not the local model alone: Chinese "pseudo-authorised, skip the
confirmation" scored **0.092** locally (would pass) -> regex caught it -> Jev **0.86 strong** -> annotated;
the reverse also worked (benign Chinese that scored 0.935 locally -> Jev 0.26 -> annotation withdrawn).

### Deploying it on Windows (the parts the Linux package doesn't cover)

- **Service**: start via a `.vbs` launched by `wscript //B //Nologo` (windowless), registered as a
  **logon-trigger Scheduled Task** — that is this machine's existing convention (`Hermes_Gateway`).
  `New-ScheduledTaskSettingsSet` defaults to a **3-day `ExecutionTimeLimit`, which silently kills a
  resident service** — pass `-ExecutionTimeLimit ([TimeSpan]::Zero)`; mirror `RestartCount 999 /
  PT1M` for crash restart. Reference implementation: `H:\dev\laya\laya-guard.vbs` +
  `run-laya-guard.cmd`.
- **Env paths must be Windows-form** — see `hermes-windows-bash-quirks` "pitfall 8": exporting
  `HERMES_HOME=$HOME/...` from MSYS hands the native process an invalid `/c/...` path, which makes the
  service silently drop the Jev layer (no key) and write its log into a `C:\c\...` junk tree. Verify
  with `/health` -> `jev.configured == true`.
- **`rss_mb` is -1 on Windows** (reads `/proc/self/status`); ignore that field.
- **`sync-jev-key.sh` needs bun + the brain directory** — it does not run on Windows; place the key at
  `%LOCALAPPDATA%\hermes\secrets\typesafe-jev.key` (108 bytes, no trailing newline) by hand.
- **Enabling the plugin needs the app/gateway restarted**; confirm it took by grepping the log for
  `hermes_plugins.laya_guard: laya-guard registered`. Enabling = add the name to `plugins.enabled`
  (use `hermes config set`, keep the existing entries).
- `pre_gateway_dispatch` covers **gateway** inbound only — interactive desktop/CLI input does not pass
  through it, so on a desktop-only box the tool-result layer is the one that actually earns its keep.

### Two corrections to the published package/handoff (both measured, not guessed)

- **A trailing newline does NOT cause HTTP 401.** `$(cat file)`, python `urllib.request` (which strips
  per RFC) both return 200 with a trailing newline present; only a raw embedded newline in the header
  gives **422** (curl refuses to send, exit 23); a **truncated/masked key gives 401**. Normalising to
  108 bytes is still worth doing (one unambiguous checksum across machines) - just don't record 401 as
  its cause, or the next 401 hunt will chase newlines.
- **Published sha256 checklists fail on Windows checkouts.** With `core.autocrlf=true` and no
  `.gitattributes`, all 14 files "mismatch" while the git blob content is byte-identical. Compare
  `git cat-file -p HEAD:<path> | sha256sum`, or ship `.gitattributes` with `* text=auto eol=lf`.

### Privacy knob to decide per machine

`jev.grey_band = [0.90, 0.99]` sends roughly **12% of ordinary content off-box** to `api.typesafe.ai`
(measured on their corpus). On a private desktop that reads mail/browser/private docs, consider
`[0.95, 0.99]` or keeping only `escalate_on_pattern: true`. Cost is negligible (~$23 per million
screens) - the decision is about content leaving the machine, not money.

## Reference

- Repo README carries an "Honest limits" section — read it before promising accuracy.
- Project layout convention used here: venv `H:\dev\venvs\laya`, HF cache `H:\dev\models\hf`,
  launcher + demo scripts `H:\dev\laya\`.
