import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


def test_contacts_list_returns_array(sandbox):
    contacts = cli_run(["contacts", "list", "--max", "5"])
    assert isinstance(contacts, list)
