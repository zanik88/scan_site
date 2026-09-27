#!/usr/bin/env python3
"""
Патч v5: финальная чистка парсера.
1. Убирает заголовки таблиц: "Name Version License Source",
   "Компонент Версия Лицензия Правообладатель"
2. Убирает "Версия программного продукта: 1.0.0"
3. Добавляет archive.* в приватные библиотеки
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_parser_v5"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Улучшить _is_garbage_component — заголовки таблиц
# ============================================================
old_check = '''    # Строки с "для установки", "this document"
    if "для установки" in lower or "this document" in lower:
        return True
    return False'''

new_check = '''    # Строки с "для установки", "this document"
    if "для установки" in lower or "this document" in lower:
        return True
    # Заголовки таблиц: name + version + license (+ source)
    table_headers = [
        "name version license",
        "name version license source",
        "компонент версия лицензия",
        "компонент версия лицензия правообладатель",
        "наименование версия лицензия",
    ]
    if any(lower.startswith(h) for h in table_headers):
        return True
    # Строки про "версия программного продукта"
    if lower.startswith(("версия программного продукта", "версия по", "программное обеспечение")):
        return True
    return False'''

if old_check in content:
    content = content.replace(old_check, new_check, 1)
    patched.append("_is_garbage_component: фильтр заголовков таблиц")
else:
    print("⚠️ Якорь конца _is_garbage_component не найден")

# ============================================================
# 2. Добавить archive. в приватные библиотеки
# ============================================================
old_private = '''    private_markers = [
        "ru.logic.bpm", "logicbpm", "@logicbpm", "logic.bpm",
        "tenant-encryption", "tenant-interceptor", "tenant-kafka",
        "tenant-security", "tenant-storage",
    ]'''

new_private = '''    private_markers = [
        "ru.logic.bpm", "logicbpm", "@logicbpm", "logic.bpm",
        "tenant-encryption", "tenant-interceptor", "tenant-kafka",
        "tenant-security", "tenant-storage",
        "archive.adminapi", "archive.bl", "archive.cryptography",
    ]'''

if old_private in content:
    content = content.replace(old_private, new_private, 1)
    patched.append("Приватные библиотеки: добавлены archive.*")
else:
    print("⚠️ Якорь private_markers не найден")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите локально:")
    print("   docker compose down && docker compose build --no-cache && docker compose up -d")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
