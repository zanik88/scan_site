#!/usr/bin/env python3
"""Убирает ссылку на GitHub со страницы /about."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_no_github_link"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Убираем строку со ссылкой на GitHub
old_line = '''            <li><a href="https://github.com/zanik88/scan_site" target="_blank">GitHub-репозиторий</a></li>
'''

if old_line in content:
    content = content.replace(old_line, '', 1)
    print("✅ Ссылка на GitHub убрана со страницы /about")
else:
    print("⚠️ Строка со ссылкой на GitHub не найдена")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.3.1")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
