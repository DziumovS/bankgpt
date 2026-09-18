from computer_use_automation.replay import ReplayRunner


def test_render_value() -> None:
    assert ReplayRunner._render_value("${member_id}", {"member_id": "67890"}) == "67890"
    assert ReplayRunner._render_value("literal", {}) == "literal"
