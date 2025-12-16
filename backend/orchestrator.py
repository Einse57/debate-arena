from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from assistant_builder_client import AssistantBuilderClient
from models import (
    AdvanceDebateResponse,
    DebateRun,
    DebateTemplate,
    FinalRecord,
    PhaseOutput,
    PhaseRole,
    RoundOutcome,
    RoundResult,
    RunMode,
    RunStatus,
    StartDebateRequest,
    VisibleTo,
    VoteResult,
    VoteValue,
)
from storage import InMemoryStore


@dataclass
class RunContext:
    template: DebateTemplate
    total_rounds: int


class DebateOrchestrator:
    def __init__(self, store: InMemoryStore, client: AssistantBuilderClient) -> None:
        self.store = store
        self.client = client
        self._progress: Dict[str, Tuple[int, int]] = {}
        self._context: Dict[str, RunContext] = {}
        self._tasks: List[asyncio.Task] = []

    async def start_debate(self, payload: StartDebateRequest) -> DebateRun:
        template = self.store.get_template(payload.template_id)
        if not template:
            raise ValueError("template not found")

        topic = payload.topic or template.topic
        total_rounds = payload.rounds or template.rounds

        run = DebateRun(
            template_id=template.id,
            title=template.name,
            topic=topic,
            status=RunStatus.running,
            mode=payload.mode,
        )
        self.store.add_run(run)
        self._context[run.id] = RunContext(template=template, total_rounds=total_rounds)
        self._progress[run.id] = (0, 0)

        if payload.mode == RunMode.auto:
            task = asyncio.create_task(self._run_to_completion(run.id))
            self._track(task)
            return run

        return run

    async def _run_to_completion(self, run_id: str) -> DebateRun:
        ctx = self._context.get(run_id)
        run = self.store.get_run(run_id)
        if not ctx or not run:
            raise ValueError("debate not found")

        for _ in range(ctx.total_rounds):
            await self._execute_round(run_id)

        await self._finalize(run_id)
        final_run = self.store.get_run(run_id) or run
        final_copy = final_run.model_copy(deep=True)
        final_copy.status = RunStatus.completed
        return final_copy

    def _track(self, task: asyncio.Task) -> None:
        self._tasks.append(task)

        def _done(_):
            try:
                self._tasks.remove(task)
            except ValueError:
                pass

        task.add_done_callback(_done)

    async def advance_debate(self, run_id: str) -> AdvanceDebateResponse:
        ctx = self._context.get(run_id)
        run = self.store.get_run(run_id)
        if not ctx or not run:
            raise ValueError("debate not found")
        if run.mode != RunMode.step:
            raise ValueError("debate not in step mode")
        if run.status in {RunStatus.completed, RunStatus.failed, RunStatus.canceled}:
            return AdvanceDebateResponse(debate=run, done=True)

        await self._execute_phase_step(run_id)

        done = run.status in {RunStatus.completed, RunStatus.failed, RunStatus.canceled}
        return AdvanceDebateResponse(debate=run, done=done)

    async def cancel(self, run_id: str) -> DebateRun:
        run = self.store.get_run(run_id)
        if not run:
            raise ValueError("debate not found")
        run.status = RunStatus.canceled
        self.store.update_run(run)
        self._progress.pop(run_id, None)
        self._context.pop(run_id, None)
        return run

    async def _execute_round(self, run_id: str) -> None:
        ctx = self._context.get(run_id)
        run = self.store.get_run(run_id)
        if not ctx or not run:
            return

        round_index = len(run.rounds) + 1
        round_result = self._get_or_create_round(run, round_index)
        template = ctx.template

        for phase in template.phases:
            outputs = await self._execute_phase(template, phase, run, round_index, round_result)
            if phase.role == PhaseRole.vote:
                votes, outcome = self._tally_votes(outputs)
                round_result.votes = votes
                round_result.outcome = outcome
                self.store.update_run(run)

        if template.moderator:
            summary = await self._moderator_summary(template, run, round_result)
            round_result.moderator_summary = summary
            self.store.update_run(run)

    async def _execute_phase_step(self, run_id: str) -> None:
        ctx = self._context.get(run_id)
        run = self.store.get_run(run_id)
        if not ctx or not run:
            return

        round_idx, phase_idx = self._progress[run_id]
        if round_idx >= ctx.total_rounds:
            await self._finalize(run_id)
            return

        round_number = round_idx + 1
        template = ctx.template

        if round_idx >= len(run.rounds):
            run.rounds.append(RoundResult(round_index=round_number))

        phase = template.phases[phase_idx]
        round_result = run.rounds[round_idx]
        outputs = await self._execute_phase(template, phase, run, round_number, round_result)

        if phase.role == PhaseRole.vote:
            votes, outcome = self._tally_votes(outputs)
            run.rounds[round_idx].votes = votes
            run.rounds[round_idx].outcome = outcome

        if phase_idx == len(template.phases) - 1:
            if template.moderator:
                summary = await self._moderator_summary(template, run, run.rounds[round_idx])
                run.rounds[round_idx].moderator_summary = summary
            round_idx += 1
            phase_idx = 0
        else:
            phase_idx += 1

        self._progress[run_id] = (round_idx, phase_idx)
        self.store.update_run(run)

        if round_idx >= ctx.total_rounds:
            await self._finalize(run_id)

    async def _execute_phase(
        self,
        template: DebateTemplate,
        phase,
        run: DebateRun,
        round_index: int,
        round_result: RoundResult,
    ) -> List[PhaseOutput]:
        async def run_one(participant):
            try:
                messages = self._build_messages(template, participant.persona_prompt, phase, run, round_index)
                raw = await self.client.chat(participant.model_id, messages)
            except Exception as exc:
                raw = f"(error: {exc})"
            return participant, raw

        tasks: List[asyncio.Task] = [asyncio.create_task(run_one(p)) for p in template.participants]

        outputs: List[PhaseOutput] = []
        for coro in asyncio.as_completed(tasks):
            participant, raw = await coro
            po = PhaseOutput(
                phase_id=phase.id,
                participant_id=participant.id,
                output=raw,
            )
            outputs.append(po)
            round_result.phase_outputs.append(po)
            self.store.update_run(run)

        return outputs

    def _get_or_create_round(self, run: DebateRun, round_index: int) -> RoundResult:
        if len(run.rounds) < round_index:
            run.rounds.append(RoundResult(round_index=round_index))
            self.store.update_run(run)
        return run.rounds[round_index - 1]

    async def _moderator_summary(
        self, template: DebateTemplate, run: DebateRun, round_result: RoundResult
    ) -> str:
        moderator = template.moderator
        if not moderator:
            return ""
        messages = [
            {
                "role": "system",
                "content": moderator.persona_prompt,
            },
            {
                "role": "user",
                "content": f"Topic: {run.topic}\nRound {round_result.round_index} summary requested.",
            },
        ]
        return await self.client.chat(moderator.model_id, messages)

    def _tally_votes(self, outputs: List[PhaseOutput]) -> Tuple[List[VoteResult], RoundOutcome]:
        votes: List[VoteResult] = []
        yes_count = 0
        no_count = 0
        for output in outputs:
            parsed = self._parse_vote(output.output)
            votes.append(
                VoteResult(
                    participant_id=output.participant_id,
                    raw_output=output.output,
                    parsed_vote=parsed,
                )
            )
            if parsed == VoteValue.yes:
                yes_count += 1
            elif parsed == VoteValue.no:
                no_count += 1

        if yes_count > no_count:
            outcome = RoundOutcome.yes
        elif no_count > yes_count:
            outcome = RoundOutcome.no
        elif yes_count == no_count and yes_count > 0:
            outcome = RoundOutcome.tie
        else:
            outcome = RoundOutcome.invalid

        return votes, outcome

    def _parse_vote(self, raw: str) -> VoteValue:
        if not raw:
            return VoteValue.invalid

        first_line = raw.strip().splitlines()[0]
        # Remove common leading markers before parsing (bullets, arrows, etc.).
        cleaned = first_line.lstrip("-*•> \t").strip()
        cleaned_lower = cleaned.lower()

        # Accept variants like "Vote: YES", "my vote - no", or "yes, because...".
        match = re.match(r"^(?:vote|my vote|i vote)?\s*[:\-]?\s*(yes|no)\b", cleaned_lower)
        if match:
            return VoteValue.yes if match.group(1) == "yes" else VoteValue.no

        if cleaned_lower.startswith("yes"):
            return VoteValue.yes
        if cleaned_lower.startswith("no"):
            return VoteValue.no
        return VoteValue.invalid

    def _build_messages(
        self,
        template: DebateTemplate,
        persona_prompt: str,
        phase,
        run: DebateRun,
        round_index: int,
    ) -> List[Dict[str, str]]:
        # Uses simple slot filling until a templating engine is added.
        history_summary = self._prior_round_transcript(run)
        user_content = (
            f"[Round {round_index} - {phase.id}]\n"
            f"Debate topic: {run.topic}\n"
            f"History:\n{history_summary}\n"
            f"Phase prompt: {phase.prompt_template}"
        )
        return [
            {"role": "system", "content": persona_prompt},
            {"role": "user", "content": user_content},
        ]

    def _prior_round_transcript(self, run: DebateRun) -> str:
        if not run.rounds:
            return "(no prior round responses)"
        last = run.rounds[-1]
        lines: List[str] = [f"Round {last.round_index} transcript:"]
        for po in last.phase_outputs:
            lines.append(f"- {po.participant_id} ({po.phase_id}): {po.output}")
        if last.votes:
            yes = sum(1 for v in last.votes if v.parsed_vote == VoteValue.yes)
            no = sum(1 for v in last.votes if v.parsed_vote == VoteValue.no)
            lines.append(f"- Votes: YES {yes} / NO {no} | Outcome: {last.outcome or RoundOutcome.invalid}")
        return "\n".join(lines)

    async def _finalize(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        ctx = self._context.get(run_id)
        if not run or not ctx:
            return

        final_outcome = run.rounds[-1].outcome if run.rounds else RoundOutcome.invalid
        run.status = RunStatus.completed
        self.store.update_run(run)

        # Persist final record and retain the run so the UI can fetch results.
        self.store.record_final(
            FinalRecord(
                debate_id=run.id,
                title=run.title,
                final_outcome=final_outcome,
            )
        )

        self._progress.pop(run_id, None)
        self._context.pop(run_id, None)
