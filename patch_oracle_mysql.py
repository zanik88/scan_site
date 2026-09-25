#!/usr/bin/env python3
"""
Патч №3: исправление логики Oracle MySQL.
- Community Edition → ✅ Разрешено (GPL)
- Commercial / Enterprise → ❌ Запрещено
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak3"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch(content: str) -> tuple:
    """Убирает 'oracle mysql' из banned_db и добавляет корректную проверку."""
    # 1. Убираем строку из banned_db
    old_line = '''        ("oracle nosql", "Oracle NoSQL"),
        ("oracle mysql", "Oracle MySQL"),
        ("oracle database", "Oracle Database"),'''

    new_line = '''        ("oracle nosql", "Oracle NoSQL"),
        ("oracle database", "Oracle Database"),'''

    patched = False
    if old_line in content:
        content = content.replace(old_line, new_line, 1)
        print("✅ Убрана строка 'oracle mysql' из banned_db")
        patched = True
    else:
        print("⚠️ Строка 'oracle mysql' в banned_db не найдена (возможно, уже убрана)")

    # 2. Добавляем явную проверку ПЕРЕД banned_db
    anchor = '''    # Запрещённые СУБД
    banned_db = ['''

    new_check = '''    # Oracle MySQL — различаем Community (разрешено) и Commercial (запрещено)
    if "mysql" in search_clean:
        if "community" in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "GPL-2.0",
                    "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 MySQL Community Edition — открытая лицензия (GPL)</small>"}
        elif "oracle" in search_clean or "enterprise" in search_clean or "cluster" in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Oracle MySQL (Commercial). Замена: MySQL Community / MariaDB / Postgres Pro</small>"}

    # Запрещённые СУБД
    banned_db = ['''

    if anchor in content:
        content = content.replace(anchor, new_check, 1)
        print("✅ Добавлена корректная проверка Oracle MySQL (Community vs Commercial)")
        patched = True
    else:
        print("⚠️ Якорь 'banned_db' не найден")

    return content, patched


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем из backup...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    print("✅ Восстановлено")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Патч №3: исправление логики Oracle MySQL")
    print("=" * 60)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content, ok = patch(content)
    if not ok:
        print("\n❌ Патч не применён.")
        if input("Восстановить? (y/n): ").strip().lower() == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
        sys.exit(1)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите контейнер:")
    print("   docker compose down && docker compose up -d --build")
