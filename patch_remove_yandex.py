#!/usr/bin/env python3
"""Убирает YandexGPT из выпадающего списка ИИ-анализа."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_no_yandex"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Заменить текст "Авто (YandexGPT → GigaChat → база)" на "Авто (GigaChat → база)"
old1 = '🔀 Авто (YandexGPT → GigaChat → база)'
new1 = '🔀 Авто (GigaChat → база)'

if old1 in content:
    content = content.replace(old1, new1)
    print("✅ Опция 'Авто' обновлена")
else:
    print("⚠️ Опция 'Авто' не найдена")

# 2. Удалить строку с опцией YandexGPT
old2 = '            <option value="yandex">YandexGPT</option>\n'
if old2 in content:
    content = content.replace(old2, '')
    print("✅ Опция 'YandexGPT' удалена")
else:
    print("⚠️ Опция 'YandexGPT' не найдена")

# 3. Обновить текст в соглашении (строка 2341)
old3 = 'При обращении к внешним ИИ-провайдерам (YandexGPT, GigaChat)'
new3 = 'При обращении к внешним ИИ-провайдерам (GigaChat)'
if old3 in content:
    content = content.replace(old3, new3)
    print("✅ Текст в соглашении обновлён")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

# Проверка синтаксиса
print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите локально:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("❌ Ошибка! Восстанавливаем из backup...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
