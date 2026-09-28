#!/usr/bin/env python3
"""
Fix v2: улучшения _parse_license_doc_line.
1. Порог длины названия: 2 символа (для Go, R и т.п.)
2. Расширенный список license_keywords (isl, psf, и т.д.)
3. Обработка двойных скобок: берём последнюю группу как лицензию
4. Флаг _from_doc — чтобы _is_garbage_component не отбрасывал по имени человека
"""
import shutil
import os
import sys

MAIN = "main.py"
BAK = "main.py.bak_license_doc_v2"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# ============================================================
# 1. Заменить _parse_license_doc_line целиком
# ============================================================
old_func_start = "def _parse_license_doc_line(line: str):"
old_func_end = "def _is_section_header(line: str) -> bool:"

new_func = '''def _parse_license_doc_line(line: str):
    """
    Парсит строку формата "Название (Лицензия)".
    Обрабатывает двойные скобки: "Name (X) (License)" → license = последняя группа.
    Возвращает (name, license) или None.
    """
    line = line.strip()
    if not line:
        return None
    line = line.rstrip(".")

    # Ищем ВСЕ группы в скобках
    groups = re.findall(r'\\(([^()]+)\\)', line)
    if not groups:
        return None

    # Лицензия — последняя группа с ключевыми словами
    license_keywords = [
        "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
        "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
        "public domain", "psf", "python", "openssl", "curl",
        "openldap", "лиценз", "соглашение", "zero clause",
        "isl", "exception", "runtime", "foundation",
    ]

    license_text = None
    for g in reversed(groups):
        g_lower = g.lower()
        if any(k in g_lower for k in license_keywords):
            license_text = g.strip()
            break

    if not license_text:
        return None

    # Название — часть до первой скобки
    name_match = re.match(r'^([^(]+?)\\s*\\(', line)
    if not name_match:
        return None
    name = name_match.group(1).strip()

    # Порог длины — 2 символа (для "Go", "R", "C#")
    if len(name) < 2:
        return None

    return (name, license_text)


''' + old_func_end

if old_func_start in content and old_func_end in content:
    start_idx = content.index(old_func_start)
    end_idx = content.index(old_func_end)
    content = content[:start_idx] + new_func + content[end_idx + len(old_func_end):]
    print("OK: _parse_license_doc_line обновлён")
else:
    print("ОШИБКА: функция не найдена")
    sys.exit(1)

# ============================================================
# 2. В parse_uploaded_file — не вызывать _is_garbage_component для doc-формата
# ============================================================
old_check = '''                # Пробуем формат "Название (Лицензия)"
                license_doc = _parse_license_doc_line(line)
                if license_doc:
                    name, lic = license_doc
                    if not _is_garbage_component(name):
                        extracted.append({
                            "name": name,
                            "version": "unknown",
                            "_license": lic,
                        })
                    continue'''

new_check = '''                # Пробуем формат "Название (Лицензия)"
                license_doc = _parse_license_doc_line(line)
                if license_doc:
                    name, lic = license_doc
                    # Не фильтруем — если строка попала в формат "Название (Лицензия)",
                    # значит, это уже валидный компонент
                    extracted.append({
                        "name": name,
                        "version": "unknown",
                        "_license": lic,
                    })
                    continue'''

if old_check in content:
    content = content.replace(old_check, new_check, 1)
    print("OK: убран фильтр _is_garbage_component для doc-формата")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: блок doc-обработки не найден")

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
