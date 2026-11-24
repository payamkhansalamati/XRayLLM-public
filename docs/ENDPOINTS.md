# Endpoint metadata and reproducibility caveats

The official [OpenRouter model catalog](https://openrouter.ai/api/v1/models)
was checked on 2026-11-21 without invoking any model. All ten saved endpoint
identifiers were listed with image input support. The table records catalog
metadata at that check, not an assertion about the provider or effective
settings of any historical request. Requested endpoint aliases are retained
in configuration; canonical slugs are informational, not replacements.

| Saved endpoint | Canonical slug at check | Temperature advertised |
|---|---|---|
| `google/gemini-4-neon` | `google/gemini-4-neon-20261118` | Yes |
| `openai/gpt-6.2-astra` | `openai/gpt-6.2-astra-20261117` | No |
| `google/gemini-4-hydrogen` | `google/gemini-4-hydrogen-20261112` | Yes |
| `google/gemini-4-carbon` | `google/gemini-4-carbon-20261110` | Yes |
| `anthropic/claude-fable-5.2` | `anthropic/claude-fable-5.2-20261109` | No |
| `anthropic/claude-sonnet-5.5` | `anthropic/claude-sonnet-5.5-20260928` | No |
| `openai/gpt-6-luna` | `openai/gpt-6-luna-20260922` | No |
| `x-ai/grok-4.20` | `x-ai/grok-4.20-20260309` | Yes |
| `meta-llama/llama-4-maverick` | `meta-llama/llama-4-maverick-17b-128e-instruct` | Yes |
| `meta-llama/llama-4-scout` | `meta-llama/llama-4-scout-17b-16e-instruct` | Yes |

The recorded study requests specified temperature 0.3 for every model. The
catalog did not advertise temperature support for Astra, Luna, Sonnet, or
Fable. Actual effective sampling behavior is therefore not established by
that request field. The release preserves the recorded parameter rather
than silently removing it or substituting a model. Before a new evaluation,
inspect the saved pilot responses and provider errors. Changing parameters
to satisfy a provider constitutes a separately documented protocol variant.

Aliases, routing, default reasoning settings, and capabilities can change.
A passing synthetic pilot establishes limited format/input behavior at that
time; it does not pin weights, prove clinical capability, or ensure a later
request will complete within its token cap.
