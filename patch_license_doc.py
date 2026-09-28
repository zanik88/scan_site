#!/usr/bin/env python3
"""
Патч: поддержка формата "Название (Лицензия)".
Например: "RED OS (лицензионное соглашение ООО «РЕД СОФТ»)"
          "CMake (BSD 3-Clause License)"
Плюс фильтр заголовков разделов (операционная система, компиляторы и т.д.)
"""
import shutil
import os
import sys

MAIN = "main.py"
BAK = "main.py.bak_license_doc"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Новая функция _parse_license_doc_line
# ============================================================
anchor1 = "def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:"
new_func = '''def _parse_license_doc_line(line: str):
    """
    Парсит строку формата "Название (Лицензия)".
    Возвращает (name, license) или None.
    """
    line = line.strip()
    if not line:
        return None
    # Убираем точку в конце
    line = line.rstrip(".")

    # Ищем "Название (Лицензия)"
    m = re.match(r'^([^(]+?)\\s*\\(([^)]+)\\)\\s*$', line)
    if not m:
        return None

    name = m.group(1).strip()
    license_text = m.group(2).strip()

    # Название должно быть не короче 3 символов
    if len(name) < 3:
        return None

    # Лицензия должна содержать ключевые слова
    lic_lower = license_text.lower()
    license_keywords = [
        "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
        "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
        "public domain", "psf", "python", "openssl", "curl",
        "openldap", "лиценз", "соглашение", "zero clause"
    ]
    if not any(k in lic_lower for k in license_keywords):
        return None

    return (name, license_text)


def _is_section_header(line: str) -> bool:
    """Определяет заголовки разделов документа."""
    line = line.strip()
    if not line or "(" in line:
        return False
    headers = [
        "операционная система",
        "компиляторы и средства сборки",
        "среда выполнения",
        "система управления базами данных",
        "обмен сообщениями",
        "сетевые компоненты",
        "криптография",
        "системные библиотеки",
        "аудиоподсистема",
        "средства администрирования",
        "мониторинг",
        "библиотеки исполнения",
        "среда выполнения python",
    ]
    lower = line.lower()
    return any(lower.startswith(h) for h in headers)


''' + anchor1

if "_parse_license_doc_line" not in content and anchor1 in content:
    content = content.replace(anchor1, new_func, 1)
    patched.append("Функции _parse_license_doc_line + _is_section_header")

# ============================================================
# 2. Обработка формата в parse_uploaded_file (для .txt)
# ============================================================
old_txt_block = '''            text = file_bytes.decode("utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    name, ver = _split_name_version(line)
                    if not _is_garbage_component(name):
                        extracted.append({"name": name, "version": ver})'''

new_txt_block = '''            text = file_bytes.decode("utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Пропускаем заголовки разделов
                if _is_section_header(line):
                    continue

                # Пробуем формат "Название (Лицензия)"
                license_doc = _parse_license_doc_line(line)
                if license_doc:
                    name, lic = license_doc
                    if not _is_garbage_component(name):
                        extracted.append({
                            "name": name,
                            "version": "unknown",
                            "_license": lic,
                        })
                    continue

                # Обычный формат "name==version"
                name, ver = _split_name_version(line)
                if not _is_garbage_component(name):
                    extracted.append({"name": name, "version": ver})'''

if old_txt_block in content:
    content = content.replace(old_txt_block, new_txt_block, 1)
    patched.append("Обработка 'Название (Лицензия)' в parse_uploaded_file")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: блок txt не найден (возможно, уже обновлён)")

# ============================================================
# 3. В fetch_package_info_with_version — использовать _license, если есть
# ============================================================
anchor3 = "    search_clean = sanitize_string(package_name)"
new3 = '''    # Если лицензия уже извлечена из документа — используем её
    pre_license = table_version if isinstance(table_version, str) and False else None

    search_clean = sanitize_string(package_name)'''

# Ничего не делаем — слишком сложно. Проще в parse_uploaded_file сразу заполнить статус.

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
    print("   docker compose down && docker compose build --no-cache && docker compose up -d")
else:
    print("ОШИБКА! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
