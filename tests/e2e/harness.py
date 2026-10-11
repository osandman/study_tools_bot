"""Эмулятор Telegram Bot API и «живой пользователь» для e2e-сценариев.

Бот работает как в проде: диспетчер из ``bot.main.build_dispatcher()``, настоящий
``DatabaseMiddleware`` и настоящий Postgres. Подменяется только HTTP-сессия aiogram:
вместо api.telegram.org запросы обрабатывает ``TelegramEmulator``. Он хранит историю
чата и соблюдает правила Bot API, на которых боты падают в проде:

- HTML разбирается так же, как в tdlib: неизвестный тег или голый ``<`` — это ошибка
  400 «can't parse entities», а голый ``&`` Telegram терпит;
- редактирование без изменений — 400 «message is not modified»;
- текст длиннее 4096 символов, пустой текст, длинный callback_data — 400;
- на нажатие кнопки можно ответить только один раз.

Пользователь (``TgUser``) может только то, что может человек: писать текст и нажимать
кнопки, которые реально есть на сообщении бота.
"""

from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Update

E2E_TOKEN = "4200000001:e2e-fake-token"
BOT_USER = {"id": 4200000001, "is_bot": True, "first_name": "Study tools", "username": "study_tools_bot"}

MAX_TEXT_LENGTH = 4096
MAX_CALLBACK_DATA_BYTES = 64
MAX_BUTTONS_PER_ROW = 8
MAX_BUTTONS_TOTAL = 100
MAX_CALLBACK_ANSWER_LENGTH = 200

NOT_MODIFIED = (
    "Bad Request: message is not modified: specified new message content and reply markup "
    "are exactly the same as a current content and reply markup of the message"
)

# Теги из раздела «HTML style» документации Bot API.
_ENTITY_BY_TAG = {
    "b": "bold", "strong": "bold",
    "i": "italic", "em": "italic",
    "u": "underline", "ins": "underline",
    "s": "strikethrough", "strike": "strikethrough", "del": "strikethrough",
    "span": "spoiler", "tg-spoiler": "spoiler",
    "a": "text_link", "tg-emoji": "custom_emoji",
    "code": "code", "pre": "pre", "blockquote": "blockquote",
}
_NAMED_ENTITIES = {"lt": "<", "gt": ">", "amp": "&", "quot": '"'}


class TelegramApiError(Exception):
    def __init__(self, status: int, description: str):
        super().__init__(description)
        self.status = status
        self.description = description


class BotCrashed(AssertionError):
    """Обработчик бросил исключение: в проде aiogram его залогирует, а пользователь не получит ответа."""


def parse_telegram_html(text: str) -> tuple[str, list[tuple[str, int, int]]]:
    """Видимый текст и сущности, как их получит Telegram; ошибки — как у tdlib parse_html."""
    out: list[str] = []
    entities: list[tuple[str, int, int]] = []
    stack: list[tuple[str, int]] = []
    i, n = 0, len(text)

    def byte_offset(pos: int) -> int:
        return len(text[:pos].encode("utf-8"))

    def fail(reason: str) -> TelegramApiError:
        return TelegramApiError(400, f"Bad Request: can't parse entities: {reason}")

    while i < n:
        ch = text[i]
        if ch == "&":
            semi = text.find(";", i + 1, i + 12)
            if semi != -1:
                name = text[i + 1:semi]
                decoded = _NAMED_ENTITIES.get(name)
                if decoded is None and name.startswith("#x"):
                    decoded = chr(int(name[2:], 16)) if name[2:] and all(c in "0123456789abcdefABCDEF" for c in name[2:]) else None
                elif decoded is None and name.startswith("#") and name[1:].isdigit():
                    decoded = chr(int(name[1:]))
                if decoded is not None:
                    out.append(decoded)
                    i = semi + 1
                    continue
            out.append("&")
            i += 1
            continue
        if ch != "<":
            out.append(ch)
            i += 1
            continue

        start = i
        close = text.find(">", i)
        if text.startswith("</", i):
            if close == -1:
                raise fail(f"Unclosed end tag at byte offset {byte_offset(start)}")
            name = text[i + 2:close].strip().lower()
            if not stack:
                raise fail(f'Unexpected end tag at byte offset {byte_offset(start)}')
            open_name, open_pos = stack.pop()
            if name != open_name:
                raise fail(
                    f'Unmatched end tag at byte offset {byte_offset(start)}, '
                    f'expected "</{open_name}>", found "</{name}>"'
                )
            entities.append((_ENTITY_BY_TAG[open_name], open_pos, len("".join(out))))
            i = close + 1
            continue

        j = i + 1
        while j < n and not text[j].isspace() and text[j] != ">":
            j += 1
        name = text[i + 1:j].lower()
        if name not in _ENTITY_BY_TAG:
            raise fail(f'Unsupported start tag "{name}" at byte offset {byte_offset(start)}')
        if close == -1:
            raise fail(f"Unclosed start tag at byte offset {byte_offset(start)}")
        stack.append((name, len("".join(out))))
        i = close + 1

    if stack:
        raise fail(f'Can\'t find end tag corresponding to start tag "{stack[-1][0]}"')
    return "".join(out), entities


