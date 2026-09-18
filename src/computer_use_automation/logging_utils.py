import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def redact(value: Any) -> Any:
    """Conservative recursive redaction for logs/evidence."""
    sensitive_keys = {
        "password",
        "token",
        "secret",
        "authorization",
        "api_key",
        "ssn",
    }

    if isinstance(value, dict):
        out: dict[str, Any] = {}

        for key, item in value.items():
            if key.lower() in sensitive_keys:
                out[key] = "[REDACTED]"
            else:
                out[key] = redact(item)

        return out

    if isinstance(value, list):
        return [redact(item) for item in value]

    return value


class JsonlLogger:
    def __init__(
        self,
        path: Path,
        *,
        truncate: bool = False,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

        if truncate:
            self.path.write_text("", encoding="utf-8")

    def write(
        self,
        event: str,
        **payload: Any,
    ) -> None:
        row = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **redact(payload),
        }

        with self.path.open(
            "a",
            encoding="utf-8",
        ) as fh:
            fh.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
