from collections.abc import Iterable


class Permission:
    APP_NAVIGATE = "app:navigate"
    PI_CYCLE_SELECT = "pi_cycle:select"
    PI_DATA_READ = "pi_data:read"
    PI_DATA_WRITE = "pi_data:write"
    BACKLOG_READ = "backlog:read"
    BACKLOG_WRITE = "backlog:write"
    PRE_PI_READ = "pre_pi:read"
    PRE_PI_WRITE = "pre_pi:write"
    GOALS_READ = "goals:read"
    GOALS_WRITE = "goals:write"
    TEAM_BOARDS_READ = "team_boards:read"
    TEAM_BOARDS_WRITE = "team_boards:write"
    TASKS_APPROVE = "tasks:approve"
    PROGRAM_BOARD_READ = "program_board:read"
    PROGRAM_BOARD_WRITE = "program_board:write"
    RISKS_READ = "risks:read"
    RISKS_WRITE = "risks:write"
    ADMIN_USERS = "admin:users"


ALL_PERMISSIONS = frozenset(
    value
    for name, value in vars(Permission).items()
    if name.isupper() and isinstance(value, str)
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": ALL_PERMISSIONS,
    "planning_editor": frozenset(
        {
            Permission.APP_NAVIGATE,
            Permission.PI_CYCLE_SELECT,
            Permission.BACKLOG_READ,
            Permission.BACKLOG_WRITE,
            Permission.PRE_PI_READ,
            Permission.PRE_PI_WRITE,
            Permission.GOALS_READ,
            Permission.TEAM_BOARDS_READ,
            Permission.TEAM_BOARDS_WRITE,
            Permission.TASKS_APPROVE,
            Permission.PROGRAM_BOARD_READ,
            Permission.PROGRAM_BOARD_WRITE,
            Permission.RISKS_READ,
            Permission.RISKS_WRITE,
        }
    ),
    "business_viewer": frozenset(
        {
            Permission.APP_NAVIGATE,
            Permission.PI_CYCLE_SELECT,
            Permission.BACKLOG_READ,
            Permission.PRE_PI_READ,
            Permission.PRE_PI_WRITE,
            Permission.GOALS_READ,
            Permission.TEAM_BOARDS_READ,
            Permission.PROGRAM_BOARD_READ,
            Permission.RISKS_READ,
        }
    ),
    "viewer": frozenset(
        {
            Permission.APP_NAVIGATE,
            Permission.PI_CYCLE_SELECT,
            Permission.BACKLOG_READ,
            Permission.PRE_PI_READ,
            Permission.GOALS_READ,
            Permission.TEAM_BOARDS_READ,
            Permission.PROGRAM_BOARD_READ,
            Permission.RISKS_READ,
        }
    ),
}

VALID_ROLES = frozenset(ROLE_PERMISSIONS)


def permissions_for_roles(roles: Iterable[str]) -> frozenset[str]:
    permissions: set[str] = set()
    for role in roles:
        try:
            permissions.update(ROLE_PERMISSIONS[role])
        except KeyError as error:
            raise ValueError(f"Неизвестная роль: {role}") from error
    return frozenset(permissions)
