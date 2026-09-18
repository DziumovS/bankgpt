import json
from pathlib import Path
from typing import Annotated

import typer

from .config import settings
from .discovery import DiscoveryRunner
from .handoff import HumanHandoff
from .llm import build_decision_client
from .logging_utils import JsonlLogger
from .models import BusinessOutcomeRule, CapabilityArtifact
from .policy import SafetyPolicy
from .replay import ReplayRunner
from .surfaces import PlaywrightSurface

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def parse_pairs(
    items: list[str],
) -> dict[str, str]:
    parsed: dict[str, str] = {}

    for item in items:
        if "=" not in item:
            raise typer.BadParameter(
                f"Expected NAME=VALUE, got: {item}"
            )

        key, value = item.split("=", 1)
        parsed[key.strip()] = value

    return parsed


def parse_outcomes(
    items: list[str],
) -> list[BusinessOutcomeRule]:
    rules: list[BusinessOutcomeRule] = []

    for item in items:
        parts = item.split("|", 2)

        if len(parts) != 3:
            raise typer.BadParameter(
                "Outcome must be CODE|VISIBLE_TEXT|MESSAGE"
            )

        rules.append(
            BusinessOutcomeRule(
                code=parts[0],
                text_present=parts[1],
                message=parts[2],
            )
        )

    return rules


@app.command()
def discover(
    goal: str = typer.Option(
        ...,
        help="Natural-language goal.",
    ),
    target: str = typer.Option(
        "http://127.0.0.1:8000/",
        help="Target entry URL.",
    ),
    name: str = typer.Option(
        "get_member_savings_balance",
        help="Capability name.",
    ),
    param: Annotated[
        list[str] | None,
        typer.Option(
            "--param",
            help="Runtime param as NAME=VALUE; repeatable.",
        ),
    ] = None,
    outcome: Annotated[
        list[str] | None,
        typer.Option(
            "--outcome",
            help=(
                "Business outcome as "
                "CODE|VISIBLE_TEXT|MESSAGE; repeatable."
            ),
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(),
    ] = Path(
        "artifacts/get_member_savings_balance.json"
    ),
) -> None:
    params = parse_pairs(param or [])
    outcomes = parse_outcomes(outcome or [])

    settings.evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = JsonlLogger(
        settings.evidence_dir / "discovery.jsonl",
        truncate=True,
    )

    policy = SafetyPolicy(
        settings.allowed_hosts
    )

    handoff = HumanHandoff(
        settings.evidence_dir
    )

    llm = build_decision_client(
        provider=settings.llm_provider,
        model=settings.model,
        ollama_base_url=settings.ollama_base_url,
        openai_api_key=settings.openai_api_key,
    )

    typer.echo(
        f"Discovery LLM: "
        f"{llm.provider_name} / {llm.model}"
    )

    with PlaywrightSurface(
        headless=settings.headless,
        action_timeout_ms=(
            settings.action_timeout_ms
        ),
    ) as surface:
        runner = DiscoveryRunner(
            surface=surface,
            llm=llm,
            policy=policy,
            logger=logger,
            handoff=handoff,
            max_steps=settings.max_steps,
            action_timeout_ms=(
                settings.action_timeout_ms
            ),
        )

        artifact = runner.run(
            goal=goal,
            target=target,
            capability_name=name,
            params=params,
            business_outcomes=outcomes,
        )

        output.write_text(
            artifact.model_dump_json(
                indent=2
            ),
            encoding="utf-8",
        )

        surface.screenshot(
            str(
                settings.evidence_dir
                / "discovery-success.png"
            )
        )

    typer.echo(
        f"Saved artifact: {output}"
    )


@app.command()
def replay(
    artifact_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
        ),
    ],
    param: Annotated[
        list[str] | None,
        typer.Option(
            "--param",
            help="Runtime param as NAME=VALUE; repeatable.",
        ),
    ] = None,
    interactive_handoff: Annotated[
        bool,
        typer.Option(
            "--interactive-handoff",
            help=(
                "Allow operator takeover "
                "after hard failure."
            ),
        ),
    ] = False,
    evidence_name: Annotated[
        str,
        typer.Option(
            "--evidence-name",
            help=(
                "Evidence file prefix for this replay run."
            ),
        ),
    ] = "replay",
) -> None:
    artifact = CapabilityArtifact.model_validate_json(
        artifact_path.read_text(
            encoding="utf-8"
        )
    )

    params = parse_pairs(param or [])

    settings.evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = JsonlLogger(
        settings.evidence_dir
        / f"{evidence_name}.jsonl",
        truncate=True,
    )

    policy = SafetyPolicy(
        settings.allowed_hosts
    )

    handoff = HumanHandoff(
        settings.evidence_dir
    )

    with PlaywrightSurface(
        headless=settings.headless,
        action_timeout_ms=(
            settings.action_timeout_ms
        ),
    ) as surface:
        runner = ReplayRunner(
            surface=surface,
            policy=policy,
            logger=logger,
            handoff=handoff,
            transient_retries=(
                settings.transient_retries
            ),
            interactive_handoff=(
                interactive_handoff
            ),
        )

        result = runner.run(
            artifact=artifact,
            params=params,
        )

        result_path = (
            settings.evidence_dir
            / f"{evidence_name}-result.json"
        )

        result_path.write_text(
            result.model_dump_json(
                indent=2
            ),
            encoding="utf-8",
        )

        if result.status == "success":
            surface.screenshot(
                str(
                    settings.evidence_dir
                    / f"{evidence_name}-success.png"
                )
            )

    typer.echo(
        json.dumps(
            result.model_dump(
                mode="json"
            ),
            indent=2,
            default=str,
        )
    )

    if result.status == "failure":
        raise typer.Exit(code=1)
