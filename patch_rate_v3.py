#!/usr/bin/env python3
"""Fix: отдельные лимиты для /register и /feedback (3/мин)."""
import shutil, sys, os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak_rate_v3"


def backup():
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch(content):
    # 1. Добавляем словарь лимитов для конкретных эндпоинтов
    anchor1 = "RATE_LIMIT_GENERAL = 120\n"
    new1 = """RATE_LIMIT_GENERAL = 120
RATE_LIMIT_ENDPOINTS = {
    "/register": 3,
    "/feedback": 3,
}
"""
    if anchor1 in content:
        content = content.replace(anchor1, new1, 1)
        print("✅ Словарь RATE_LIMIT_ENDPOINTS добавлен")
    else:
        print("⚠️ Якорь RATE_LIMIT_GENERAL не найден")

    # 2. Меняем логику выбора лимита
    old = """    if user is not None and (getattr(user, "role", None) == "admin" or getattr(user, "subscription_plan", None) in ["Pro", "Unlimited"]):
        limit = RATE_LIMIT_PRO
    elif endpoint == "/upload":
        limit = RATE_LIMIT_GUEST
    else:
        limit = RATE_LIMIT_GENERAL
"""
    new = """    if user is not None and (getattr(user, "role", None) == "admin" or getattr(user, "subscription_plan", None) in ["Pro", "Unlimited"]):
        limit = RATE_LIMIT_PRO
    elif endpoint == "/upload":
        limit = RATE_LIMIT_GUEST
    elif endpoint in RATE_LIMIT_ENDPOINTS:
        limit = RATE_LIMIT_ENDPOINTS[endpoint]
    else:
        limit = RATE_LIMIT_GENERAL
"""
    if old in content:
        content = content.replace(old, new, 1)
        print("✅ Логика выбора лимита обновлена")
    else:
        print("⚠️ Якорь логики лимита не найден")

    return content


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    return False


if __name__ == "__main__":
    print("=" * 55)
    print("🔧 Rate Limiting v3: отдельные лимиты")
    print("=" * 55)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        c = f.read()
    c = patch(c)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(c)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
