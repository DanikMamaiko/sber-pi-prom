"""Local entry point for the Program Board load-data utility."""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.program_board_load import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
