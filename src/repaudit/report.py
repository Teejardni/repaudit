from typing import Literal
from dataclasses import dataclass


@dataclass
class Report:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    affected: list[str]
    suggested_action: str | None
    project: str
    ecosystem: str

    def __str__(self):
        return f"[{self.code}] {self.message}"
