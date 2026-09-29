"""
Управление версиями сервиса «Компонент-Эксперт».

Версия берётся из последнего git-тега (формат vX.Y.Z).
Если git недоступен — используется VERSION_FALLBACK.
"""
import subprocess
import os
from datetime import datetime

# Резервная версия, если git-тег недоступен
VERSION_FALLBACK = "9.5.5"

# История версий (от новых к старым)
CHANGELOG = [
    {
        "version": "9.5.5",
        "date": "2026-09-30",
        "changes": [
            "- Мобильная вёрстка: бургер-меню, скрытие разделителей |, адаптивные отступы",
            "- patch_mobile_css_v6: динамическое определение отступа (_mobile_css на 12 пробелах)",
            "- patch_burger_v1: замена 6 nav-обёрток на nav-burger + nav-links",
            "- patch_burger_v2: обёртка 10 разделителей в span.nav-sep",
        ]
    },
    {
        "version": "9.5.4",
        "date": "2026-09-29",
        "changes": [
            "- Профилактика матчинга: word-boundary (устранены коллизии libarchive/hive, django/go, predis/redis)",
            "- KB для клиентских библиотек: redis-py, predis, pymongo, mongodb-driver, firebird-driver, jaeger-client и др.",
            "- patch_kb_version v3: хеш от содержимого main.py",
            "- Фикс лицензий: _hard_all в главной функции (license, status, recommendation)",
            "- Мобильная вёрстка: @media (max-width: 768px) через middleware",
        ]
    },
    {
        "version": "9.5.3",
        "date": "2026-09-28",
        "changes": [
            "- Word-парсер: формат [License](url), ключ _license",
            "- KB: Qt, zlib, Eigen, QuaZIP, JKQTPlotter (hard-match до ИИ)",
            "- KB: ~45 компонентов (CMake, GCC, Go, LLVM, Python, PostgreSQL, glibc и др.)",
            "- Фикс libarchive (ложный матч с hive)",
            "- Авто-инвалидация ai_license_cache по хешу KB",
            "- Fix: COOKIE_SECURE берётся из .env (устранён хардкод)",
            "- Fix: восстановлен логин на проде (SECRET_KEY подхватывается из .env)",
        ]
    },
    {
        "version": "9.5.2",
        "date": "2026-09-28",
        "changes": [
            "Поддержка парсинга лицензий из Word-документов (.docx)",
            "Формат \"Название (Лицензия)\" и \"Название ([License](url))\"",
            "Использование лицензии из документа без обращения к GigaChat",
            "Очистка markdown-разметки из параграфов Word",
            "Фильтр заголовков разделов (Операционная система, Компиляторы и т.д.)",
        ]
    },
    {
        "version": "9.5.1",
        "date": "2026-09-27",
        "changes": [
            "Добавлен счётчик Яндекс.Метрики (ID 113107006)",
            "Исправлен middleware для вставки счётчика в HTML",
            "Добавлены robots.txt и sitemap.xml для SEO",
            "Meta-теги, favicon",
        ]
    },
    {
        "version": "9.5.0",
        "date": "2026-09-27",
        "changes": [
            "Флаг is_test для разделения тестовых и реальных",
        ]
    },
    {
        "version": "9.4.0",
        "date": "2026-09-27",
        "changes": [
            "Elasticsearch/OpenSearch/Kibana/Logstash → категория СУБД",
            "Добавлено 110+ Maven namespace-правил (Spring, Apache, Google, Bouncy Castle и др.)",
            "PDF временно убран из UI (много ложных срабатываний)",
            "Бэкенд отклоняет PDF с понятным сообщением",
            "Современный дизайн формы загрузки: карточки, бейджи форматов, градиентная кнопка",
        ]
    },
    {
        "version": "9.3.3",
        "date": "2026-09-27",
        "changes": [
            "Парсер v3-v5: Maven-координаты, npm, приватные библиотеки",
            "Убрана обрезка многословных названий компонентов",
            "Улучшен фильтр мусора: заголовки таблиц, описания, URL",
            "Добавлен ETA в прогресс-бар (осталось ~N мин)",
            "Пауза между ИИ-запросами уменьшена до 0.7 сек",
        ]
    },
    {
        "version": "9.3.2",
        "date": "2026-09-27",
        "changes": [
            "Улучшен парсер: формат с тире, фильтр заголовков, дедупликация",
            "Уменьшена пауза между ИИ-запросами (0.7 сек)",
            "Добавлен ETA в прогресс-бар (осталось ~N мин)",
        ]
    },
    {
        "version": "9.3.1",
        "date": "2026-09-27",
        "changes": [
            "Убрана ссылка на GitHub со страницы О сервисе",
        ]
    },
    {
        "version": "9.3.0",
        "date": "2026-09-27",
        "changes": [
            "Добавлена кнопка Отменить проверку на странице прогресса",
            "Новый эндпоинт POST /audit/{id}/cancel",
            "Отменённые отчёты помечаются статусом cancelled",
        ]
    },
    {
        "version": "9.2.3",
        "date": "2026-09-26",
        "changes": [
            "Docker-сканер временно убран из UI (вернём при развитии сервиса)",
        ]
    },
    {
        "version": "9.2.2",
        "date": "2026-09-26",
        "changes": [
            "Semaphore(1) — последовательные ИИ-запросы против rate limit GigaChat",
            "Retry на 429 с паузами 2/4/6 сек",
            "Пауза 1.5 сек между ИИ-запросами",
            "Добавлено 35+ правил: vLLM, llama.cpp, JupyterLab, ruff, OPA, TensorFlow и др.",
        ]
    },
    {
        "version": "9.2.1",
        "date": "2026-09-26",
        "changes": [
            "Добавлены правила: Filebeat, Fluent Bit, Jaeger, .NET SDK с версией",
            "Улучшен UI колонки Категория: цветные бейджи фиксированной ширины",
        ]
    },
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
