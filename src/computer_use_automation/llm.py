import json
from typing import Protocol

from openai import OpenAI
from pydantic import TypeAdapter

from .models import AgentDecision, Observation

AGENT_DECISION_ADAPTER = TypeAdapter(AgentDecision)

SYSTEM_PROMPT = """You are the discovery planner for a computer-use automation system.
You receive a goal, runtime parameters, the current UI observation, and recent history.
Choose exactly one next UI action.

Rules:
- Prefer robust accessibility locators: role+name first, then label, then text. CSS is last resort.
- Never invent an element, role, accessible name, label, or text that is not supported by the current observation.
- For role locators, the role value must exactly match a role shown in the accessibility snapshot.
- For role locators, name means the accessible name shown in the accessibility snapshot. It is not the HTML name attribute.
- Locators recorded during discovery must be reusable with different runtime parameter values and different dynamic output values.
- Never include a runtime parameter value, account/member identifier, balance, amount, date, generated ID, or other dynamic result value in an extract locator when a stable role+name, label, or static text locator exists.
- Do not use a combined visible-text line such as "Savings Balance $1,427.52" as an extract locator when the accessibility snapshot exposes a stable element such as `status "Savings Balance": $1,427.52`.
- When the accessibility snapshot shows an element in the form `role "Stable Name": dynamic value`, extract using that role and stable accessible name. Example: `status "Savings Balance": $1,427.52` must use locator `{"kind":"role","value":"status","name":"Savings Balance"}`.
- A click action requires a locator.
- A fill action requires a locator and the concrete value to type now.
- If a fill value comes from a runtime parameter, put ${parameter_name} in record_value.
- Example: for runtime parameter {"member_id": "12345"}, use value="12345" and record_value="${member_id}".
- An extract action requires a locator and a stable output_name.
- Extract each required output only once.
- Recent history summarizes successfully completed actions without persisting their concrete values.
- If recent history already contains a successful extract, do not extract the same required output again.
- After all information required by the goal has been successfully extracted, use finish.
- Use finish only when the goal is satisfied.
- finish.success_text must be stable visible text from the current observation that replay can verify.
- Prefer a stable completion message such as "Account details loaded" over dynamic data such as a balance or member number.
- Never use finish merely because a page loaded if required outputs have not yet been extracted.
- Keep reasoning short and operational. Do not repeat secrets or full sensitive data.
- Mark only actions that may be irreversible or security-sensitive as risk_hint="risky".
- Ordinary search, navigation, fill, wait, and read-only extraction actions are always safe.
- Never mark extract or wait as risky.
- Return only data matching the supplied JSON schema.
"""


class DecisionClient(Protocol):
    provider_name: str
    model: str

    def decide(
        self,
        *,
        goal: str,
        params: dict[str, str],
        observation: Observation,
        history: list[dict[str, str]],
    ) -> AgentDecision: ...


def _payload(
    goal: str,
    params: dict[str, str],
    observation: Observation,
    history: list[dict[str, str]],
) -> str:
    return json.dumps(
        {
            "goal": goal,
            "runtime_parameters": params,
            "observation": observation.model_dump(),
            "recent_history": history[-8:],
        },
        ensure_ascii=False,
    )


class OllamaDecisionClient:
    """Local/free discovery client using Ollama's OpenAI-compatible HTTP API."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
    ):
        self.client = OpenAI(
            base_url=base_url.rstrip("/") + "/",
            api_key="ollama",
        )
        self.model = model

    def decide(
        self,
        *,
        goal: str,
        params: dict[str, str],
        observation: Observation,
        history: list[dict[str, str]],
    ) -> AgentDecision:
        schema = AGENT_DECISION_ADAPTER.json_schema()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": _payload(
                        goal,
                        params,
                        observation,
                        history,
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_decision",
                    "strict": True,
                    "schema": schema,
                },
            },
            temperature=0,
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Local model returned an empty decision"
            )

        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Local model returned invalid JSON"
            ) from exc

        return AGENT_DECISION_ADAPTER.validate_python(
            raw
        )


class OpenAIDecisionClient:
    """Optional paid/cloud discovery client using structured JSON output."""

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
    ):
        self.client = OpenAI(
            api_key=api_key
        )
        self.model = model

    def decide(
        self,
        *,
        goal: str,
        params: dict[str, str],
        observation: Observation,
        history: list[dict[str, str]],
    ) -> AgentDecision:
        schema = AGENT_DECISION_ADAPTER.json_schema()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": _payload(
                        goal,
                        params,
                        observation,
                        history,
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "agent_decision",
                    "strict": True,
                    "schema": schema,
                },
            },
            temperature=0,
        )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Cloud model returned an empty decision"
            )

        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Cloud model returned invalid JSON"
            ) from exc

        return AGENT_DECISION_ADAPTER.validate_python(
            raw
        )


def build_decision_client(
    *,
    provider: str,
    model: str,
    ollama_base_url: str,
    openai_api_key: str | None,
) -> DecisionClient:
    normalized = provider.strip().lower()

    if normalized == "ollama":
        return OllamaDecisionClient(
            base_url=ollama_base_url,
            model=model,
        )

    if normalized == "openai":
        if not openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when "
                "CUA_LLM_PROVIDER=openai. "
                "Use CUA_LLM_PROVIDER=ollama for "
                "the default free/local mode."
            )

        return OpenAIDecisionClient(
            api_key=openai_api_key,
            model=model,
        )

    raise RuntimeError(
        "Unsupported "
        f"CUA_LLM_PROVIDER={provider!r}; "
        "use 'ollama' or 'openai'"
    )
