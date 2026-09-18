from pathlib import Path
from typing import Any

from .handoff import HumanHandoff
from .llm import DecisionClient
from .logging_utils import JsonlLogger
from .models import (
    AgentDecision,
    BusinessOutcomeRule,
    CapabilityArtifact,
)
from .policy import SafetyPolicy
from .recorder import CapabilityRecorder
from .surfaces.base import Surface


def _safe_decision_for_log(
    decision: AgentDecision,
) -> dict[str, Any]:
    if decision.action == "fill":
        return {
            "action": decision.action,
            "locator": decision.locator.model_dump(
                mode="json"
            ),
            "value_template": (
                decision.record_value
                or "[REDACTED]"
            ),
            "risk_hint": decision.risk_hint,
        }

    if decision.action == "click":
        return {
            "action": decision.action,
            "locator": decision.locator.model_dump(
                mode="json"
            ),
            "risk_hint": decision.risk_hint,
        }

    if decision.action == "extract":
        return {
            "action": decision.action,
            "locator": decision.locator.model_dump(
                mode="json"
            ),
            "output_name": decision.output_name,
            "risk_hint": decision.risk_hint,
        }

    if decision.action == "wait":
        return {
            "action": decision.action,
            "risk_hint": decision.risk_hint,
        }

    return {
        "action": decision.action,
        "success_text": decision.success_text,
        "risk_hint": decision.risk_hint,
    }


class DiscoveryRunner:
    def __init__(
        self,
        *,
        surface: Surface,
        llm: DecisionClient,
        policy: SafetyPolicy,
        logger: JsonlLogger,
        handoff: HumanHandoff,
        max_steps: int,
        action_timeout_ms: int,
    ):
        self.surface = surface
        self.llm = llm
        self.policy = policy
        self.logger = logger
        self.handoff = handoff
        self.max_steps = max_steps
        self.action_timeout_ms = action_timeout_ms

    def run(
        self,
        *,
        goal: str,
        target: str,
        capability_name: str,
        params: dict[str, str],
        business_outcomes: list[BusinessOutcomeRule],
    ) -> CapabilityArtifact:
        url_decision = self.policy.check_url(
            target
        )

        if not url_decision.allowed:
            raise RuntimeError(
                url_decision.reason
            )

        recorder = CapabilityRecorder(
            capability_name=capability_name,
            description=goal,
            target_entrypoint=target,
            params=params,
            business_outcomes=business_outcomes,
        )

        history: list[dict[str, str]] = []

        self.surface.goto(target)

        self.logger.write(
            "discovery_started",
            target=target,
            params=list(params),
        )

        for index in range(
            1,
            self.max_steps + 1,
        ):
            observation = (
                self.surface.observe()
            )

            decision = self.llm.decide(
                goal=goal,
                params=params,
                observation=observation,
                history=history,
            )

            self.logger.write(
                "agent_decision",
                step=index,
                url=observation.url,
                decision=(
                    _safe_decision_for_log(
                        decision
                    )
                ),
            )

            policy_decision = (
                self.policy.check_action(
                    decision
                )
            )

            if not policy_decision.allowed:
                raise RuntimeError(
                    policy_decision.reason
                )

            if policy_decision.requires_human:
                self.handoff.request(
                    surface=self.surface,
                    reason=(
                        policy_decision.reason
                    ),
                    step_id=(
                        f"discovery-{index}"
                    ),
                )

                history.append(
                    {
                        "action": (
                            "human_handoff"
                        ),
                        "result": "resumed",
                    }
                )

                continue

            if decision.action == "finish":
                if not self.surface.text_present(
                    decision.success_text
                ):
                    history.append(
                        {
                            "action": "finish",
                            "result": (
                                "checkpoint_not_visible"
                            ),
                        }
                    )
                    continue

                recorder.record(decision)
                artifact = recorder.build()

                self.logger.write(
                    "discovery_succeeded",
                    capability=(
                        artifact.capability_name
                    ),
                    capability_version=(
                        artifact.capability_version
                    ),
                    step_count=len(
                        artifact.steps
                    ),
                    inputs=[
                        item.name
                        for item
                        in artifact.inputs
                    ],
                    outputs=[
                        item.name
                        for item
                        in artifact.outputs
                    ],
                    checkpoint=(
                        artifact.checkpoint
                        .model_dump(
                            mode="json"
                        )
                    ),
                )

                return artifact

            if decision.action == "click":
                self.surface.click(
                    decision.locator,
                    self.action_timeout_ms,
                )
                result = "clicked"

            elif decision.action == "fill":
                self.surface.fill(
                    decision.locator,
                    decision.value,
                    self.action_timeout_ms,
                )
                result = "filled"

            elif decision.action == "extract":
                self.surface.extract(
                    decision.locator,
                    self.action_timeout_ms,
                )
                result = (
                    "extracted output "
                    f"{decision.output_name}"
                )

            elif decision.action == "wait":
                result = "waited"

            else:
                raise RuntimeError(
                    "Unsupported discovery "
                    f"action: {decision.action}"
                )

            recorder.record(decision)

            history.append(
                {
                    "action": decision.action,
                    "result": result,
                }
            )

        screenshot = (
            Path("evidence")
            / "discovery-max-steps.png"
        )

        self.surface.screenshot(
            str(screenshot)
        )

        raise RuntimeError(
            "Discovery exceeded "
            f"max_steps={self.max_steps}"
        )
