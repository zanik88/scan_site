#!/usr/bin/env python3
"""Fix: убираем аннотацию типа Optional[User] в check_rate_limit."""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak_fix"


def backup():
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch():
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    old = 'def check_rate_limit(request: Request, endpoint: str, user: Optional[User] = None) -> tuple:'
    new = 'def check_rate_limit(request: Request, endpoint: str, user=None) -> tuple:'

    if old in content:
        content = content.replace(old, new, 1)
        print("✅ Патч применён: аннотация Optional[User] убрана")
    else:
        print("⚠️ Строка не найдена. Возможно, уже исправлено.")
        return False

    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    return False


if __name__ == "__main__":
    print("=" * 50)
    print("🔧 Fix: Optional[User] в check_rate_limit")
    print("=" * 50)
    backup()
    if not patch():
        sys.exit(0)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose up -d --build")
