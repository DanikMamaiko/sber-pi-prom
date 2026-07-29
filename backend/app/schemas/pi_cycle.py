"""Backwards-compatible aggregate of all PI-cycle schemas.

The concrete definitions now live in per-domain modules (_base, reference,
pi_cycle_data, backlog, pre_pi, team_boards, program_board, goals, risks).
They are re-exported here so existing ``from app.schemas.pi_cycle import X``
imports keep resolving unchanged.
"""

from app.schemas._base import (  # noqa: F401
    ORMModel,
)

from app.schemas.reference import (  # noqa: F401
    TribeCreate, TribeRead, TeamCreate, TeamRead,
    TeamMemberCreate, TeamMemberRead,
)

from app.schemas.pi_cycle_data import (  # noqa: F401
    PiEventCreate, PiEventRead, PiCycleCreate, PiCycleUpdate,
    PiCycleRead, PiCycleSetupEvent, PiCycleSetupTeam, PiCycleSetupData,
    PiCycleSetupWrite, PiCycleSetupRead, PiCycleDataCommand, PiCycleDataUpdate,
    PiEventDataCreate, PiEventDataUpdate, PiCycleTeamDataCreate, PiCycleTeamDataUpdate,
    PiCycleTeamDelete, PiGoalOptionDataCreate, PiGoalOptionDataUpdate, PiTagDataCreate,
    PiTagDataUpdate, PiEventDataWrite, PiCycleTeamDataWrite, PiNamedDataWrite,
    PiTagDataWrite, PiCycleDataReplace, PiEventDataRead, PiCycleTeamDataRead,
    PiGoalOptionDataRead, PiTagDataRead, PiScheduleWeekRead, PiScheduleSprintRead,
    PiScheduleRead, PiCycleReferenceDataRead, PiCycleDataRead, SprintRead,
    OverviewRead,
)

from app.schemas.backlog import (  # noqa: F401
    BacklogExecutorPayload, BacklogBoardExecutor, BacklogBoardExecutorRead, BacklogItemFields,
    BacklogItemCommand, BacklogItemDelete, BacklogReorderCommand, BacklogBoardItemWrite,
    BacklogBoardWrite, BacklogTribeRef, BacklogTeamRef, BacklogReferenceDataRead,
    BacklogBoardItemRead, BacklogBoardRead, BacklogDispatchWrite,
)

from app.schemas.pre_pi import (  # noqa: F401
    InitiativeCreate, InitiativeRead, PrePiAttraction, PrePiExecutor,
    PrePiInitiativeWrite, PrePiInitiativeRead, PrePiWrite, PrePiRead,
    PrePiInitiativeCommand, PrePiMoveCommand, PrePiDeleteCommand, PrePiSubmitTeam,
    PrePiSubmitWrite, PrePiSubmitRead,
)

from app.schemas.team_boards import (  # noqa: F401
    TeamBoardStoryWrite, TeamBoardStoryRead, TeamBoardWorkItemWrite, TeamBoardWorkItemRead,
    TeamBoardInitiativeWrite, TeamBoardInitiativeRead, TeamBoardsWrite, TeamBoardsRead,
    TeamBoardCommand, TeamBoardInitiativeCommand, TeamBoardStoryCreate,
    TeamBoardStoryUpdate, TeamBoardDeleteCommand, TeamBoardWorkItemCreate,
    TeamBoardWorkItemUpdate, CapacityDateRange, CapacityMemberWrite,
    CapacitySprintRead, CapacityWeekRead, CapacityMemberRead, CapacityTeamWrite,
    CapacityTeamRead, CapacityWrite, CapacityRead, CapacityMemberCreate,
    CapacityMemberUpdate,
)

from app.schemas.program_board import (  # noqa: F401
    ProgramBoardEndpoint, ProgramBoardBend, ProgramBoardConnectionWrite, ProgramBoardConnectionRead,
    ProgramBoardWrite, ProgramBoardRead,
)

from app.schemas.goals import (  # noqa: F401
    GoalsItemWrite, GoalsItemRead, GoalsWrite, GoalsRead,
    GoalCommand, GoalFields, GoalCreateCommand, GoalUpdateCommand,
    GoalDeleteCommand, GoalReorderCommand, GoalStatusCommand, GoalLinkCommand,
    GoalUnlinkCommand, PiGoalCreate, PiGoalRead,
)

from app.schemas.risks import (  # noqa: F401
    RiskCreate, RiskRead, RiskTeamRef, RiskItemWrite,
    RiskItemRead, RisksWrite, RisksRead, RiskCommand,
    RiskFields, RiskCreateCommand, RiskUpdateCommand, RiskDeleteCommand,
    RiskReorderCommand, RiskStatusCommand, RiskRoamCommand, RiskLinkCommand,
)

