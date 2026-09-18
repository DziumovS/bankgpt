from datetime import UTC, datetime
from pathlib import Path

from .models import HandoffRecord
from .surfaces.base import Surface


class HumanHandoff:
    """Minimal real handoff: pause automation, human uses the same headed browser, then resume."""

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def request(self, *, surface: Surface, reason: str, step_id: str | None) -> HandoffRecord:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        before = self.evidence_dir / f"handoff-{stamp}-before.png"
        after = self.evidence_dir / f"handoff-{stamp}-after.png"
        surface.screenshot(str(before))
        started_at = datetime.now(UTC)

        print("\n=== HUMAN HANDOFF ===")
        print(reason)
        print("The automation is PAUSED. Use the already-open browser window directly.")
        input("When your manual action is complete, press Enter here to hand control back... ")
        note = input("Short operator note describing what you did: ").strip() or "manual intervention"

        resumed_at = datetime.now(UTC)
        surface.screenshot(str(after))
        record = HandoffRecord(
            reason=reason,
            step_id=step_id,
            operator_note=note,
            started_at=started_at,
            resumed_at=resumed_at,
            before_screenshot=str(before),
            after_screenshot=str(after),
        )
        record_path = self.evidence_dir / f"handoff-{stamp}.json"
        record_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record