@dataclass
class StoredMessage:
    chat_id: int
    message_id: int
    html: str
    text: str
    entities: list[tuple[str, int, int]]
    markup: dict | None
    date: int = field(default_factory=lambda: int(time.time()))

    def as_json(self, chat: dict) -> dict:
        data = {
            "message_id": self.message_id,
            "date": self.date,
            "chat": chat,
            "from": BOT_USER,
            "text": self.text,
        }
        if self.markup is not None:
            data["reply_markup"] = self.markup
        return data


class TelegramEmulator(BaseSession):
    """Сессия aiogram, которая вместо HTTP отвечает как Telegram Bot API."""

    def __init__(self) -> None:
        super().__init__()
        self.chats: dict[int, dict] = {}
        self.messages: dict[tuple[int, int], StoredMessage] = {}
        self.message_ids = itertools.count(1000)
        self.pending_callbacks: set[str] = set()
        self.callback_answers: dict[str, dict] = {}
        self.commands: dict[str, list[dict]] = {}
        self.events: list[tuple[str, Any, Any]] = []

    async def close(self) -> None:
        pass

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError
        yield b""

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        params = {
            key: value
            for key, value in (
                (key, self.prepare_value(raw, bot=bot, files={}, _dumps_json=False))
                for key, raw in method.model_dump(warnings=False).items()
            )
            if value is not None
        }
        handler = getattr(self, f"_api_{method.__api_method__}", None)
        if handler is None:
            raise AssertionError(f"Эмулятор не знает метод {method.__api_method__}: добавь его в harness.py")
        try:
            payload, status = {"ok": True, "result": handler(params)}, 200
        except TelegramApiError as exc:
            payload, status = {"ok": False, "error_code": exc.status, "description": exc.description}, exc.status
        return self.check_response(bot, method, status, json.dumps(payload)).result

    # ─── проверки ────────────────────────────────────────────────────────────

    @staticmethod
    def _render(params: dict) -> tuple[str, list]:
        raw = params.get("text", "")
        if params.get("parse_mode") == "HTML":
            text, entities = parse_telegram_html(raw)
        else:
            text, entities = raw, []
        if not text.strip():
            raise TelegramApiError(400, "Bad Request: message text is empty")
        if len(text) > MAX_TEXT_LENGTH:
            raise TelegramApiError(400, "Bad Request: message is too long")
        return text, entities

    @staticmethod
    def _inline_markup(params: dict) -> dict | None:
        markup = params.get("reply_markup")
        if not markup or "inline_keyboard" not in markup:
            return None
        rows = markup["inline_keyboard"]
        if sum(len(row) for row in rows) > MAX_BUTTONS_TOTAL or any(len(row) > MAX_BUTTONS_PER_ROW for row in rows):
            raise TelegramApiError(400, "Bad Request: BUTTONS_TOO_MUCH")
        for row in rows:
            for button in row:
                if not button.get("text", "").strip():
                    raise TelegramApiError(400, "Bad Request: BUTTON_TEXT_INVALID")
                data = button.get("callback_data")
                if data is not None and not 1 <= len(data.encode("utf-8")) <= MAX_CALLBACK_DATA_BYTES:
                    raise TelegramApiError(400, "Bad Request: BUTTON_DATA_INVALID")
        return {"inline_keyboard": rows}

    def _message(self, params: dict, action: str) -> StoredMessage:
        message = self.messages.get((int(params["chat_id"]), int(params["message_id"])))
        if message is None:
            raise TelegramApiError(400, f"Bad Request: message to {action} not found")
        return message

    # ─── методы Bot API ──────────────────────────────────────────────────────

    def _api_getMe(self, params: dict) -> dict:
        return BOT_USER

    def _api_setMyCommands(self, params: dict) -> bool:
        self.commands[params.get("scope", {}).get("type", "default")] = params["commands"]
        return True

    def _api_deleteMyCommands(self, params: dict) -> bool:
        self.commands.pop(params.get("scope", {}).get("type", "default"), None)
        return True

    def _api_getMyCommands(self, params: dict) -> list:
        return self.commands.get(params.get("scope", {}).get("type", "default"), [])

    def _api_sendMessage(self, params: dict) -> dict:
        chat_id = int(params["chat_id"])
        chat = self.chats.get(chat_id)
        if chat is None:
            raise TelegramApiError(403, "Forbidden: bot can't initiate conversation with a user")
        text, entities = self._render(params)
        message = StoredMessage(chat_id, next(self.message_ids), params["text"], text, entities, self._inline_markup(params))
        self.messages[(chat_id, message.message_id)] = message
        self.events.append(("sent", chat_id, message.message_id))
        return message.as_json(chat)

    def _api_editMessageText(self, params: dict) -> dict:
        message = self._message(params, "edit")
        text, entities = self._render(params)
        markup = self._inline_markup(params)
        if (text, entities, markup) == (message.text, message.entities, message.markup):
            raise TelegramApiError(400, NOT_MODIFIED)
        message.html, message.text, message.entities, message.markup = params["text"], text, entities, markup
        self.events.append(("edited", message.chat_id, message.message_id))
        return message.as_json(self.chats[message.chat_id])

    def _api_deleteMessage(self, params: dict) -> bool:
        message = self._message(params, "delete")
        del self.messages[(message.chat_id, message.message_id)]
        self.events.append(("deleted", message.chat_id, message.message_id))
        return True

    def _api_answerCallbackQuery(self, params: dict) -> bool:
        query_id = params["callback_query_id"]
        if query_id not in self.pending_callbacks:
            raise TelegramApiError(
                400, "Bad Request: query is too old and response timeout expired or query ID is invalid"
            )
        if len(params.get("text", "")) > MAX_CALLBACK_ANSWER_LENGTH:
            raise TelegramApiError(400, "Bad Request: MESSAGE_TOO_LONG")
        self.pending_callbacks.discard(query_id)
        self.callback_answers[query_id] = {"text": params.get("text"), "show_alert": params.get("show_alert", False)}
        self.events.append(("answered", query_id, None))
        return True


