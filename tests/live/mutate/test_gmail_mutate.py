import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.mutate]


def test_gmail_modify_add_then_remove_label(sandbox):
    msgs = cli_run(["gmail", "search", "in:inbox", "--max", "1"], allow_nonzero=True)
    if not isinstance(msgs, list) or not msgs:
        pytest.skip("inbox empty; nothing to label")
    msg_id = msgs[0]["id"]

    add = cli_run(
        [
            "gmail",
            "modify",
            msg_id,
            "--add-labels",
            sandbox.label_id,
        ]
    )
    assert sandbox.label_id in add.get("labels", [])

    remove = cli_run(
        [
            "gmail",
            "modify",
            msg_id,
            "--remove-labels",
            sandbox.label_id,
        ]
    )
    assert sandbox.label_id not in remove.get("labels", [])
