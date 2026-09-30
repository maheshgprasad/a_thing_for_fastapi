import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime


def _today() -> str:
    now = datetime.now().astimezone()
    return f"Today is {now:%A, %B} {now.day}, {now.year}."


def _time() -> str:
    now = datetime.now().astimezone()
    return f"It is {now:%I:%M %p} ({now.tzname() or 'local time'})."


R_EATING = "I don't like eating anything because I'm a bot obviously!"
R_SOUND = "beep boop beep boop"
R_WEATHER = "I can't check a live forecast from here. Try the ollama, claude, or bob provider for that."
R_ME = "Hi, I am Mi-Joo, a small assistant. Ask me the date, or switch providers to talk to a model."

_UNKNOWN = (
    "Could you please re-phrase that?",
    "...",
    "Sounds about right",
    "What does that mean?",
)


@dataclass(frozen=True)
class _Intent:
    reply: str | Callable[[], str]
    words: tuple[str, ...]
    required: tuple[str, ...] = ()
    single: bool = False


_INTENTS = (
    _Intent("Hello!", ("hello", "hi", "hey", "howdy", "sup"), single=True),
    _Intent("I'm doing fine, and you?", ("how", "are", "you", "doing"), required=("how",)),
    _Intent("Hello! Good to see you.", ("i", "love", "you"), required=("love", "you")),
    _Intent(R_EATING, ("what", "do", "you", "eat"), required=("you", "eat")),
    _Intent(R_SOUND, ("sound", "you", "make"), required=("sound", "make")),
    _Intent(R_WEATHER, ("what", "is", "the", "weather", "like"), required=("weather",)),
    _Intent(R_ME, ("who", "are", "you"), required=("who", "are", "you")),
    _Intent(_today, ("what", "is", "today", "date", "day"), required=("today",)),
    _Intent(_today, ("what", "is", "the", "date", "today", "day"), required=("date",)),
    _Intent(_today, ("what", "day", "is", "it", "today"), required=("day",)),
    _Intent(_time, ("what", "is", "the", "time", "clock"), required=("time",)),
    _Intent(
        "I can greet you, tell you the date and time, and answer a few set questions. "
        "Set provider to ollama, claude, bob, or cursor for a real model.",
        ("help", "commands"),
        single=True,
    ),
)


def _tokens(user_input: str) -> list[str]:
    return [token for token in re.split(r"\s+|[,;?!.-]\s*", user_input.lower()) if token]


def _score(tokens: list[str], intent: _Intent) -> int:
    if intent.required and not all(word in tokens for word in intent.required):
        if not intent.single:
            return 0
    hits = sum(1 for token in tokens if token in intent.words)
    if hits == 0:
        return 0
    if not (intent.single or all(word in tokens for word in intent.required)):
        return 0
    return int(100 * hits / len(intent.words))


def get_response(user_input: str) -> str:
    tokens = _tokens(user_input)
    best_reply = ""
    best_score = 0
    for intent in _INTENTS:
        score = _score(tokens, intent)
        if score > best_score:
            best_score = score
            reply = intent.reply
            best_reply = reply() if callable(reply) else reply
    if best_score < 1:
        return random.choice(_UNKNOWN)
    return best_reply
