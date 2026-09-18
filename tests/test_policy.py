from computer_use_automation.models import ClickDecision, RoleLocatorSpec
from computer_use_automation.policy import SafetyPolicy


def test_blocks_non_allowlisted_host() -> None:
    policy = SafetyPolicy({"localhost"})
    decision = policy.check_url("https://example.com")
    assert decision.allowed is False


def test_risky_keyword_requires_human() -> None:
    policy = SafetyPolicy({"localhost"})

    action = ClickDecision(
        reasoning="Potentially irreversible",
        action="click",
        locator=RoleLocatorSpec(
            kind="role",
            value="button",
            name="Delete account",
        ),
    )

    decision = policy.check_action(action)

    assert decision.allowed is True
    assert decision.requires_human is True
