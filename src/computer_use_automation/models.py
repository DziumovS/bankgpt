from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class LocatorKind(StrEnum):
    ROLE = "role"
    LABEL = "label"
    TEXT = "text"
    CSS = "css"


type AriaRole = Literal[
    "button",
    "cell",
    "checkbox",
    "columnheader",
    "combobox",
    "dialog",
    "grid",
    "gridcell",
    "heading",
    "link",
    "list",
    "listbox",
    "listitem",
    "menu",
    "menuitem",
    "navigation",
    "option",
    "paragraph",
    "radio",
    "region",
    "row",
    "rowgroup",
    "searchbox",
    "status",
    "table",
    "tab",
    "tabpanel",
    "textbox",
]


class RoleLocatorSpec(BaseModel):
    kind: Literal[LocatorKind.ROLE]
    value: AriaRole = Field(
        description=(
            "Exact ARIA role from the accessibility snapshot. "
            "Use 'cell', never 'table cell'."
        )
    )
    name: str | None = Field(
        default=None,
        description=(
            "Accessible name shown in the accessibility snapshot. "
            "Do not use an HTML name attribute as the accessible name."
        ),
    )
    exact: bool = True


class LabelLocatorSpec(BaseModel):
    kind: Literal[LocatorKind.LABEL]
    value: str = Field(
        description="Exact visible label associated with the target control."
    )
    name: None = None
    exact: bool = True


class TextLocatorSpec(BaseModel):
    kind: Literal[LocatorKind.TEXT]
    value: str = Field(
        description="Visible text that identifies the target element."
    )
    name: None = None
    exact: bool = True


class CssLocatorSpec(BaseModel):
    kind: Literal[LocatorKind.CSS]
    value: str = Field(
        description="CSS selector. Use only when a stable accessibility locator is unavailable."
    )
    name: None = None
    exact: bool = True


type LocatorSpec = Annotated[
    RoleLocatorSpec | LabelLocatorSpec | TextLocatorSpec | CssLocatorSpec,
    Field(discriminator="kind"),
]


class DecisionBase(BaseModel):
    reasoning: str = Field(
        description="Short operational reason; never include secrets or full PII."
    )
    risk_hint: Literal["safe", "risky"] = "safe"


class ClickDecision(DecisionBase):
    action: Literal["click"]
    locator: LocatorSpec


class FillDecision(DecisionBase):
    action: Literal["fill"]
    locator: LocatorSpec
    value: str
    record_value: str | None = Field(
        default=None,
        description="Value saved into the capability, e.g. ${member_id}.",
    )


class ExtractDecision(DecisionBase):
    action: Literal["extract"]
    locator: LocatorSpec
    output_name: str


class WaitDecision(DecisionBase):
    action: Literal["wait"]


class FinishDecision(DecisionBase):
    action: Literal["finish"]
    success_text: str


type AgentDecision = Annotated[
    ClickDecision | FillDecision | ExtractDecision | WaitDecision | FinishDecision,
    Field(discriminator="action"),
]


class CapabilityInput(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"] = "string"
    required: bool = True
    description: str = ""


class CapabilityOutput(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"] = "string"
    description: str = ""


class RecordedStep(BaseModel):
    id: str
    action: Literal["click", "fill", "extract", "wait"]
    locator: LocatorSpec | None = None
    value_template: str | None = None
    output_name: str | None = None
    timeout_ms: int = 5_000


class Checkpoint(BaseModel):
    kind: Literal["text_present"] = "text_present"
    value: str


class BusinessOutcomeRule(BaseModel):
    code: str
    text_present: str
    message: str


class CapabilityArtifact(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    capability_name: str
    capability_version: int = 1
    description: str
    target_entrypoint: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inputs: list[CapabilityInput]
    outputs: list[CapabilityOutput]
    steps: list[RecordedStep]
    checkpoint: Checkpoint
    business_outcomes: list[BusinessOutcomeRule] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    url: str
    title: str
    visible_text: str
    accessibility_snapshot: str


class ResultStatus(StrEnum):
    SUCCESS = "success"
    BUSINESS_OUTCOME = "business_outcome"
    FAILURE = "failure"


class RunResult(BaseModel):
    status: ResultStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    outcome_code: str | None = None
    message: str
    failed_step_id: str | None = None
    expected: str | None = None
    observed: str | None = None
    evidence_path: str | None = None


class HandoffRecord(BaseModel):
    reason: str
    step_id: str | None = None
    operator_note: str
    started_at: datetime
    resumed_at: datetime
    before_screenshot: str
    after_screenshot: str