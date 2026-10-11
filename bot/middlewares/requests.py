from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, TelegramMethod
from aiogram.methods.base import TelegramType


class IgnoreMessageNotModified(BaseRequestMiddleware):
    """Re-rendering a screen with the content it already shows is a no-op, not an error.

    Telegram rejects such edits with 400 "message is not modified" (pressing «−» on an empty
    grade, the already selected period, ...). Raised from the handler, it skipped
    callback.answer(), and the user was left with a spinning button.
    """

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ):
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            if isinstance(method, (EditMessageText, EditMessageReplyMarkup)) and "message is not modified" in exc.message:
                return True
            raise
