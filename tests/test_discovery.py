import json

from computer_use_automation.discovery import (
    DiscoveryRunner,
    _safe_decision_for_log,
)
from computer_use_automation.models import (
    ExtractDecision,
    FillDecision,
    FinishDecision,
    Observation,
    RoleLocatorSpec,
)
from computer_use_automation.policy import SafetyPolicy


class FakeSurface:
    def __init__(self) -> None:
        self.filled: list[tuple[object, str, int]] = []
        self.extracted: list[tuple[object, int]] = []

    def goto(self, url: str) -> None:
        pass

    def observe(self) -> Observation:
        return Observation(
            url="http://localhost:8000/",
            title="Test",
            visible_text="Account details loaded",
            accessibility_snapshot="",
        )

    def fill(
        self,
        locator: object,
        value: str,
        timeout_ms: int,
    ) -> None:
        self.filled.append(
            (locator, value, timeout_ms)
        )

    def extract(
        self,
        locator: object,
        timeout_ms: int,
    ) -> str:
        self.extracted.append(
            (locator, timeout_ms)
        )
        return "$1,427.52"

    def click(
        self,
        locator: object,
        timeout_ms: int,
    ) -> None:
        pass

    def text_present(self, text: str) -> bool:
        return text == "Account details loaded"

    def screenshot(self, path: str) -> None:
        pass


class FakeLLM:
    provider_name = "fake"
    model = "fake"

    def __init__(self) -> None:
        self.decisions = [
            FillDecision(
                reasoning="Fill runtime value",
                action="fill",
                locator=RoleLocatorSpec(
                    kind="role",
                    value="textbox",
                    name="Member Number",
                ),
                value="12345",
                record_value="${member_id}",
            ),
            ExtractDecision(
                reasoning="Read dynamic balance",
                action="extract",
                locator=RoleLocatorSpec(
                    kind="role",
                    value="status",
                    name="Savings Balance",
                ),
                output_name="savings_balance",
            ),
            FinishDecision(
                reasoning="Complete",
                action="finish",
                success_text="Account details loaded",
            ),
        ]
        self.histories: list[
            list[dict[str, str]]
        ] = []

    def decide(
        self,
        *,
        goal: str,
        params: dict[str, str],
        observation: Observation,
        history: list[dict[str, str]],
    ):
        self.histories.append(
            [dict(item) for item in history]
        )
        return self.decisions.pop(0)


class FakeLogger:
    def __init__(self) -> None:
        self.rows: list[
            tuple[str, dict[str, object]]
        ] = []

    def write(
        self,
        event: str,
        **payload: object,
    ) -> None:
        self.rows.append(
            (event, payload)
        )


class FakeHandoff:
    def request(self, **kwargs: object) -> None:
        raise AssertionError(
            "Handoff should not be requested"
        )


def test_discovery_executes_fill_and_tracks_output_without_value() -> None:
    surface = FakeSurface()
    llm = FakeLLM()
    logger = FakeLogger()

    runner = DiscoveryRunner(
        surface=surface,
        llm=llm,
        policy=SafetyPolicy({"localhost"}),
        logger=logger,
        handoff=FakeHandoff(),
        max_steps=5,
        action_timeout_ms=5000,
    )

    artifact = runner.run(
        goal=(
            "Look up the member identified by "
            "member_id and return the current "
            "savings balance"
        ),
        target="http://localhost:8000/",
        capability_name="balance_lookup",
        params={"member_id": "12345"},
        business_outcomes=[],
    )

    assert len(surface.filled) == 1
    assert surface.filled[0][1] == "12345"

    assert len(surface.extracted) == 1

    assert llm.histories[1] == [
        {
            "action": "fill",
            "result": "filled",
        }
    ]

    assert llm.histories[2][-1] == {
        "action": "extract",
        "result": (
            "extracted output savings_balance"
        ),
    }

    assert artifact.steps[0].value_template == (
        "${member_id}"
    )
    assert artifact.outputs[0].name == (
        "savings_balance"
    )

    persisted = json.dumps(
        logger.rows,
        default=str,
    )

    assert "12345" not in persisted
    assert "$1,427.52" not in persisted
    assert "Fill runtime value" not in persisted
    assert "Read dynamic balance" not in persisted


def test_safe_fill_log_uses_template_not_runtime_value() -> None:
    decision = FillDecision(
        reasoning="Contains sensitive context",
        action="fill",
        locator=RoleLocatorSpec(
            kind="role",
            value="textbox",
            name="Member Number",
        ),
        value="12345",
        record_value="${member_id}",
    )

    logged = _safe_decision_for_log(
        decision
    )

    serialized = json.dumps(logged)

    assert logged["value_template"] == (
        "${member_id}"
    )
    assert "12345" not in serialized
    assert "Contains sensitive context" not in serialized
