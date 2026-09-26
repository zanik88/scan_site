#!/usr/bin/env python3
"""Временно скрывает Docker-сканер из UI (код обработки остаётся)."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_hide_docker"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Убрать блок "Способ 3: Сканировать Docker-образ" из FILE_UPLOAD_HTML
# ============================================================
old_block = '''    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px dashed #cbd5e0;">
        <h4 style="margin: 0 0 10px 0; color: #2d3748; font-size: 14px;">🐳 Способ 3: Сканировать Docker-образ</h4>
        <input type="text" name="docker_image" placeholder="ubuntu:22.04 / python:3.12-slim / node:20-alpine" style="width: 100%; padding: 10px; border: 1px solid #cbd5e0; border-radius: 4px; font-family: monospace;">
        <div style="font-size: 11px; color: #718096; margin-top: 5px;">Система поднимет контейнер, определит базовую ОС и проверит пакеты.</div>
    </div>'''

new_block = '''    <!-- Docker-сканер временно отключён. Вернём после доработки. -->'''

if old_block in content:
    content = content.replace(old_block, new_block, 1)
    patched.append("Docker-сканер убран из UI")
else:
    print("⚠️ Блок Docker-сканера не найден в FILE_UPLOAD_HTML")

# ============================================================
# 2. Убрать упоминание Docker из GUIDELINES_HTML (опционально)
# ============================================================
old_guide = '''        <li><b>Docker:</b> укажите <code>image:tag</code></li>
'''
if old_guide in content:
    content = content.replace(old_guide, '', 1)
    patched.append("Упоминание Docker в рекомендациях убрано")

# ============================================================
# 3. Обновить заголовок "Способ 3" → "Два способа загрузки"
# ============================================================
old_h3 = '📂 Загрузите файл, вставьте список или укажите Docker-образ'
new_h3 = '📂 Загрузите файл или вставьте список компонентов'
if old_h3 in content:
    content = content.replace(old_h3, new_h3, 1)
    patched.append("Заголовок формы обновлён (без Docker)")

# ============================================================
# 4. Обновить описание в /about — убрать Docker из технологий
# ============================================================
old_about = '''            <span>Docker</span>'''
if old_about in content:
    # не удаляем — Docker всё ещё используется для деплоя, оставляем
    pass

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.2.3")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
