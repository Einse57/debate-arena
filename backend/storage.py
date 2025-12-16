from __future__ import annotations

from typing import Dict, List, Optional

from models import DebateRun, DebateTemplate, FinalRecord


class InMemoryStore:
    def __init__(self) -> None:
        self.templates: Dict[str, DebateTemplate] = {}
        self.runs: Dict[str, DebateRun] = {}
        self.final_records: List[FinalRecord] = []

    def add_template(self, template: DebateTemplate) -> DebateTemplate:
        self.templates[template.id] = template
        return template

    def get_template(self, template_id: str) -> Optional[DebateTemplate]:
        return self.templates.get(template_id)

    def delete_template(self, template_id: str) -> None:
        self.templates.pop(template_id, None)

    def list_templates(self) -> List[DebateTemplate]:
        return list(self.templates.values())

    def add_run(self, run: DebateRun) -> DebateRun:
        self.runs[run.id] = run
        return run

    def get_run(self, run_id: str) -> Optional[DebateRun]:
        return self.runs.get(run_id)

    def update_run(self, run: DebateRun) -> None:
        self.runs[run.id] = run

    def delete_run(self, run_id: str) -> None:
        self.runs.pop(run_id, None)

    def record_final(self, final: FinalRecord) -> None:
        self.final_records.append(final)

    def list_finals(self) -> List[FinalRecord]:
        return list(self.final_records)
