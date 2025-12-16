from __future__ import annotations

import datetime as dt
import uuid
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class ResourcePolicy(ModelBase):
    max_llm_ram_pct: int = Field(60, ge=1, le=100)
    reserve_ram_gb: int = Field(12, ge=0)
    max_parallel_requests: int = Field(3, ge=1)


class Participant(ModelBase):
    id: str
    display_name: str
    model_id: str
    persona_prompt: str
    color: Optional[str] = None
    icon: Optional[str] = None


class PhaseRole(str, Enum):
    reaction = "reaction"
    argument_for = "argument_for"
    argument_against = "argument_against"
    vote = "vote"
    summary = "summary"
    custom = "custom"


class VisibleTo(str, Enum):
    all_participants = "all_participants"
    moderator_only = "moderator_only"
    audience_only = "audience_only"


class PhaseSpec(ModelBase):
    id: str
    role: PhaseRole
    prompt_template: str
    visible_to: VisibleTo = VisibleTo.all_participants


class VotingMode(str, Enum):
    simple_majority = "simple_majority"


class VotingConfig(ModelBase):
    mode: VotingMode = VotingMode.simple_majority
    allow_abstain: bool = False


class DebateTemplate(ModelBase):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    topic: str
    rounds: int = Field(1, ge=1)
    phases: List[PhaseSpec]
    participants: List[Participant]
    moderator: Optional[Participant] = None
    voting: VotingConfig = Field(default_factory=VotingConfig)
    resource_policy: ResourcePolicy = Field(default_factory=ResourcePolicy)

    @model_validator(mode="after")
    def validate_participants(self) -> "DebateTemplate":
        count = len(self.participants)
        if count not in {3, 5, 7}:
            raise ValueError("participants must be an odd count: 3, 5, or 7")
        return self


class VoteValue(str, Enum):
    yes = "YES"
    no = "NO"
    invalid = "INVALID"


class VoteResult(ModelBase):
    participant_id: str
    raw_output: str
    parsed_vote: VoteValue


class PhaseOutput(ModelBase):
    phase_id: str
    participant_id: str
    output: str


class RoundOutcome(str, Enum):
    yes = "YES"
    no = "NO"
    tie = "TIE"
    invalid = "INVALID"


class RoundResult(ModelBase):
    round_index: int
    phase_outputs: List[PhaseOutput] = Field(default_factory=list)
    votes: Optional[List[VoteResult]] = None
    outcome: Optional[RoundOutcome] = None
    moderator_summary: Optional[str] = None


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class RunMode(str, Enum):
    auto = "auto"
    step = "step"


class DebateRun(ModelBase):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    template_id: str
    title: str
    topic: str
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.utcnow())
    status: RunStatus = RunStatus.pending
    mode: RunMode = RunMode.auto
    rounds: List[RoundResult] = Field(default_factory=list)


class FinalRecord(ModelBase):
    debate_id: str
    title: str
    final_outcome: RoundOutcome


class CreateTemplateRequest(ModelBase):
    name: str
    topic: str
    rounds: int = 1
    phases: List[PhaseSpec]
    participants: List[Participant]
    moderator: Optional[Participant] = None
    voting: VotingConfig = Field(default_factory=VotingConfig)
    resource_policy: ResourcePolicy = Field(default_factory=ResourcePolicy)


class StartDebateRequest(ModelBase):
    template_id: str
    topic: Optional[str] = None
    rounds: Optional[int] = None
    mode: RunMode = RunMode.auto


class AdvanceDebateResponse(ModelBase):
    debate: DebateRun
    done: bool


class ErrorResponse(ModelBase):
    detail: str
