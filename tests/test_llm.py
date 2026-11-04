import logging

import httpx
import pytest

from src import llm
from src.errors import LLMAuthError, LLMError, LLMRateLimitError, LLMUnavailableError

SECRET = "AIzaSyD-this-is-a-fake-key-0123456789abcd"


class Boom:
    """Fails with the given exceptions in order, then answers."""

    def __init__(self, *errors, answer="ok"):
        self.errors, self.answer, self.calls = list(errors), answer, 0

    def invoke(self, messages):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return type("R", (), {"content": self.answer})()


def run(model, **kw):
    sleeps = []
    out = llm.invoke_with_retry(model, ["m"], sleep=sleeps.append, rand=lambda: 0.0, base_delay=15, max_retries=3, **kw)
    return out, sleeps


def test_success_without_retry():
    out, sleeps = run(Boom())
    assert out == "ok" and sleeps == []


def test_rate_limit_is_retried_with_growing_waits():
    model = Boom(Exception("429 RESOURCE_EXHAUSTED"), Exception("quota exceeded"))
    out, sleeps = run(model)
    assert out == "ok" and model.calls == 3
    assert sleeps == [15, 22.5]


def test_jitter_adds_up_to_25_percent():
    sleeps = []
    llm.invoke_with_retry(Boom(Exception("429")), ["m"], sleep=sleeps.append, rand=lambda: 1.0, base_delay=10, max_retries=2)
    assert sleeps == [12.5]


def test_gives_up_after_the_retries_and_does_not_wait_after_the_last_failure():
    model = Boom(*[Exception("429")] * 10)
    sleeps = []
    with pytest.raises(LLMRateLimitError):
        llm.invoke_with_retry(model, ["m"], sleep=sleeps.append, rand=lambda: 0.0, base_delay=1, max_retries=3)
    assert model.calls == 4 and len(sleeps) == 3


def test_connection_problem_is_not_retried_and_the_message_names_the_provider():
    model = Boom(ConnectionError("refused"))
    with pytest.raises(LLMUnavailableError, match="Ollama"):
        run(model)
    assert model.calls == 1
    with pytest.raises(LLMUnavailableError, match="Gemini"):
        run(Boom(Exception("Failed to connect")), api_key="k")


def test_other_errors_become_a_generic_error_without_details():
    model = Boom(ValueError("model 'x' not found at http://10.0.0.5:11434"))
    with pytest.raises(LLMError) as err:
        run(model)
    assert "10.0.0.5" not in err.value.public_message and model.calls == 1


def test_api_key_never_reaches_logs_or_errors(caplog):
    caplog.set_level(logging.DEBUG)
    for exc in (Exception(f"429 too many for key={SECRET}"), Exception(f"bad request key={SECRET}"),
                Exception(f"Failed to connect using {SECRET}")):
        with pytest.raises(Exception) as err:
            llm.invoke_with_retry(Boom(*[exc] * 5), ["m"], api_key=SECRET, sleep=lambda s: None, rand=lambda: 0.0,
                                  base_delay=0, max_retries=1)
        assert SECRET not in str(err.value) and SECRET not in repr(err.value)
    assert SECRET not in caplog.text


def test_redact_removes_known_and_google_shaped_keys():
    assert llm.redact("a custom-key-123 b", "custom-key-123") == "a *** b"
    assert SECRET not in llm.redact(f"x {SECRET} y", None)


def test_message_text_handles_list_content():
    assert llm.message_text(type("R", (), {"content": [{"text": "a"}, {"text": "b"}, "c"]})()) == "abc"
    assert llm.message_text(type("R", (), {"content": "plain"})()) == "plain"


def test_get_llm_chooses_gemini_with_a_key_and_ollama_without():
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_ollama import ChatOllama
    assert isinstance(llm.get_llm("k" * 20, 0.5), ChatGoogleGenerativeAI)
    assert isinstance(llm.get_llm(None, 0.5), ChatOllama)


@pytest.mark.parametrize("message", [
    "Error calling model 'gemini-2.0-flash' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.'}}",
    "403 PERMISSION_DENIED: API key expired", "UNAUTHENTICATED: invalid api key",
])
def test_a_rejected_key_gets_a_clear_message_and_is_not_retried(message):
    model = Boom(Exception(message))
    with pytest.raises(LLMAuthError) as err:
        run(model, api_key=SECRET)
    assert model.calls == 1 and "rejected" in err.value.public_message and err.value.status_code == 401


def test_auth_check_does_not_catch_unrelated_errors():
    assert not llm.is_auth_problem(Exception("model returned 401 items"))
    assert not llm.is_auth_problem(Exception("quota exceeded"))


@pytest.mark.parametrize("error", [
    OSError(101, "Network is unreachable"),              # seen for real inside Docker when Ollama is not reachable
    OSError(113, "No route to host"),
    httpx.ConnectError("All connection attempts failed"),
    httpx.ReadTimeout("slow"),
    Exception("Failed to connect to Ollama"),
])
def test_real_world_network_failures_are_reported_as_unreachable(error):
    model = Boom(error)
    with pytest.raises(LLMUnavailableError, match="Ollama"):
        run(model)
    assert model.calls == 1
