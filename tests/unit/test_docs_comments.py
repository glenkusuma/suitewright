"""Tests for docs.comments normalizer helpers."""

from __future__ import annotations

from suitewright.docs.comments import _normalize_comment, _normalize_reply


class TestNormalizeReply:
    def test_full_reply(self):
        raw = {
            "id": "r1",
            "content": "Great point",
            "htmlContent": "<p>Great point</p>",
            "author": {"displayName": "Alice"},
            "createdTime": "2026-01-01T00:00:00Z",
            "modifiedTime": "2026-01-01T01:00:00Z",
            "deleted": False,
        }
        result = _normalize_reply(raw)
        assert result["replyId"] == "r1"
        assert result["content"] == "Great point"
        assert result["htmlContent"] == "<p>Great point</p>"
        assert result["author"] == "Alice"
        assert result["createdTime"] == "2026-01-01T00:00:00Z"
        assert result["deleted"] is False

    def test_absent_fields_omitted(self):
        raw = {"id": "r2", "content": "ok"}
        result = _normalize_reply(raw)
        assert "htmlContent" not in result
        assert "author" not in result
        assert "modifiedTime" not in result

    def test_empty_raw(self):
        result = _normalize_reply({})
        assert result == {}


class TestNormalizeComment:
    def test_full_comment_without_replies(self):
        raw = {
            "id": "c1",
            "content": "Fix this",
            "htmlContent": "<p>Fix this</p>",
            "quotedFileContent": {"value": "original text"},
            "author": {"displayName": "Bob"},
            "createdTime": "2026-01-01T00:00:00Z",
            "modifiedTime": "2026-01-01T01:00:00Z",
            "resolved": False,
            "deleted": False,
            "anchor": "kix.abc123",
            "replies": [{"id": "r1", "content": "Done"}],
        }
        result = _normalize_comment(raw, include_replies=False)
        assert result["commentId"] == "c1"
        assert result["content"] == "Fix this"
        assert result["quotedFileContent"] == "original text"
        assert result["author"] == "Bob"
        assert result["resolved"] is False
        assert result["replyCount"] == 1
        assert "replies" not in result

    def test_comment_with_replies_inline(self):
        raw = {
            "id": "c2",
            "content": "Question",
            "replies": [
                {"id": "r1", "content": "Answer", "author": {"displayName": "Alice"}},
            ],
        }
        result = _normalize_comment(raw, include_replies=True)
        assert "replies" in result
        assert len(result["replies"]) == 1
        assert result["replies"][0]["replyId"] == "r1"
        assert "replyCount" not in result

    def test_absent_fields_omitted(self):
        raw = {"id": "c3", "content": "Simple"}
        result = _normalize_comment(raw, include_replies=False)
        assert "htmlContent" not in result
        assert "quotedFileContent" not in result
        assert "author" not in result
        assert "anchor" not in result
        assert result["replyCount"] == 0

    def test_empty_replies_list(self):
        raw = {"id": "c4", "content": "No replies", "replies": []}
        result = _normalize_comment(raw, include_replies=False)
        assert result["replyCount"] == 0
