"""Знакомство с ботом: первый запуск, возвращение, команды до регистрации."""

from dbtools import db_subject_names, db_user

from database.models import DEFAULT_SUBJECTS

COMMANDS = ["start", "subjects", "grades", "summary", "settings", "help"]


async def test_bot_start_publishes_command_menu(e2e):
    """Бот стартует: меню команд в Telegram заполнено в обоих скоупах."""
    await e2e.startup()

    for scope in ("default", "all_private_chats"):
        assert [c["command"] for c in e2e.tg.commands[scope]] == COMMANDS


async def test_new_student_is_greeted_and_gets_default_subjects(e2e):
    """Новый ученик: /start → приветствие по имени и 13 стандартных предметов в /subjects."""
    anya = e2e.user("Аня")

    greeting = await anya.send("/start")
    assert "Привет, Аня" in greeting.text

    subjects = await anya.send("/subjects")
    assert len(subjects.sent) == 1, "служебное сообщение для снятия старой клавиатуры должно удалиться"
    *subject_buttons, add_button = subjects.message.button_texts
    assert {text.split(" ", 1)[1] for text in subject_buttons} == set(DEFAULT_SUBJECTS)
    assert add_button == "➕ Добавить"


async def test_returning_student_keeps_subjects_and_updates_username(e2e, admin):
    """Ученик возвращается с новым ником: «С возвращением», предметы не задвоились, ник обновился."""
    anya = e2e.user("Аня", username="anya_old")
    await anya.send("/start")
    anya.username = "anya_new"

    again = await anya.send("/start")

    assert "С возвращением, Аня" in again.text
    assert len(await db_subject_names(anya.id)) == len(DEFAULT_SUBJECTS)
    assert "anya_new" in (await admin.get("/admin/users")).text


async def test_commands_before_start_ask_to_register(e2e):
    """Человек открыл бота по ссылке и сразу жмёт команды из меню, не нажав /start."""
    stranger = e2e.user("Гость")

    for command in ("/grades", "/subjects", "/summary", "/settings"):
        reply = await stranger.send(command)
        assert "Сначала нажмите /start" in reply.text, command


async def test_help_and_unknown_input(e2e):
    """/help объясняет команды; неизвестная команда и случайный текст получают подсказку."""
    anya = e2e.user("Аня")
    await anya.send("/start")

    assert "/summary" in (await anya.send("/help")).text
    assert "Неизвестная команда" in (await anya.send("/gpa")).text
    assert "Не понял сообщение" in (await anya.send("привет")).text


async def test_name_with_angle_brackets_gets_greeting(e2e):
    """Имя в Telegram может содержать «<», например «Аня <3»: приветствие всё равно должно прийти."""
    anya = e2e.user("Аня <3")

    greeting = await anya.send("/start")

    assert "Аня <3" in greeting.text


async def test_registration_counts_as_activity(e2e):
    """Админка показывает время последней активности даже у того, кто сделал только /start."""
    anya = e2e.user("Аня")
    await anya.send("/start")

    user = await db_user(anya.id)
    assert user.last_seen_at is not None, "в админке у такого ученика «Последняя активность: —»"

