from computer_use_automation.models import (
    ExtractDecision,
    FillDecision,
    FinishDecision,
    LabelLocatorSpec,
)
from computer_use_automation.recorder import CapabilityRecorder


def test_recorder_parameterizes_fill_and_output() -> None:
    recorder = CapabilityRecorder(
        capability_name="balance_lookup",
        description="Look up a balance",
        target_entrypoint="http://localhost:8000/",
        params={"member_id": "12345"},
        business_outcomes=[],
    )

    recorder.record(
        FillDecision(
            reasoning="Fill member number",
            action="fill",
            locator=LabelLocatorSpec(
                kind="label",
                value="Member Number",
            ),
            value="12345",
            record_value="${member_id}",
        )
    )

    recorder.record(
        ExtractDecision(
            reasoning="Read balance",
            action="extract",
            locator=LabelLocatorSpec(
                kind="label",
                value="Savings Balance",
            ),
            output_name="balance",
        )
    )

    recorder.record(
        FinishDecision(
            reasoning="Goal complete",
            action="finish",
            success_text="Account details loaded",
        )
    )

    artifact = recorder.build()

    assert artifact.steps[0].value_template == "${member_id}"
    assert artifact.outputs[0].name == "balance"
    assert artifact.checkpoint.value == "Account details loaded"
