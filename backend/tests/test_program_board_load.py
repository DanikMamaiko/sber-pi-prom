from argparse import Namespace
from datetime import date

import pytest

from app.tools.program_board_load import build_parser, fixture_scope


def test_load_tool_defaults_to_isolated_2000_card_scope():
    args = build_parser().parse_args(["create"])
    scope = fixture_scope(args)

    assert args.count == 2_000
    assert args.teams == 20
    assert (scope.year, scope.quarter) == (2099, "Q4")
    assert scope.issue_prefix == "LOAD-VDI-2000-"
    assert scope.start_date == date(2099, 10, 1)


def test_load_run_id_is_normalized_and_rejects_sql_like_wildcards():
    scope = fixture_scope(Namespace(year=2098, quarter="Q2", run_id="vdi_test"))
    assert scope.run_id == "VDI_TEST"
    assert scope.issue_prefix == "LOAD-VDI-TEST-"

    with pytest.raises(ValueError, match="--run-id"):
        fixture_scope(Namespace(year=2098, quarter="Q2", run_id="vdi%test"))
