"""
Управление версиями сервиса «Компонент-Эксперт».

Версия берётся из последнего git-тега (формат vX.Y.Z).
Если git недоступен — используется VERSION_FALLBACK.
"""
import subprocess
import os
from datetime import datetime

# Резервная версия, если git-тег недоступен
VERSION_FALLBACK = "9.2.0"

# История версий (от новых к старым)
CHANGELOG = [
    {
        "version": "9.2.0",
        "date": "2026-09-26",
        "changes": [
            "Добавлено 80+ правил для DevTools, языков, ML-библиотек",
            "Снижен параллелизм ИИ-запросов до 3 (защита от rate limit GigaChat)",
        ]
    },
    {
        "version": "9.1.2",
        "date": "2026-09-26",
        "changes": [
            "TTL неудачных ИИ-ответов уменьшен с 7 дней до 1 часа",
            "Текст в админ-панели обновлён",
        ]
    },
    {
        "version": "9.1.1",
        "date": "2026-09-26",
        "changes": [
            "Исправлен /health: версия берётся из APP_VERSION",
        ]
    },
    {
        "version": "9.1.0",
        "date": "2026-09-26",
        "changes": [
            "Добавлены категории: Мониторинг и логирование",
            "Добавлены категории: Очереди сообщений",
            "Убраны дубликаты из СУБД (kafka, rabbitmq, elasticsearch)",
        ]
    },
    {
        "version": "9.0.0",
        "date": "2026-09-26",
        "changes": [
            "Интеграция GigaChat через OAuth 2.0 (обмен Authorization Key на access_token)",
            "Кэширование ИИ-ответов в SQLite (TTL 90 дней, экономия API)",
            "Rate Limiting: 5/мин на /upload, 30/мин для Pro, 120/мин для остальных",
            "Проверка CVE через OSV API (пакетные запросы, серьёзность по CVSS)",
            "Статистика AI-кэша в админ-панели с расчётом экономии",
            "13 категорий компонентов с фильтрами",
            "Полная база знаний из таблицы Минцифры (DevExpress, IBM DB2, Splunk)",
            "Кнопка «Наверх» на всех страницах",
            "Убран YandexGPT из выпадающего списка (нет ключа)",
        ]
    },
    {
        "version": "8.7.0",
        "date": "2026-09-25",
        "changes": [
            "Initial release",
            "Парсинг 5+ форматов файлов",
            "Docker-сканер",
            "Интеграция YandexGPT / GigaChat",
            "База знаний 250+ правил",
            "Экспорт в Excel",
            "Мультипользовательский режим с тарифами",
            "Админ-панель с обратной связью",
        ]
    },
]


def get_version() -> str:
    """
    Возвращает текущую версию.
    Сначала пробует git describe, при неудаче — VERSION_FALLBACK.
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if result.returncode == 0 and result.stdout.strip():
            tag = result.stdout.strip()
            # Убираем префикс "v" если есть
            return tag.lstrip("v")
    except Exception:
        pass
    return VERSION_FALLBACK


def get_version_info() -> dict:
    """Возвращает словарь с версией, датой сборки и changelog."""
    return {
        "version": get_version(),
        "fallback": VERSION_FALLBACK,
        "build_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "changelog": CHANGELOG,
    }


# Для быстрого импорта
__version__ = get_version()
