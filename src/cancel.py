"""Stopping a debate whose browser tab was closed. The API sets an event; each agent checks it before a model call."""
import threading

from langchain_core.runnables import RunnableConfig


class Cancelled(Exception):
    """The visitor left; stop without calling the model again."""


def new_event() -> threading.Event:
    return threading.Event()


def run_config(event: threading.Event) -> RunnableConfig:
    return {"configurable": {"cancel": event}}


def check(config: RunnableConfig | None) -> None:
    event = ((config or {}).get("configurable") or {}).get("cancel")
    if event is not None and event.is_set():
        raise Cancelled()