# ─── взгляд пользователя ─────────────────────────────────────────────────────


class ChatMessage:
    """Сообщение бота в чате: всегда показывает текущее состояние, как экран телефона."""

    def __init__(self, tg: TelegramEmulator, chat_id: int, message_id: int):
        self._tg, self.chat_id, self.message_id = tg, chat_id, message_id

    @property
    def _stored(self) -> StoredMessage:
        stored = self._tg.messages.get((self.chat_id, self.message_id))
        if stored is None:
            raise AssertionError(f"Сообщение {self.message_id} удалено из чата")
        return stored

    @property
    def exists(self) -> bool:
        return (self.chat_id, self.message_id) in self._tg.messages

    @property
    def text(self) -> str:
        return self._stored.text

    @property
    def buttons(self) -> list[dict]:
        markup = self._stored.markup or {"inline_keyboard": []}
        return [button for row in markup["inline_keyboard"] for button in row]

    @property
    def button_texts(self) -> list[str]:
        return [button["text"].strip() for button in self.buttons]

    def find_button(self, label: str, nth: int = 0) -> dict:
        exact = [b for b in self.buttons if b["text"].strip() == label]
        pool = exact or [b for b in self.buttons if b["text"].strip().endswith(label)]
        if not exact and len(pool) > 1:
            raise AssertionError(f"Кнопка «{label}» неоднозначна: {[b['text'] for b in pool]}")
        if len(pool) <= nth:
            raise AssertionError(f"На сообщении нет кнопки «{label}» (#{nth}). Есть: {self.button_texts}")
        return pool[nth]

    def __repr__(self) -> str:
        state = repr(self.text[:70]) if self.exists else "удалено"
        return f"<ChatMessage {self.message_id}: {state}>"


@dataclass
class Outcome:
    """Что пользователь увидел в ответ на своё действие."""

    sent: list[ChatMessage]
    edited: list[ChatMessage]
    answer: dict | None = None
    last: ChatMessage | None = None

    @property
    def message(self) -> ChatMessage:
        if self.last is None:
            raise AssertionError("Бот ничего не отправил и не изменил")
        return self.last

    @property
    def text(self) -> str:
        return self.message.text


class E2E:
    def __init__(self, dp: Dispatcher, bot: Bot, tg: TelegramEmulator):
        self.dp, self.bot, self.tg = dp, bot, tg
        self.update_ids = itertools.count(1)
        self.user_ids = itertools.count(5_000_001)

    def user(self, first_name: str = "Аня", *, user_id: int | None = None,
             username: str | None = None, last_name: str | None = None) -> "TgUser":
        return TgUser(self, user_id or next(self.user_ids), first_name, username, last_name)

    async def startup(self) -> None:
        await self.dp.emit_startup(bot=self.bot)

    async def feed(self, update: dict) -> Any:
        return await self.dp.feed_update(self.bot, Update.model_validate(update, context={"bot": self.bot}))


