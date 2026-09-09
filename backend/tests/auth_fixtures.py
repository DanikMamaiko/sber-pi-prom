"""Ephemeral credentials for isolated tests only; never imported by runtime code."""
from secrets import token_urlsafe

TEST_ROLES = {
    "admin": "admin",
    "editor": "planning_editor",
    "po_itl": "planning_editor",
    "pm": "business_viewer",
    "user": "viewer",
}
TEST_PASSWORDS = {username: token_urlsafe(32) for username in TEST_ROLES}
INVALID_TEST_PASSWORD = token_urlsafe(32)
TEST_SESSION_SECRET = token_urlsafe(48)
TEST_LDAP_PASSWORD = token_urlsafe(32)
TEST_SERVICE_PASSWORD = token_urlsafe(32)
TEST_AUTH_USERS = ",".join(
    f"{username}:{TEST_PASSWORDS[username]}:{role}"
    for username, role in TEST_ROLES.items()
)
