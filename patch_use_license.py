#!/usr/bin/env python3
"""
Патч: использовать готовую лицензию из документа (_license),
не обращаясь к базе знаний и GigaChat.
"""
import shutil
import os
import sys

MAIN = "main.py"
BAK = "main.py.bak_use_license"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Добавить параметр pre_license в fetch_package_info_with_version
# ============================================================
old_sig = '''async def fetch_package_info_with_version(session, package_name, table_version, cached_rules,
                                          report_id, ai_provider="auto") -> dict:'''

new_sig = '''async def fetch_package_info_with_version(session, package_name, table_version, cached_rules,
                                          report_id, ai_provider="auto", pre_license=None) -> dict:'''

if old_sig in content:
    content = content.replace(old_sig, new_sig, 1)
    patched.append("Параметр pre_license в fetch_package_info_with_version")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: сигнатура функции не найдена")

# ============================================================
# 2. Внутри функции — если pre_license передан, сразу вернуть результат
# ============================================================
old_body = '''    search_clean = sanitize_string(package_name)

    # Приватные библиотеки — сразу возвращаем результат без ИИ'''

new_body = '''    search_clean = sanitize_string(package_name)

    # Если лицензия уже извлечена из документа — используем её без ИИ
    if pre_license:
        lic_lower = pre_license.lower()
        # Определяем статус по ключевым словам в лицензии
        forbidden_markers = [
            "proprietary", "commercial", "eula", "nvidia", "oracle",
            "microsoft", "aws", "google cloud", "sspl", "bsl",
        ]
        attention_markers = [
            "gpl-3", "gplv3", "agpl", "lgpl", "mpl", "busl", "sspl",
            "openjdk", "gpl-2", "gplv2",
        ]
        if any(m in lic_lower for m in forbidden_markers):
            status = "⚠️ Требует внимания"
        elif any(m in lic_lower for m in attention_markers):
            status = "Разрешено с условиями"
        else:
            status = "✅ Разрешено"
        return {
            "name": package_name,
            "version": table_version,
            "license": pre_license,
            "status": f"{status} <br><small style='color:#4a5568;'>💡 Лицензия из документа</small>",
        }

    # Приватные библиотеки — сразу возвращаем результат без ИИ'''

if old_body in content:
    content = content.replace(old_body, new_body, 1)
    patched.append("Использование pre_license в fetch_package_info_with_version")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: тело функции не найдено")

# ============================================================
# 3. Передать _license из process_audit_task
# ============================================================
old_call = '''                res = await fetch_package_info_with_version(
                    session, item["name"], item["version"], cached_rules, report_id, ai_provider)'''

new_call = '''                res = await fetch_package_info_with_version(
                    session, item["name"], item["version"], cached_rules, report_id, ai_provider,
                    pre_license=item.get("_license"))'''

if old_call in content:
    content = content.replace(old_call, new_call, 1)
    patched.append("Передача _license из process_audit_task")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: вызов fetch_package_info_with_version не найден")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print()
print("Патчей применено:", len(patched))
for p in patched:
    print("  •", p)

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
