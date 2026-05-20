"""Shared fixtures for suitewright tests."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def sample_paragraph_element():
    return {
        "startIndex": 1,
        "endIndex": 25,
        "paragraph": {
            "elements": [
                {"textRun": {"content": "Hello, world!\n"}},
                {"textRun": {"content": "Second run."}},
            ]
        },
    }


@pytest.fixture
def sample_table_element():
    return {
        "startIndex": 30,
        "endIndex": 120,
        "table": {
            "tableRows": [
                {
                    "tableCells": [
                        {
                            "startIndex": 31,
                            "endIndex": 50,
                            "content": [
                                {
                                    "startIndex": 32,
                                    "endIndex": 49,
                                    "paragraph": {"elements": [{"textRun": {"content": "Name"}}]},
                                }
                            ],
                        },
                        {
                            "startIndex": 51,
                            "endIndex": 70,
                            "content": [
                                {
                                    "startIndex": 52,
                                    "endIndex": 69,
                                    "paragraph": {"elements": [{"textRun": {"content": "Role"}}]},
                                }
                            ],
                        },
                        {
                            "startIndex": 71,
                            "endIndex": 90,
                            "content": [
                                {
                                    "startIndex": 72,
                                    "endIndex": 89,
                                    "paragraph": {"elements": [{"textRun": {"content": "Status"}}]},
                                }
                            ],
                        },
                    ]
                },
                {
                    "tableCells": [
                        {
                            "startIndex": 91,
                            "endIndex": 100,
                            "content": [
                                {
                                    "startIndex": 92,
                                    "endIndex": 99,
                                    "paragraph": {"elements": [{"textRun": {"content": "Alice"}}]},
                                }
                            ],
                        },
                        {
                            "startIndex": 101,
                            "endIndex": 110,
                            "content": [
                                {
                                    "startIndex": 102,
                                    "endIndex": 109,
                                    "paragraph": {"elements": [{"textRun": {"content": "Owner"}}]},
                                }
                            ],
                        },
                        {
                            "startIndex": 111,
                            "endIndex": 120,
                            "content": [
                                {
                                    "startIndex": 112,
                                    "endIndex": 119,
                                    "paragraph": {"elements": [{"textRun": {"content": "Active"}}]},
                                }
                            ],
                        },
                    ]
                },
            ]
        },
    }


@pytest.fixture
def sample_doc(sample_paragraph_element, sample_table_element):
    return {
        "documentId": "DOC123",
        "title": "Test Document",
        "body": {
            "content": [
                sample_paragraph_element,
                sample_table_element,
                {
                    "startIndex": 120,
                    "endIndex": 121,
                    "paragraph": {"elements": [{"textRun": {"content": "\n"}}]},
                },
            ]
        },
    }


@pytest.fixture
def sample_form():
    return {
        "formId": "FORM123",
        "revisionId": "rev1",
        "items": [
            {
                "itemId": "item001",
                "title": "A1. First question",
                "questionItem": {
                    "question": {
                        "questionId": "q001",
                        "required": True,
                        "textQuestion": {},
                    }
                },
            },
            {
                "itemId": "item002",
                "title": "B2. Second question",
                "questionItem": {
                    "question": {
                        "questionId": "q002",
                        "required": False,
                        "choiceQuestion": {
                            "type": "RADIO",
                            "options": [{"value": "Yes"}, {"value": "No"}],
                        },
                    }
                },
            },
            {
                "itemId": "item003",
                "title": "Section header",
                "textItem": {},
            },
        ],
    }


@pytest.fixture
def tmp_requests_file(tmp_path):
    def _make(requests: list) -> str:
        p = tmp_path / "requests.json"
        p.write_text(json.dumps(requests))
        return str(p)

    return _make
