#!/usr/bin/env python3
"""Fix: get_free_checks_left открывает собственную сессию для сброса Pro."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_pro_session"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

old_block = """        if days_passed >= 30:
            user.pro_checks_used = 0
            user.pro_period_start = now
            if db:
                try:
                    db.commit()
                except Exception:
                    db.rollback()"""

new_block = """        if days_passed >= 30:
            db_local = SessionLocal()
            try:
                db_user = db_local.query(User).filter(User.id == user.id).first()
                if db_user:
                    db_user.pro_checks_used = 0
                    db_user.pro_period_start = now
                    db_local.commit()
                    user.pro_checks_used = 0
                    user.pro_period_start = now
            except Exception as e:
                db_local.rollback()
                print("[PRO RESET] error:", e)
            finally:
                db_local.close()"""

if old_block in content:
    content = content.replace(old_block, new_block, 1)
    print("OK: блок заменён на SessionLocal()")
else:
    print("ОШИБКА: старый блок не найден")
    sys.exit(1)

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print()
print("Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("OK: синтаксис корректен")
    print()
    print("Готово! Пересоберите:")
    print("   docker compose down && docker compose build --no-cache && docker compose up -d")
else:
    print("ОШИБКА! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
