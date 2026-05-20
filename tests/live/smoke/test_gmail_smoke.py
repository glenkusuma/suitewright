import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


def test_gmail_labels_present(sandbox):
    labels = cli_run(["gmail", "labels"])
    assert isinstance(labels, list)
    names = {label.get("name") for label in labels}
    assert "INBOX" in names
    assert "SENT" in names


def test_gmail_search_inbox(sandbox):
    result = cli_run(["gmail", "search", "in:inbox", "--max", "1"], allow_nonzero=True)
    if isinstance(result, list):
        if not result:
            pytest.skip("inbox is empty; search shape verified by mock suite")
        assert "id" in result[0]
    # "No messages found." plain text is also acceptable


def test_gmail_get_recent_message(sandbox):
    msgs = cli_run(["gmail", "search", "in:inbox", "--max", "1"], allow_nonzero=True)
    if not isinstance(msgs, list) or not msgs:
        pytest.skip("inbox is empty")
    full = cli_run(["gmail", "get", msgs[0]["id"]])
    assert full.get("id") == msgs[0]["id"]
    assert "body" in full
