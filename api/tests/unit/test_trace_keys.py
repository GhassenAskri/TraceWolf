from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.storage.base import (
    build_trace_key,
    deserialize,
    project_prefix,
    serialize,
    volume_prefix,
)

TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN = "00f067aa0ba902b7"
PROJECT = "My Project"


def test_key_layout():
    at = datetime(2026, 9, 24, 10, 1, 3, 120_000, tzinfo=UTC)

    key = build_trace_key(PROJECT, "alice-chat-42", at, TRACE, SPAN)

    assert key == (
        f"projects/My%20Project/volumes/alice-chat-42/2026/09/24/100103_{TRACE}_{SPAN}.json"
    )


def test_key_date_is_utc():
    paris = timezone(timedelta(hours=2))
    at = datetime(2026, 9, 25, 1, 30, tzinfo=paris)  # 2026-09-24 23:30 UTC

    key = build_trace_key("p", "v", at, TRACE, SPAN)

    assert key.startswith("projects/p/volumes/v/2026/09/24/233000_")


def test_key_is_deterministic():
    at = datetime(2026, 9, 24, tzinfo=UTC)

    assert build_trace_key("p", "v", at, TRACE, SPAN) == build_trace_key("p", "v", at, TRACE, SPAN)


def test_the_same_volume_name_in_two_projects_gets_different_keys():
    at = datetime(2026, 9, 24, tzinfo=UTC)

    assert build_trace_key("a", "chat", at, TRACE, SPAN) != build_trace_key(
        "b", "chat", at, TRACE, SPAN
    )


NAMES = [
    ("alice-chat-42", "alice-chat-42"),
    ("user@example.com:chat_1", "user@example.com:chat_1"),
    ("a/b", "a%2Fb"),
    ("..", "%2E%2E"),
    ("../../etc", "..%2F..%2Fetc"),
    (".", "%2E"),
    ("my chat", "my%20chat"),
    ("café", "caf%C3%A9"),
]


@pytest.mark.parametrize(("project", "segment"), NAMES)
def test_project_names_are_encoded_into_a_single_safe_segment(project, segment):
    assert project_prefix(project) == f"projects/{segment}/"
    assert project_prefix(project).count("/") == 2


@pytest.mark.parametrize(("volume", "segment"), NAMES)
def test_volume_names_are_encoded_into_a_single_safe_segment(volume, segment):
    assert volume_prefix("p", volume) == f"projects/p/volumes/{segment}/"
    assert volume_prefix("p", volume).count("/") == 4


def test_a_volume_prefix_lies_inside_its_project_prefix():
    assert volume_prefix(PROJECT, "chat").startswith(project_prefix(PROJECT))


def test_distinct_names_never_share_a_prefix():
    names = ["a", "a/b", "a%2Fb", "a.b", "a%2Eb", "A", "a b"]

    for prefix_of in (project_prefix, lambda n: volume_prefix("p", n)):
        prefixes = [prefix_of(n) for n in names]
        assert len(set(prefixes)) == len(names)
        assert not any(p != q and q.startswith(p) for p in prefixes for q in prefixes)


def test_a_project_cannot_reach_into_another_projects_prefix():
    # "a/volumes/b" is encoded as one segment, so it is not inside project "a"
    assert not project_prefix("a/volumes/b").startswith(project_prefix("a"))


@pytest.mark.parametrize("name", ["", "x" * 256])
def test_invalid_name_length_is_rejected(name):
    with pytest.raises(ValueError, match="Project name"):
        project_prefix(name)
    with pytest.raises(ValueError, match="Volume name"):
        volume_prefix("p", name)


def test_serialization_round_trip_keeps_unicode_and_dates():
    doc = {"content": "Sunny, 22°C ☀️", "at": datetime(2026, 9, 24, tzinfo=UTC)}

    data = serialize(doc)

    assert "☀️".encode() in data
    assert deserialize(data) == {"content": "Sunny, 22°C ☀️", "at": "2026-09-24 00:00:00+00:00"}
