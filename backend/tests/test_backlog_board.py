import uuid

import pytest

from app.models.pi_cycle import BacklogExecutor, BacklogItem
from app.services.backlog_board import _item_effort, normalize_issue_key


def test_issue_key_is_trimmed_and_rejects_unsafe_or_empty_values():
    assert normalize_issue_key("  SBOL-42  ") == "SBOL-42"
    assert normalize_issue_key("Продукт_7.2") == "Продукт_7.2"

    for value in ("", "SBOL 42", "#42", "A/42"):
        with pytest.raises(ValueError, match="Issue ID"):
            normalize_issue_key(value)


def test_server_total_effort_is_finite_sum_rounded_to_three_decimals():
    item = BacklogItem(id=uuid.uuid4(), issue_key="EFFORT-1", title="Effort")
    item.executors = [
        BacklogExecutor(
            id=uuid.uuid4(),
            team_id=uuid.uuid4(),
            effort_by_competency={"SA": 1.1114, "DEV": 2},
        ),
        BacklogExecutor(
            id=uuid.uuid4(),
            team_id=uuid.uuid4(),
            effort_by_competency={"QA": 0.5555},
        ),
    ]

    assert _item_effort(item) == 3.667
