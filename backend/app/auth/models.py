from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    username: str
    roles: tuple[str, ...]
    provider: str


@dataclass(frozen=True, slots=True)
class CurrentUser:
    username: str
    roles: tuple[str, ...]
    permissions: frozenset[str]
    provider: str
    issued_at: int
    expires_at: int
