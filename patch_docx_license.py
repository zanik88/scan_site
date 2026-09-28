#!/usr/bin/env python3
"""
Патч: поддержка _parse_license_doc_line в ветке .docx.
Плюс очистка markdown-разметки ([text](url), **bold**) из параграфов Word.
"""
import shutil
import os
import sys

MAIN = "main.py"
BAK = "main.py.bak_docx_license"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# ============================================================
# 1. Добавить функцию очистки markdown перед _is_section_header
# ============================================================
anchor1 = "def _is_section_header(line: str) -> bool:"
new_func = '''def _clean_markdown(text: str) -> str:
    """Убирает markdown-разметку: [текст](url) → текст, **жирный** → жирный."""
    if not text:
        return text
    # [текст](url) → текст
    text = re.sub(r'\\[([^\\]]+)\\]\\([^)]+\\)', r'\\1', text)
    # **текст** → текст
    text = re.sub(r'\\*\\*([^*]+)\\*\\*', r'\\1', text)
    # *текст* → текст (курсив, но осторожно с умножением)
    text = re.sub(r'(?<![\\w*])\\*([^*\\n]+)\\*(?![\\w*])', r'\\1', text)
    # `код` → код
    text = re.sub(r'`([^`]+)`', r'\\1', text)
    return text.strip()


''' + anchor1

if "_clean_markdown" not in content and anchor1 in content:
    content = content.replace(anchor1, new_func, 1)
    print("OK: добавлена функция _clean_markdown")

# ============================================================
# 2. Заменить блок обработки docx
# ============================================================
old_docx = '''        elif ext == "docx":
            doc = docx.Document(io.BytesIO(file_bytes))
            for table in doc.tables:
                for row in table.rows:
                    row_vals = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_vals:
                        name = row_vals[0]
                        ver = row_vals[1] if len(row_vals) > 1 else "unknown"
                        if not _is_garbage_component(name):
                            extracted.append({"name": name, "version": ver})
            for p in doc.paragraphs:
                if p.text.strip():
                    parts = re.split(r'[\\t:,]+', p.text.strip())
                    if parts and not _is_garbage_component(parts[0]):
                        extracted.append({"name": parts[0].strip(), "version": parts[1].strip() if len(parts) > 1 else "unknown"})'''

new_docx = '''        elif ext == "docx":
            doc = docx.Document(io.BytesIO(file_bytes))
            # Обработка таблиц (как было)
            for table in doc.tables:
                for row in table.rows:
                    row_vals = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_vals:
                        name = row_vals[0]
                        ver = row_vals[1] if len(row_vals) > 1 else "unknown"
                        if not _is_garbage_component(name):
                            extracted.append({"name": name, "version": ver})
            # Обработка параграфов с поддержкой лицензий
            for p in doc.paragraphs:
                raw = p.text.strip()
                if not raw:
                    continue
                # Убираем markdown-разметку
                line = _clean_markdown(raw)
                if not line:
                    continue
                # Пропускаем заголовки разделов
                if _is_section_header(line):
                    continue
                # Пробуем формат "Название (Лицензия)" / "Название ([License](url))"
                license_doc = _parse_license_doc_line(raw)
                if not license_doc:
                    license_doc = _parse_license_doc_line(line)
                if license_doc:
                    name, lic = license_doc
                    extracted.append({
                        "name": name,
                        "version": "unknown",
                        "_license": lic,
                    })
                    continue
                # Обычная обработка — "name: version" или просто "name"
                parts = re.split(r'[\\t:,]+', line)
                if parts and parts[0] and not _is_garbage_component(parts[0]):
                    extracted.append({
                        "name": parts[0].strip(),
                        "version": parts[1].strip() if len(parts) > 1 else "unknown",
                    })'''

if old_docx in content:
    content = content.replace(old_docx, new_docx, 1)
    print("OK: ветка docx обновлена (поддержка _parse_license_doc_line)")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: блок docx не найден или уже обновлён")

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