class TgUser:
    def __init__(self, e2e: E2E, user_id: int, first_name: str, username: str | None, last_name: str | None):
        self.e2e, self.id = e2e, user_id
        self.first_name, self.username, self.last_name = first_name, username, last_name

    @property
    def tg(self) -> TelegramEmulator:
        return self.e2e.tg

    @property
    def json(self) -> dict:
        data = {"id": self.id, "is_bot": False, "first_name": self.first_name,
                "username": self.username, "last_name": self.last_name, "language_code": "ru"}
        return {key: value for key, value in data.items() if value is not None}

    @property
    def chat(self) -> dict:
        data = {"id": self.id, "type": "private", "first_name": self.first_name, "username": self.username}
        return {key: value for key, value in data.items() if value is not None}

    @property
    def last_message(self) -> ChatMessage:
        ids = sorted(mid for chat_id, mid in self.tg.messages if chat_id == self.id)
        if not ids:
            raise AssertionError("В чате нет сообщений бота")
        return ChatMessage(self.tg, self.id, ids[-1])

    def message_update(self, text: str) -> dict:
        self.tg.chats[self.id] = self.chat
        message = {"message_id": next(self.tg.message_ids), "date": int(time.time()),
                   "chat": self.chat, "from": self.json, "text": text}
        if text.startswith("/"):
            command_length = len(text.split()[0].encode("utf-16-le")) // 2
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": command_length}]
        return {"update_id": next(self.e2e.update_ids), "message": message}

    def click_update(self, label: str, *, nth: int = 0, on: ChatMessage | None = None) -> tuple[dict, str]:
        message = on or self.last_message
        button = message.find_button(label, nth)
        if "callback_data" not in button:
            raise AssertionError(f"Кнопка «{label}» не шлёт боту callback: {button}")
        query_id = f"cq-{next(self.e2e.update_ids)}"
        self.tg.pending_callbacks.add(query_id)
        query = {"id": query_id, "from": self.json, "chat_instance": f"ci-{self.id}",
                 "message": message._stored.as_json(self.chat), "data": button["callback_data"]}
        return {"update_id": next(self.e2e.update_ids), "callback_query": query}, query_id

    async def _run(self, update: dict, what: str, query_id: str | None = None) -> Outcome:
        start = len(self.tg.events)
        try:
            await self.e2e.feed(update)
        except Exception as exc:
            raise BotCrashed(f"Бот упал, обрабатывая {what}: {type(exc).__name__}: {exc}") from exc
        return self._outcome(start, query_id)

    def _outcome(self, start: int, query_id: str | None) -> Outcome:
        sent, edited, last = [], [], None
        for kind, chat_id, message_id in self.tg.events[start:]:
            if kind in ("sent", "edited") and chat_id == self.id and (chat_id, message_id) in self.tg.messages:
                view = ChatMessage(self.tg, chat_id, message_id)
                (sent if kind == "sent" else edited).append(view)
                last = view
        answer = self.tg.callback_answers.get(query_id) if query_id else None
        return Outcome(sent=sent, edited=edited, answer=answer, last=last)

    async def send(self, text: str) -> Outcome:
        return await self._run(self.message_update(text), f"сообщение «{text}»")

    async def click(self, label: str, *, nth: int = 0, on: ChatMessage | None = None) -> Outcome:
        update, query_id = self.click_update(label, nth=nth, on=on)
        outcome = await self._run(update, f"нажатие «{label}»", query_id)
        if outcome.answer is None:
            raise AssertionError(f"Нажатие «{label}» осталось без ответа: у пользователя крутятся часики на кнопке")
        return outcome


# ─── типовые действия ────────────────────────────────────────────────────────


async def open_counter(user: TgUser, subject: str) -> ChatMessage:
    await user.send("/grades")
    return (await user.click(subject)).message


async def press_grade(user: TgUser, grade: int, sign: str = "+", *, on: ChatMessage | None = None) -> Outcome:
    """Кнопки «+» и «−» стоят в колонках под 1️⃣…5️⃣; nth — номер колонки."""
    return await user.click("+" if sign == "+" else "−", nth=grade - 1, on=on)


async def put_grades(user: TgUser, subject: str, *grades: int) -> Outcome:
    counter = await open_counter(user, subject)
    for grade in grades:
        await press_grade(user, grade, on=counter)
    return await user.click("✅ Сохранить", on=counter)
