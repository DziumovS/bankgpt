import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from .handoff import HumanHandoff
from .logging_utils import JsonlLogger
from .models import CapabilityArtifact, RecordedStep, ResultStatus, RunResult
from .policy import SafetyPolicy
from .surfaces.base import Surface

PARAM_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class ReplayRunner:
    def __init__(
        self,
        *,
        surface: Surface,
        policy: SafetyPolicy,
        logger: JsonlLogger,
        handoff: HumanHandoff,
        transient_retries: int,
        interactive_handoff: bool,
    ):
        self.surface = surface
        self.policy = policy
        self.logger = logger
        self.handoff = handoff
        self.transient_retries = transient_retries
        self.interactive_handoff = interactive_handoff

    @staticmethod
    def _render_value(
        template: str | None,
        params: dict[str, Any],
    ) -> str:
        if template is None:
            return ""

        match = PARAM_RE.match(template)

        if not match:
            return template

        name = match.group(1)

        if name not in params:
            raise ValueError(
                f"Missing required input parameter: {name}"
            )

        return str(params[name])

    def _check_business_outcome(
        self,
        artifact: CapabilityArtifact,
    ) -> RunResult | None:
        for rule in artifact.business_outcomes:
            if self.surface.text_present(
                rule.text_present
            ):
                return RunResult(
                    status=ResultStatus.BUSINESS_OUTCOME,
                    outcome_code=rule.code,
                    message=rule.message,
                )

        return None

    def _execute_step(
        self,
        step: RecordedStep,
        params: dict[str, Any],
        outputs: dict[str, Any],
    ) -> None:
        if step.action == "wait":
            return

        if step.locator is None:
            raise ValueError(
                f"Step {step.id} requires locator"
            )

        if step.action == "click":
            self.surface.click(
                step.locator,
                step.timeout_ms,
            )

        elif step.action == "fill":
            self.surface.fill(
                step.locator,
                self._render_value(
                    step.value_template,
                    params,
                ),
                step.timeout_ms,
            )

        elif step.action == "extract":
            if not step.output_name:
                raise ValueError(
                    f"Extract step {step.id} "
                    "is missing output_name"
                )

            outputs[step.output_name] = (
                self.surface.extract(
                    step.locator,
                    step.timeout_ms,
                )
            )

        else:
            raise ValueError(
                f"Unsupported replay action: "
                f"{step.action}"
            )

    def run(
        self,
        *,
        artifact: CapabilityArtifact,
        params: dict[str, Any],
    ) -> RunResult:
        url_decision = self.policy.check_url(
            artifact.target_entrypoint
        )

        if not url_decision.allowed:
            return RunResult(
                status=ResultStatus.FAILURE,
                message=url_decision.reason,
            )

        missing = [
            item.name
            for item in artifact.inputs
            if item.required
            and item.name not in params
        ]

        if missing:
            return RunResult(
                status=ResultStatus.FAILURE,
                message=(
                    "Missing required inputs: "
                    + ", ".join(missing)
                ),
            )

        outputs: dict[str, Any] = {}

        self.surface.goto(
            artifact.target_entrypoint
        )

        self.logger.write(
            "replay_started",
            capability=artifact.capability_name,
            params=list(params),
        )

        for step in artifact.steps:
            outcome = self._check_business_outcome(
                artifact
            )

            if outcome:
                self.logger.write(
                    "replay_business_outcome",
                    result=outcome.model_dump(),
                )
                return outcome

            last_error: Exception | None = None
            attempts = self.transient_retries + 1

            for attempt in range(
                1,
                attempts + 1,
            ):
                try:
                    self._execute_step(
                        step,
                        params,
                        outputs,
                    )

                    self.logger.write(
                        "replay_step_ok",
                        step=step.id,
                        attempt=attempt,
                    )

                    last_error = None
                    break

                except PlaywrightError as exc:
                    last_error = exc

                    self.logger.write(
                        "replay_transient_error",
                        step=step.id,
                        attempt=attempt,
                        error=str(exc),
                    )

            if last_error is not None:
                screenshot = (
                    Path("evidence")
                    / f"replay-failure-{step.id}.png"
                )

                self.surface.screenshot(
                    str(screenshot)
                )

                if self.interactive_handoff:
                    record = self.handoff.request(
                        surface=self.surface,
                        reason=(
                            "Replay could not complete "
                            f"{step.id} after retries: "
                            f"{last_error}"
                        ),
                        step_id=step.id,
                    )

                    self.logger.write(
                        "human_handoff_completed",
                        step=step.id,
                        operator_note=(
                            record.operator_note
                        ),
                        before_screenshot=(
                            record.before_screenshot
                        ),
                        after_screenshot=(
                            record.after_screenshot
                        ),
                    )

                    outcome = (
                        self._check_business_outcome(
                            artifact
                        )
                    )

                    if outcome:
                        self.logger.write(
                            "replay_business_outcome",
                            result=(
                                outcome.model_dump()
                            ),
                        )
                        return outcome

                    self.logger.write(
                        "replay_step_completed_by_human",
                        step=step.id,
                    )

                    continue

                result = RunResult(
                    status=ResultStatus.FAILURE,
                    message=(
                        "Hard failure after "
                        "bounded retries."
                    ),
                    failed_step_id=step.id,
                    expected=(
                        f"Step {step.action} "
                        "should complete"
                    ),
                    observed=str(last_error),
                    evidence_path=str(
                        screenshot
                    ),
                )

                self.logger.write(
                    "replay_failed",
                    result=result.model_dump(),
                )

                return result

        outcome = self._check_business_outcome(
            artifact
        )

        if outcome:
            self.logger.write(
                "replay_business_outcome",
                result=outcome.model_dump(),
            )
            return outcome

        if not self.surface.text_present(
            artifact.checkpoint.value
        ):
            screenshot = (
                Path("evidence")
                / "replay-checkpoint-failure.png"
            )

            self.surface.screenshot(
                str(screenshot)
            )

            result = RunResult(
                status=ResultStatus.FAILURE,
                message=(
                    "Checkpoint verification failed."
                ),
                expected=(
                    "Visible text containing "
                    f"{artifact.checkpoint.value!r}"
                ),
                observed=(
                    self.surface.observe()
                    .visible_text[:1_000]
                ),
                evidence_path=str(
                    screenshot
                ),
            )

            self.logger.write(
                "replay_failed",
                result=result.model_dump(),
            )

            return result

        result = RunResult(
            status=ResultStatus.SUCCESS,
            outputs=outputs,
            message=(
                "Deterministic replay completed "
                "and checkpoint verified."
            ),
        )

        self.logger.write(
            "replay_succeeded",
            result=result.model_dump(),
        )

        return result
