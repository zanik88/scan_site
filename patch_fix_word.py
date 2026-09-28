#!/usr/bin/env python3
"""
Fix двух багов:
1. Несовпадение ключей: "license" → "_license"
2. Поддержка формата Word/Markdown: лицензия в квадратных скобках [License](url)
"""
import shutil
import os
import sys

MAIN = "main.py"
BAK = "main.py.bak_fix_word"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Заменить _parse_license_doc_line на версию с поддержкой [License](url)
# ============================================================
old_func_start = "def _parse_license_doc_line(line: str):"
old_func_end = "def _is_section_header(line: str) -> bool:"

new_func = '''def _parse_license_doc_line(line: str):
    """
    Парсит строку формата "Название (Лицензия)" или "Название ([Лицензия](url))".
    Возвращает (name, license) или None.
    """
    line = line.strip()
    if not line:
        return None
    line = line.rstrip(".")

    # Приоритет 1: Markdown-формат [License Text](url)
    md_groups = re.findall(r'\\[([^\\]]+)\\]\\([^)]+\\)', line)
    if md_groups:
        license_keywords = [
            "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
            "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
            "public domain", "psf", "python", "openssl", "curl",
            "openldap", "лиценз", "соглашение", "zero clause",
            "exception", "runtime", "foundation",
        ]
        license_text = None
        for g in reversed(md_groups):
            g_lower = g.lower()
            g_stripped = g.strip()
            if len(g_stripped) <= 5 and not any(k in g_lower for k in ["mit", "bsd", "gpl", "apache"]):
                continue
            if any(k in g_lower for k in license_keywords):
                license_text = g_stripped
                break
        if license_text:
            name_match = re.match(r'^([^\\[(]+?)\\s*[\\(\\[]', line)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) >= 2:
                    return (name, license_text)

    # Приоритет 2: Круглые скобки (Nazvanie (License))
    groups = re.findall(r'\\(([^()]+)\\)', line)
    if groups:
        license_keywords = [
            "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
            "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
            "public domain", "psf", "python", "openssl", "curl",
            "openldap", "лиценз", "соглашение", "zero clause",
            "exception", "runtime", "foundation",
        ]
        license_text = None
        for g in reversed(groups):
            g_lower = g.lower()
            g_stripped = g.strip()
            if len(g_stripped) <= 5 and not any(k in g_lower for k in ["mit", "bsd", "gpl", "apache"]):
                continue
            if any(k in g_lower for k in license_keywords):
                license_text = g_stripped
                break
        if license_text:
            name_match = re.match(r'^([^(]+?)\\s*\\(', line)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) >= 2:
                    return (name, license_text)

    return None


''' + old_func_end

if old_func_start in content and old_func_end in content:
    start_idx = content.index(old_func_start)
    end_idx = content.index(old_func_end)
    content = content[:start_idx] + new_func + content[end_idx + len(old_func_end):]
    print("OK: _parse_license_doc_line обновлён (поддержка [License](url))")
else:
    print("ОШИБКА: функция не найдена")
    sys.exit(1)

# ============================================================
# 2. Исправить ключ "license" → "_license" в parse_uploaded_file
# ============================================================
old_key = '''                        extracted.append({
                            "name": name,
                            "version": "unknown",
                            "license": lic,
                        })'''
new_key = '''                        extracted.append({
                            "name": name,
                            "version": "unknown",
                            "_license": lic,
                        })'''

if old_key in content:
    content = content.replace(old_key, new_key, 1)
    print("OK: ключ 'license' → '_license' в parse_uploaded_file")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: блок extracted.append с 'license' не найден")

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
