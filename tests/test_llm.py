import pytest
from pydantic import ValidationError

from computer_use_automation.llm import (
    AGENT_DECISION_ADAPTER,
    OllamaDecisionClient,
    build_decision_client,
)


def test_local_ollama_is_constructible_without_api_key():
    client = build_decision_client(
        provider="ollama",
        model="qwen3:8b",
        ollama_base_url=(
            "http://127.0.0.1:11434/v1"
        ),
        openai_api_key=None,
    )

    assert isinstance(
        client,
        OllamaDecisionClient,
    )
    assert client.provider_name == "ollama"


def test_openai_requires_key():
    with pytest.raises(
        RuntimeError,
        match="OPENAI_API_KEY",
    ):
        build_decision_client(
            provider="openai",
            model="example-cloud-model",
            ollama_base_url=(
                "http://127.0.0.1:11434/v1"
            ),
            openai_api_key=None,
        )


def test_invalid_aria_role_is_rejected():
    with pytest.raises(ValidationError):
        AGENT_DECISION_ADAPTER.validate_python(
            {
                "reasoning": "Read balance",
                "action": "extract",
                "locator": {
                    "kind": "role",
                    "value": "table cell",
                    "name": "Savings Balance",
                },
                "output_name": (
                    "savings_balance"
                ),
            }
        )
