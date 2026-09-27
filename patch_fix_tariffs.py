#!/usr/bin/env python3
"""
Fix: get_free_checks_left без обязательного db.
1. Убираем db из всех вызовов.
2. Внутри функции сами открываем сессию, если db не передан.
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_fix_tariffs"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Убрать db из всех вызовов get_free_checks_left
# ============================================================
count1 = content.count("get_free_checks_left(user, request, db)")
if count1 > 0:
    content = content.replace("get_free_checks_left(user, request, db)", "get_free_checks_left(user, request)")
    patched.append(f"Убрано db из {count1} вызовов get_free_checks_left")

# ============================================================
# 2. Улучшить функцию — сама открывает сессию при необходимости
# ============================================================
old_func = '''def get_free_checks_left
