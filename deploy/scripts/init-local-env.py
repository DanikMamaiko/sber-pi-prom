"""Generate a local .env with unique credentials; never overwrite an existing file."""
import argparse
from pathlib import Path
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".env"))
    args = parser.parse_args()
    template = Path(__file__).resolve().parents[2] / ".env.example"
    content = template.read_text(encoding="utf-8")
    for placeholder in (
        "CHANGE_ME_DB_PASSWORD", "CHANGE_ME_ADMIN_PASSWORD",
        "CHANGE_ME_EDITOR_PASSWORD", "CHANGE_ME_POITL_PASSWORD",
        "CHANGE_ME_PM_PASSWORD", "CHANGE_ME_USER_PASSWORD",
        "CHANGE_ME_TO_A_RANDOM_VALUE_OF_AT_LEAST_32_CHARACTERS",
    ):
        content = content.replace(placeholder, secrets.token_urlsafe(48))
    try:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(content)
    except FileExistsError:
        parser.exit(1, f"File already exists; left unchanged: {args.output}\n")
    print(f"Created {args.output}. Local login credentials are in AUTH_TEST_USERS.")


if __name__ == "__main__":
    main()
