from dataclasses import dataclass


@dataclass
class JobSpec:
    project_id: str
    description: str | None = None
