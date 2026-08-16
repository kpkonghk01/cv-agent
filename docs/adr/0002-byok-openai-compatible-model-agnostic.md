# BYOK via OpenAI-compatible API, model-agnostic, per-node override

The product never ships, mandates, or depends on any specific model or provider. Every LLM node talks to an OpenAI-compatible endpoint described by `(base_url, api_key, model_name)`. Configuration is a single default set in `.env`, with optional **per-node overrides** so an individual node (CV structuring, JD→Rubric, Screening, Interview) can point at a different model or even a different provider. A local runtime such as vMLX or `mlx-lm` is just another `base_url`; a cloud provider is another. The operator chooses; the code is indifferent.

## Considered Options

- **OpenAI-compatible BYOK, per-node override (chosen).** Maximum portability; local and cloud are interchangeable; no vendor lock-in. A future reader might wonder why we don't use provider-native SDKs or LangChain provider integrations — the answer is deliberate model/provider indifference.
- **Provider-native SDKs / hardcoded provider.** Rejected: couples the product to a vendor and blocks the local-hosting and BYOK requirements.

## Consequences

- Whatever model the operator points a node at (including uncensored/de-aligned local models) is the operator's responsibility; screening quality and bias follow the operator's model choice, not the product.
- The product must degrade gracefully across models of differing capability (e.g. enforce structured output via schema + validation + retry rather than trusting any single model's JSON discipline).
