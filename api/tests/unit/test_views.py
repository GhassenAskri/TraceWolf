from app.views import new_messages

SYSTEM = {"role": "system", "content": "You are helpful"}
USER_1 = {"role": "user", "content": "Hi"}
REPLY_1 = {"role": "assistant", "content": "Hello!"}
USER_2 = {"role": "user", "content": "Weather in Paris?"}
TOOL_CALL = {
    "role": "assistant",
    "content": None,
    "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}],
}
TOOL_RESULT = {"role": "tool", "content": '{"temp": 22}', "tool_call_id": "call_1"}
FINAL = {"role": "assistant", "content": "Sunny, 22°C"}


def test_first_turn_shows_system_user_and_reply():
    assert new_messages([SYSTEM, USER_1], [REPLY_1]) == [SYSTEM, USER_1, REPLY_1]


def test_turn_n_shows_latest_user_message_and_reply():
    assert new_messages([SYSTEM, USER_1, REPLY_1, USER_2], [FINAL]) == [USER_2, FINAL]


def test_reply_that_is_a_tool_call():
    assert new_messages([SYSTEM, USER_2], [TOOL_CALL]) == [SYSTEM, USER_2, TOOL_CALL]


def test_tool_round_trip_shows_tool_result_and_reply():
    history = [SYSTEM, USER_2, TOOL_CALL, TOOL_RESULT]

    assert new_messages(history, [FINAL]) == [TOOL_RESULT, FINAL]


def test_no_output_for_failed_calls():
    assert new_messages([SYSTEM, USER_1], []) == [SYSTEM, USER_1]


def test_transcript_of_an_error_call():
    from app.views import format_transcript

    call = {
        "id": 7,
        "started_at": "2026-09-24T10:00:00+00:00",
        "request_model": "gpt-4o-mini",
        "tokens": {"input": None, "output": None},
        "status": "error",
        "error_type": "RateLimitError",
        "status_message": "Error code: 429",
        "input_messages": [USER_1],
        "output_messages": [],
    }

    text = format_transcript("My Project", "v", "2026-09-24T11:00:00+00:00", [call])

    assert text.startswith("# Project: My Project\n# Volume: v\n# 1 calls up to ")
    assert "## Call 1 (id 7) | 2026-09-24T10:00:00+00:00 | gpt-4o-mini" in text
    assert "| error" in text
    assert "[error] RateLimitError: Error code: 429" in text
    assert "[user] Hi" in text
