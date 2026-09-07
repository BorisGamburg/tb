from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    status: str
    executed: bool
