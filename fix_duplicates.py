#!/usr/bin/env python3
"""Удаляет ВТОРОЕ определение check_rate_limit и ВТОРОЙ вызов в /upload."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_fixdup"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    lines = f.readlines()

# --- 1. Найти все строки с "def check_rate_limit"
def_lines = [i for i, l in enumerate(lines) if "def check_rate_limit" in l]
print(f"🔍 Определений check_rate_limit: {len(def_lines)} → строки {[i+1 for i in def_lines]}")

if len(def_lines) >= 2:
    # Удалить всё от второго определения до строки с "return True, limit - len(bucket), 0"
    start = def_lines[1]
    end = None
    for j in range(start, len(lines)):
        if "return True, limit - len(bucket), 0" in lines[j]:
            end = j
            break
    if end:
        # Удалить блок + пустые строки после
        del lines[start:end+1]
        print(f"✅ Удалён дубликат check_rate_limit: строки {start+1}–{end+1}")
    else:
        print("⚠️ Не найден конец второго check_rate_limit")

# --- 2. Найти все строки с 'check_rate_limit(request, "/upload"' ПОСЛЕ обновления
with open(MAIN, "w", encoding="utf-8") as f:
    f.writelines(lines)

# Перечитываем
with open(MAIN, "r", encoding="utf-8") as f:
    lines = f.readlines()

upload_calls = [i for i, l in enumerate(lines) if 'check_rate_limit(request, "/upload"' in l]
print(f"🔍 Вызовов в /upload: {len(upload_calls)} → строки {[i+1 for i in upload_calls]}")

if len(upload_calls) >= 2:
    # Удалить второй вызов вместе с его HTML-блоком 429
    start = upload_calls[1]
    # Идём назад до пустой строки или до предыдущего кода
    # Идём вперёд до закрывающей скобки ) после 'headers={"Retry-After": str(retry_after)},'
    end = None
    for j in range(start, len(lines)):
        if "Retry-After" in lines[j]:
            # Следующая строка — закрывающая ) и пустая
            end = j + 2
            break
    if end:
        del lines[start:end]
        print(f"✅ Удалён дубликат вызова в /upload: строки {start+1}–{end}")

# --- 3. Найти все определения констант
with open(MAIN, "w", encoding="utf-8") as f:
    f.writelines(lines)

with open(MAIN, "r", encoding="utf-8") as f:
    lines = f.readlines()

const_lines = [i for i, l in enumerate(lines) if "RATE_LIMIT_WINDOW = 60" in l]
print(f"🔍 Определений RATE_LIMIT_WINDOW: {len(const_lines)} → строки {[i+1 for i in const_lines]}")

if len(const_lines) >= 2:
    # Удалить второе определение + следующие 3 строки (GUEST, PRO, GENERAL) + _RATE_BUCKETS
    start = const_lines[1]
    # Второе определение обычно ниже вызовов; удалить строки start..start+5
    # Найдём конец блока - строку с '_RATE_BUCKETS = defaultdict(list)'
    end = None
    for j in range(start, len(lines)):
        if "_RATE_BUCKETS = defaultdict(list)" in lines[j]:
            end = j
            break
    if end:
        del lines[start:end+1]
        print(f"✅ Удалён дубликат констант: строки {start+1}–{end+1}")

with open(MAIN, "w", encoding="utf-8") as f:
    f.writelines(lines)

# --- Проверка синтаксиса
print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("❌ Синтаксическая ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    print("✅ Восстановлено из бэкапа")
