import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]


def test_forms_list_returns_array(sandbox):
    forms = cli_run(["forms", "list", "--max", "5"])
    assert isinstance(forms, list)
