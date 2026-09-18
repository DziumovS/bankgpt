# Computer-Use Automation System

A deliberately small end-to-end implementation of the take-home brief:

1. an LLM observes a live UI and chooses actions;
2. a successful discovery run is compiled into a typed, versioned capability artifact;
3. the artifact is replayed deterministically with no LLM in the decision loop;
4. replay distinguishes success, expected business outcomes, bounded transient failures, and hard failures;
5. safety policy enforces target allowlisting and routes risky actions to a human;
6. a human can take over the same live Playwright session and hand control back;
7. structured JSONL logs and screenshots are committed under `evidence/`.

The demo target is a small local legacy-style credit-union UI. The architecture is not tied to that application.

## Architecture

```text
Natural-language goal
        |
        v
   LLM discovery
        |
        v
 observe -> decide -> policy -> act
        |                    |
        |                    v
        |               live UI
        v
CapabilityRecorder
        |
        v
typed/versioned JSON artifact
        |
        v
deterministic ReplayRunner
        |
        +----> outputs
        +----> checkpoint
        +----> business outcome
        +----> bounded retry / hard failure
        +----> optional human handoff
```

Discovery and replay share the `Surface` abstraction. The included implementation uses Playwright, while the recorded artifact contains abstract locator specifications rather than Playwright objects.

## LLM providers

Discovery is local and free by default.

The default provider is Ollama with `qwen3:8b`; no OpenAI account or API key is required. Ollama exposes an OpenAI-compatible local endpoint, allowing the local and optional cloud implementations to use the same `DecisionClient` contract.

Supported discovery providers:

- `ollama` — default, local, no API key;
- `openai` — optional cloud provider requiring an API key.

Replay never constructs or calls a `DecisionClient`.

## Setup

### 1. Install and start Ollama

On macOS:

```bash
brew install --cask ollama
ollama serve
```

Keep the Ollama server running.

In another terminal, pull the model once:

```bash
ollama pull qwen3:8b
```

### 2. Install the project

```bash
uv sync --extra dev
uv run playwright install chromium
cp .env.example .env
```

The supplied `.env.example` selects local discovery:

```dotenv
CUA_LLM_PROVIDER=ollama
CUA_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_API_KEY=
CUA_HEADLESS=false
CUA_ALLOWED_HOSTS=127.0.0.1,localhost
```

Optional Ollama check:

```bash
curl http://127.0.0.1:11434/v1/models
```

## Run the demo target

Terminal 1:

```bash
uv run demo-bank
```

The UI is available at:

```text
http://127.0.0.1:8000/
```

## LLM-driven discovery

Terminal 2:

```bash
uv run computer-use discover \
  --goal "Look up the member identified by member_id and return the current savings balance" \
  --target "http://127.0.0.1:8000/" \
  --name get_member_savings_balance \
  --param member_id=12345 \
  --outcome 'MEMBER_NOT_FOUND|Member not found|No member exists with that number' \
  --output artifacts/get_member_savings_balance.json
```

This is the model-driven path.

For each step the model receives the current live UI observation and recent sanitized action history, then chooses exactly one typed action. The successful run is compiled into:

```text
artifacts/get_member_savings_balance.json
```

The resulting artifact contains three deterministic execution steps:

```text
fill Member Number with ${member_id}
click Search Member
extract Savings Balance -> savings_balance
```

The final discovery `finish` decision becomes the stable checkpoint:

```text
Account details loaded
```

Runtime values and extracted values are not persisted in the discovery JSONL log. The recorded fill step stores `${member_id}` rather than the concrete discovery value.

## Deterministic replay

Replay consumes only the saved artifact and runtime inputs.

```bash
uv run computer-use replay \
  artifacts/get_member_savings_balance.json \
  --param member_id=67890 \
  --evidence-name replay-success
```

Expected output:

```json
{
  "status": "success",
  "outputs": {
    "savings_balance": "$315.08"
  },
  "outcome_code": null,
  "message": "Deterministic replay completed and checkpoint verified."
}
```

### Verify that replay does not use the LLM

Unload the discovery model:

```bash
ollama stop qwen3:8b
ollama ps
```

`ollama ps` should show no loaded model.

Then run replay:

```bash
uv run computer-use replay \
  artifacts/get_member_savings_balance.json \
  --param member_id=67890 \
  --evidence-name replay-success
```

The committed evidence contains a successful replay produced with the model unloaded.

## Expected business outcome

The artifact declares `MEMBER_NOT_FOUND` as an expected business outcome.

```bash
uv run computer-use replay \
  artifacts/get_member_savings_balance.json \
  --param member_id=99999 \
  --evidence-name replay-business-outcome
```

This returns `business_outcome`, not a system failure.

## Hard failure and bounded retry

Replay retries Playwright execution failures a bounded number of times. If the step still cannot execute, replay returns a hard failure with the failed step, expected behavior, observed error, and screenshot evidence.

