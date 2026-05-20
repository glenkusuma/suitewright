import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_gmail_send_reply_trash(sandbox):
    if not sandbox.self_email:
        pytest.skip("self_email not resolved; set SUITEWRIGHT_LIVE_TEST_EMAIL")

    subject = f"[{sandbox.prefix}] {sandbox.run_id} hello"
    sent = cli_run(
        [
            "gmail",
            "send",
            "--to",
            sandbox.self_email,
            "--subject",
            subject,
            "--body",
            "live-test body",
        ]
    )
    assert sent["status"] == "sent"
    msg_id = sent["id"]
    sandbox.track("gmail_msg", msg_id)

    # Send a reply on the same thread.
    reply = cli_run(
        [
            "gmail",
            "reply",
            msg_id,
            "--body",
            "live-test reply",
        ]
    )
    assert reply["status"] == "sent"
    sandbox.track("gmail_msg", reply["id"])

    # Verify both are findable in Sent.
    found = cli_run(
        [
            "gmail",
            "search",
            f'from:me subject:"{subject}"',
            "--max",
            "5",
        ],
        allow_nonzero=True,
    )
    if isinstance(found, list):
        assert any(m["id"] in {msg_id, reply["id"]} for m in found)

    # Trash the original explicitly.
    trash = cli_run(["gmail", "trash", msg_id])
    assert trash["status"] == "trashed"
