# Local LLM hosting with vMLX

`cv-agent` is **BYOK** — it talks to any OpenAI-compatible endpoint. This guide sets up a local
one on Apple Silicon using **[vMLX](https://github.com/jjang-ai/vmlx)**, an MLX-native inference
server (OpenAI/Anthropic-compatible, with continuous batching that helps when the pipeline runs
several requests). You can equally point `cv-agent` at `mlx-lm`, Ollama, or a cloud provider —
nothing below is required, it's just one convenient option.

> Commands below reflect vMLX's official docs at the time of writing. If anything differs, trust
> `vmlx --help` and the [official repo](https://github.com/jjang-ai/vmlx).

## 1. Install

Recommended (isolated, no global pollution):

```bash
brew install uv
uv tool install vmlx
```

(Alternatives: `pipx install vmlx`, or a venv + `pip install vmlx`. On macOS 14+ avoid a bare
`pip install` due to the externally-managed-environment restriction.)

## 2. Get a model (from Hugging Face)

vMLX serves **MLX-format** models straight from Hugging Face — you don't download manually, you
pass a HF model id to `vmlx serve` and it fetches on first run.

- Any model under **`mlx-community/…`** works (thousands available).
- Pre-quantized JANG-format models come from **JANGQ-AI** on Hugging Face.
- You can also pass **your own** HF model id (whatever you host).

### Where do the files go? (matters on a small disk)

vMLX pulls through the standard Hugging Face cache, i.e. **`~/.cache/huggingface/hub`**. A 27B
model is roughly **15–20 GB** (more unquantized), so:

```bash
# Optional: relocate the cache to a bigger disk
export HF_HOME=/Volumes/BigDisk/hf
# Inspect / clean up what you've downloaded
du -sh ~/.cache/huggingface/hub/*
```

> Tip: prefer a quantized (e.g. `-4bit`) build to fit a 27B model comfortably in unified memory
> and on disk.

## 3. Start the server

```bash
# Example with a clean official model:
vmlx serve mlx-community/Qwen3-8B-4bit

# ...or any HF model id you want to host:
vmlx serve <your-org/your-model-id>
```

Defaults to an OpenAI + Anthropic compatible API on **`http://0.0.0.0:8000`**. Useful flags:

```bash
vmlx serve <model-id> --host 127.0.0.1 --port 8000 --api-key sk-local
```

Quick smoke test:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"default","messages":[{"role":"user","content":"Hello!"}]}'
```

## 4. Point cv-agent at it

In your `.env`:

```
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_API_KEY=sk-local          # match --api-key if you set one
LLM_MODEL=<the model id / name vMLX serves>
```

Because access is per-node ([see `.env.example`](../.env.example)), you can keep cheap nodes
(e.g. `STRUCTURE_CV`) on this local server and send only the hardest node (`INTERVIEW`) to a
stronger model — local and cloud are interchangeable.

> Note: `cv-agent` does **not** use the LLM for OCR (Marker does that — see
> [ADR 0001](../docs/adr/0001-marker-ocr-llm-structuring.md)), so the served model only needs to be
> a strong **bilingual text** model. A multimodal model is only needed if you later enable the
> reserved `--ocr-fallback`.
