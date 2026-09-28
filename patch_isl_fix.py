#!/usr/bin/env python3
"""
Fix: убрать "isl" из license_keywords, чтобы бралась MIT License.
Плюс: пропускать очень короткие группы в скобках (<= 4 символов),
если они не содержат ключевых слов лицензий.
"""
import shutil
import os
import sys

MAIN = "main.py"
BAK = "main.py.bak_isl_fix"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# ============================================================
# 1. Убрать "isl" из списка license_keywords
# ============================================================
old_kw = '''    license_keywords = [
        "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
        "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
        "public domain", "psf", "python", "openssl", "curl",
        "openldap", "лиценз", "соглашение", "zero clause",
        "isl", "exception", "runtime", "foundation",
    ]'''

new_kw = '''    license_keywords = [
        "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
        "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
        "public domain", "psf", "python", "openssl", "curl",
        "openldap", "лиценз", "соглашение", "zero clause",
        "exception", "runtime", "foundation",
    ]'''

if old_kw in content:
    content = content.replace(old_kw, new_kw, 1)
    print("OK: убран 'isl' из license_keywords")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: список ключевых слов не найден")

# ============================================================
# 2. Пропускать короткие группы без ключевых слов
# ============================================================
old_loop = '''    license_text = None
    for g in reversed(groups):
        g_lower = g.lower()
        if any(k in g_lower for k in license_keywords):
            license_text = g.strip()
            break'''

new_loop = '''    license_text = None
    for g in reversed(groups):
        g_lower = g.lower()
        g_stripped = g.strip()
        # Пропускаем слишком короткие группы (аббревиатуры), если нет ключевых слов
        if len(g_stripped) <= 5 and not any(k in g_lower for k in ["mit", "bsd", "gpl", "apache"]):
            continue
        if any(k in g_lower for k in license_keywords):
            license_text = g_stripped
            break'''

if old_loop in content:
    content = content.replace(old_loop, new_loop, 1)
    print("OK: фильтр коротких групп добавлен")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: цикл поиска license_text не найден")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print()
print("Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("OK: синтаксис корректен")
    print()
    print("Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("ОШИБКА! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
