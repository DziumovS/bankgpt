from .models import (
    AgentDecision,
    BusinessOutcomeRule,
    CapabilityArtifact,
    CapabilityInput,
    CapabilityOutput,
    Checkpoint,
    RecordedStep,
)


class CapabilityRecorder:
    def __init__(
        self,
        *,
        capability_name: str,
        description: str,
        target_entrypoint: str,
        params: dict[str, str],
        business_outcomes: list[BusinessOutcomeRule],
    ):
        self.capability_name = capability_name
        self.description = description
        self.target_entrypoint = target_entrypoint
        self.params = params
        self.business_outcomes = business_outcomes
        self.steps: list[RecordedStep] = []
        self.outputs: dict[str, CapabilityOutput] = {}
        self.checkpoint: Checkpoint | None = None

    def record(self, decision: AgentDecision) -> None:
        if decision.action == "finish":
            self.checkpoint = Checkpoint(value=decision.success_text)
            return

        if decision.action == "wait":
            self.steps.append(
                RecordedStep(
                    id=f"step-{len(self.steps) + 1:02d}",
                    action="wait",
                    timeout_ms=1_000,
                )
            )
            return

        value_template: str | None = None
        output_name: str | None = None

        if decision.action == "fill":
            value_template = decision.record_value

            if not value_template:
                for name, concrete_value in self.params.items():
                    if decision.value == concrete_value:
                        value_template = f"${{{name}}}"
                        break
                else:
                    value_template = decision.value

        if decision.action == "extract":
            output_name = decision.output_name

        step = RecordedStep(
            id=f"step-{len(self.steps) + 1:02d}",
            action=decision.action,
            locator=decision.locator,
            value_template=value_template,
            output_name=output_name,
        )

        if decision.action == "extract":
            self.outputs[decision.output_name] = CapabilityOutput(
                name=decision.output_name,
                type="string",
                description=f"Value extracted by {step.id}",
            )

        self.steps.append(step)


    def build(self) -> CapabilityArtifact:
        if self.checkpoint is None:
            raise RuntimeError("Cannot build capability without a success checkpoint")
        return CapabilityArtifact(
            capability_name=self.capability_name,
            description=self.description,
            target_entrypoint=self.target_entrypoint,
            inputs=[
                CapabilityInput(name=name, type="string", description="Runtime discovery parameter")
                for name in self.params
            ],
            outputs=list(self.outputs.values()),
            steps=self.steps,
            checkpoint=self.checkpoint,
            business_outcomes=self.business_outcomes,
            metadata={"locator_preference": ["role", "label", "text", "css"]},
        )
