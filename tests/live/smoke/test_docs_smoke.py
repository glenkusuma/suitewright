import pytest

from tests.live.helpers import cli_run

pytestmark = [pytest.mark.live, pytest.mark.smoke]

TEMPLATES = ["replace-all", "insert-table", "insert-image", "style-range"]


@pytest.mark.parametrize("kind", TEMPLATES)
def test_docs_request_template_emits_valid_json(sandbox, kind):
    result = cli_run(["docs", "request-template", kind])
    assert isinstance(result, list)
    assert result, f"template {kind} should emit at least one request"
    for req in result:
        assert isinstance(req, dict)
        assert len(req) == 1, "each request should have exactly one operation key"
