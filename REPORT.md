# 1. Architecture

The implementation is intentionally a small single-process vertical slice rather than a distributed automation platform.

The system has two distinct execution modes.

During **discovery**, a `DecisionClient` receives a natural-language goal, runtime parameters, a bounded live UI observation, and recent sanitized action history. The observation contains visible text, an accessibility snapshot, and current form-control state. The LLM chooses exactly one typed `AgentDecision`. `DiscoveryRunner` applies the safety policy, executes the action through the `Surface` abstraction, and passes the successful decision to `CapabilityRecorder`.

A successful discovery run is therefore compiled into a reusable `CapabilityArtifact`. The artifact is not a raw transcript and does not contain model reasoning.

During **replay**, `ReplayRunner` loads the artifact and executes its ordered steps directly through `Surface`. No `DecisionClient` is created or called. The submitted evidence includes a successful replay after `qwen3:8b` was explicitly unloaded from Ollama.

The primary abstraction boundary is `Surface`. Both discovery and replay depend on navigation, observation, locator-based actions, extraction, checkpoint lookup, and screenshots rather than directly depending on Playwright. `PlaywrightSurface` is the browser implementation.

The LLM boundary is also provider-neutral. `DecisionClient` is a small protocol. The submitted demo uses local Ollama with `qwen3:8b`; an optional OpenAI implementation uses the same typed decision contract.

# 2. Artifact schema

`CapabilityArtifact` is a typed and versioned Pydantic model.

It contains:

- schema version;
- capability name and capability version;
- description and target entrypoint;
- typed inputs;
- typed outputs;
- ordered deterministic steps;
- locator specifications;
- value templates;
- success checkpoint;
- expected business-outcome rules;
- metadata.

The submitted artifact records the discovered flow as three execution steps:

1. fill the `Member Number` textbox with `${member_id}`;
2. click the `Search Member` button;
3. extract the `Savings Balance` status into `savings_balance`.

The successful discovery `finish` decision produces the stable checkpoint `Account details loaded`.

Runtime discovery values are normalized before becoming part of the capability. For example, the concrete member number used during discovery is not stored in the fill step; `${member_id}` is stored instead. The same artifact can therefore replay with another member ID.

Locators prefer accessibility role plus accessible name, followed by label, visible text, and finally CSS. The artifact contains locator data rather than Playwright objects or generated coordinates.

The schema constrains ARIA roles to an explicit set. This prevents malformed model output such as an invented `table cell` role from becoming part of an artifact.

# 3. Determinism & error handling

Replay contains no model decision loop.

For each recorded step, `ReplayRunner` resolves runtime templates, executes the recorded action, and captures declared outputs. At the end it verifies the recorded checkpoint before returning success.

The submitted successful replay uses `member_id=67890`, even though discovery used a different value. It returns `savings_balance=$315.08`.

To demonstrate that this is genuinely model-free replay, `qwen3:8b` was unloaded with `ollama stop qwen3:8b`, `ollama ps` showed no loaded model, and the same artifact still replayed successfully.

Replay distinguishes three result classes.

**Success** means all deterministic steps completed and the checkpoint was verified.

**Business outcome** means the UI reached a known, expected domain state. The artifact declares `MEMBER_NOT_FOUND`; replay with an unknown member therefore returns `business_outcome` instead of treating it as an automation defect.

**Failure** means deterministic execution could not satisfy the capability. Playwright execution errors are treated as recoverable transient conditions and retried a bounded number of times. After the retry budget is exhausted, replay produces a hard failure containing the failed step, expected behavior, observed error, and screenshot evidence.

There is no open-ended LLM recovery during replay. This is deliberate: once a capability has been recorded, replay behavior remains bounded and inspectable.

# 4. Heterogeneity & multi-tenant

The `Surface` interface is the boundary between capability semantics and UI technology.

The browser implementation uses Playwright and accessibility-oriented locators. Another browser adapter could add frame-aware or application-specific targeting while preserving the same artifact contract. A desktop implementation could map the same operations to OS accessibility APIs or another desktop UI driver.

The artifact itself does not contain Playwright `Page`, `Locator`, browser-context objects, or browser-specific execution code.

For a multi-tenant production system, I would add explicit application identity, tenant identity, application version, and artifact variant metadata. The discovered base capability would remain immutable. Tenant- or version-specific differences would be represented as reviewed overlays or new capability versions rather than silently mutating the base artifact.

Replay telemetry could track locator success and checkpoint success by application version and tenant. Repeated instability would then trigger review or rediscovery rather than allowing individual replay runs to improvise with a model.

This keeps the reusable capability contract separate from tenant-specific UI drift.

# 5. Escalation & handoff

The handoff implementation uses the same live browser session.

When handoff is requested:

1. automation captures a before screenshot;
2. automation pauses;
3. the existing headed Chromium browser/context/page remains alive;
4. the operator performs the required action directly in that browser;
5. the operator explicitly returns control from the terminal;
6. an operator note and after screenshot are recorded;
7. automation continues in the same session.

This mechanism is available for policy-classified risky actions during discovery and, when `--interactive-handoff` is enabled, after deterministic replay exhausts its retry budget.

The submitted replay handoff evidence intentionally uses a broken `Search Member BROKEN` locator. Automated execution fails three times. The operator then clicks the real `Search Member` button in the already-open browser. Control is returned to replay, which executes the next recorded extraction step and verifies the final checkpoint.

The prototype therefore demonstrates takeover and hand-back rather than restarting the task in a separate browser.

A production implementation would replace terminal coordination with an operator service and explicit session/control leases. It would also attach an explicit postcondition to each step so automation could verify the exact state produced by a manually completed failed step before continuing.

# 6. Safety

Targets are checked before navigation. Only `http` and `https` schemes are accepted, and the target hostname must be present in the configured allowlist.

Potentially irreversible UI actions are not silently executed. The policy uses action type plus conservative locator-keyword detection to route actions such as deletion, money transfer, payment submission, purchase confirmation, or account closure to human control.

The prototype also minimizes persisted sensitive data.

`.env` is excluded from Git. Runtime parameter values are not written to replay-start logs. Discovery logs persist parameter names rather than values. Logged discovery decisions omit model reasoning and concrete fill values. Parameterized fills persist templates such as `${member_id}`. Extracted dynamic values are not written into discovery history or discovery logs.

The artifact is also decoupled from the raw LLM transcript and does not persist model reasoning.

The recursive logger redacts common secret-key names as an additional defense.

The local demo uses synthetic member data only.

# 7. Cuts

I deliberately did not build databases, queues, distributed workers, a browser-control service, desktop automation, a polished co-browsing UI, automatic tenant overlays, or LLM-based replay recovery.

Those components would add breadth but are not required to demonstrate the load-bearing design:

- genuine model-driven UI discovery;
- compilation into a reusable typed artifact;
- deterministic model-free replay;
- explicit outputs and success checkpoint;
- expected business outcomes;
- bounded retries and hard failures;
- safety policy;
- same-session human takeover and hand-back;
- structured evidence.

The current evidence uses JSONL logs and screenshots rather than full Playwright traces.

The next production-oriented additions would be artifact approval states, per-step postconditions, locator fallback sets with confidence metadata, Playwright trace capture, an operator control service, and stability testing across multiple UI variants.