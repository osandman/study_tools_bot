EXACT_SUBJECT_EMOJIS = {
    "Математика": "➗",
    "Русский язык": "✍️",
    "Литература": "📚",
    "Физика": "⚛️",
    "Химия": "🧪",
    "Биология": "🧬",
    "История": "🏛️",
    "Обществознание": "👥",
    "География": "🌍",
    "Английский язык": "🇬🇧",
    "Информатика": "💻",
    "Физкультура": "🏃",
}

KEYWORD_EMOJIS = [
    (("матем", "алгеб", "геометр"), "➗"),
    (("русск", "язык", "диктант", "сочинен"), "✍️"),
    (("литер", "книга", "чтени"), "📚"),
    (("физик",), "⚛️"),
    (("хими",), "🧪"),
    (("биолог",), "🧬"),
    (("истор",), "🏛️"),
    (("обществ", "соци", "право"), "👥"),
    (("географ",), "🌍"),
    (("англ", "english"), "🇬🇧"),
    (("информ", "програм", "it", "компьют"), "💻"),
    (("физкул", "спорт", "gym", "pe"), "🏃"),
    (("музык",), "🎵"),
    (("рисован", "изо", "art"), "🎨"),
]


def get_subject_emoji(name: str) -> str:
    normalized = name.strip()
    emoji = EXACT_SUBJECT_EMOJIS.get(normalized)
    if emoji:
        return emoji

    lower_name = normalized.lower()
    for keywords, keyword_emoji in KEYWORD_EMOJIS:
        if any(keyword in lower_name for keyword in keywords):
            return keyword_emoji

    return "📘"


def format_subject_name(name: str) -> str:
    return f"{get_subject_emoji(name)} {name}"