The committed hard-failure evidence uses an intentionally broken test artifact whose button locator is `Search Member BROKEN`.

Relevant evidence:

```text
evidence/replay-hard-failure.jsonl
evidence/replay-hard-failure-result.json
evidence/replay-failure-step-02.png
```

## Human takeover and hand-back

The same intentionally broken locator is also used to demonstrate real human escalation.

Run:

```bash
uv run computer-use replay \
  evidence/fixtures/get_member_savings_balance_broken.json \
  --param member_id=67890 \
  --interactive-handoff \
  --evidence-name replay-human-handoff
```

After bounded retries are exhausted:

1. automation pauses;
2. the same headed Chromium browser remains open;
3. the operator performs the missing action directly in that browser;
4. the operator presses Enter and records a short note;
5. automation resumes in the same session;
6. the next deterministic step extracts the balance;
7. the final checkpoint is verified.

Committed evidence:

```text
evidence/handoff-20260918T064249Z-before.png
evidence/handoff-20260918T064249Z-after.png
evidence/handoff-20260918T064249Z.json
evidence/replay-human-handoff.jsonl
evidence/replay-human-handoff-result.json
evidence/replay-human-handoff-success.png
```

## Artifact contract

`CapabilityArtifact` contains:

- `schema_version`;
- `capability_name` and `capability_version`;
- typed runtime inputs;
- typed outputs;
- ordered deterministic steps;
- stable locator specifications;
- value templates such as `${member_id}`;
- success checkpoint;
- expected business-outcome rules;
- metadata.

Locator preference is:

```text
role + accessible name
        ↓
label
        ↓
visible text
        ↓
CSS
```

CSS is the last resort.

The artifact is deliberately decoupled from the raw discovery transcript and from the LLM provider.

## Safety and privacy

The prototype includes:

- explicit hostname allowlisting;
- only `http` and `https` target schemes;
- human escalation for risky or potentially irreversible UI actions;
- `.env` excluded from Git;
- recursive redaction of common secret fields in structured logs;
- runtime parameter names rather than values in replay logs;
- parameter templates rather than discovery values in artifacts;
- sanitized discovery decisions without model reasoning, concrete fill values, or extracted values.

The demo member records are synthetic.

## Surface abstraction

`DiscoveryRunner` and `ReplayRunner` depend on the `Surface` interface rather than Playwright directly.

The included `PlaywrightSurface` implements:

- navigation;
- observation;
- role/label/text/CSS locator resolution;
- click;
- fill;
- extract;
- checkpoint text lookup;
- screenshots.

A desktop implementation could provide the same contract using OS accessibility APIs or another UI driver without changing the artifact model or replay semantics.

## Tests and lint

```bash
uv run ruff check .
uv run pytest -v
```

Current test suite:

```text
9 passed
```

Tests cover:

- provider construction;
- OpenAI key validation;
- invalid ARIA-role rejection;
- host allowlisting;
- risky-action escalation;
- artifact parameterization;
- deterministic parameter rendering;
- discovery fill/extract behavior;
- prevention of concrete runtime/extracted values in persisted discovery logs.

## Evidence

Committed evidence is separated by scenario:

### Discovery

```text
evidence/discovery.jsonl
evidence/discovery-success.png
```

### Successful deterministic replay

```text
evidence/replay-success.jsonl
evidence/replay-success-result.json
evidence/replay-success-success.png
```

### Expected business outcome

```text
evidence/replay-business-outcome.jsonl
evidence/replay-business-outcome-result.json
```

### Hard failure

```text
evidence/replay-hard-failure.jsonl
evidence/replay-hard-failure-result.json
evidence/replay-failure-step-02.png
```

### Human handoff

```text
evidence/replay-human-handoff.jsonl
evidence/replay-human-handoff-result.json
evidence/replay-human-handoff-success.png
evidence/handoff-20260918T064249Z-before.png
evidence/handoff-20260918T064249Z-after.png
evidence/handoff-20260918T064249Z.json
```

## Configuration

- `CUA_LLM_PROVIDER` — `ollama` by default.
- `CUA_MODEL` — defaults to `qwen3:8b`.
- `OLLAMA_BASE_URL` — defaults to `http://127.0.0.1:11434/v1`.
- `OPENAI_API_KEY` — unused in local mode; required for the optional OpenAI provider.
- `CUA_HEADLESS` — defaults to `false`; headed mode is required for the interactive handoff demo.
- `CUA_ALLOWED_HOSTS` — comma-separated hostname allowlist.

## Optional OpenAI provider

The project also contains an optional OpenAI `DecisionClient`. Set:

```dotenv
CUA_LLM_PROVIDER=openai
CUA_MODEL=<compatible model>
OPENAI_API_KEY=<your key>
```

The submitted demonstration and evidence use the local Ollama path. The optional cloud path is not required to reproduce the submitted demo.