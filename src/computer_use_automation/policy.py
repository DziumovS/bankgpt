from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlparse

from .models import AgentDecision


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    requires_human: bool = False
    reason: str = ""


class SafetyPolicy:
    risky_keywords: ClassVar[set[str]] = {
        "delete",
        "remove",
        "transfer",
        "send money",
        "submit payment",
        "confirm purchase",
        "close account",
    }

    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts = allowed_hosts

    def check_url(self, url: str) -> PolicyDecision:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if parsed.scheme not in {"http", "https"}:
            return PolicyDecision(
                False,
                reason=f"Blocked URL scheme: {parsed.scheme}",
            )

        if host not in self.allowed_hosts:
            return PolicyDecision(
                False,
                reason=f"Host {host!r} is not allowlisted",
            )

        return PolicyDecision(True)

    def check_action(self, decision: AgentDecision) -> PolicyDecision:
        if decision.action in {"extract", "wait"}:
            return PolicyDecision(True)

        locator_text = ""

        if decision.action in {"click", "fill"}:
            locator_text = " ".join(
                filter(
                    None,
                    [
                        decision.locator.value,
                        decision.locator.name,
                    ],
                )
            )

        normalized = locator_text.lower()

        risky_by_keyword = any(
            keyword in normalized
            for keyword in self.risky_keywords
        )

        if risky_by_keyword:
            return PolicyDecision(
                allowed=True,
                requires_human=True,
                reason=(
                    "Risky or potentially irreversible UI action "
                    "requires human approval/control."
                ),
            )

        return PolicyDecision(True)