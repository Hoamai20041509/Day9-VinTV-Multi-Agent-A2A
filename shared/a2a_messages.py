from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentHandoff:
    case_id: str
    order_id: str
    source_agent: str
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "order_id": self.order_id,
            "source_agent": self.source_agent,
            "payload": self.payload,
            "warnings": self.warnings,
        }
