#!/usr/bin/env python3
"""
Патч: улучшенная обработка PDF.
Фильтрует артефакты извлечения: номера страниц, короткие строки,
повторяющиеся заголовки, многоточия из оглавления.
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_pdf_v2"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Заменяем блок PDF на улучшенный
old_pdf_block = '''        elif ext == "pdf":
            # Извлекаем текст из всех страниц PDF
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            full_text = ""
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\\n"
                except Exception as pe:
                    print(f"[PDF] Ошибка страницы: {pe}")
            # Обрабатываем как обычный текст
            for line in full_text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Пропускаем очень короткие строки
                if len(line) < 3:
                    continue
                name, ver = _split_name_version(line)
                if not _is_garbage_component(name):
                    extracted.append({"name": name, "version": ver})'''

new_pdf_block = '''        elif ext == "pdf":
            # Извлекаем текст из всех страниц PDF
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            full_text = ""
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\\n"
                except Exception as pe:
                    print(f"[PDF] Ошибка страницы: {pe}")

            # Собираем статистику по строкам (для поиска повторяющихся)
            lines_raw = [ln.strip() for ln in full_text.splitlines()]
            from collections import Counter
            line_counter = Counter([ln for ln in lines_raw if len(ln) >= 5])
            # Повторяющиеся больше 3 раз — это колонтитулы, пропускаем
            repeated_lines = {ln for ln, cnt in line_counter.items() if cnt >= 3}

            seen_names = set()
            for line in lines_raw:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Очень короткие строки (1-4 символа) — пропустить
                if len(line) < 5:
                    continue
                # Только цифры (номер страницы)
                if re.match(r'^\\d+$', line):
                    continue
                # Строка из точек/пробелов (оглавление)
                if re.match(r'^[\\s\\.\\u2026]+$', line):
                    continue
                # Строка с многоточием и цифрой в конце (оглавление)
                if re.search(r'\\.\\s*\\.\\s*\\.', line) and re.search(r'\\d+\\s*$', line):
                    continue
                # Повторяющаяся строка (колонтитул)
                if line in repeated_lines:
                    continue
                # Строка с "Оглавление" / "Содержание" / "стр."
                lower = line.lower()
                if lower.startswith(("оглавление", "содержание", "стр.", "страница", "page ")):
                    continue
                # Строка вида "1. FRONTEND . . . 3" (оглавление с номером страницы)
                if re.match(r'^\\d+\\.\\s+\\S+', line) and re.search(r'\\.{2,}', line):
                    continue
                # Строка вида "1" или "12" в конце (уже отфильтровано выше)
                # Разбираем на name + version
                name, ver = _split_name_version(line)
                if not name or len(name) < 3:
                    continue
                if _is_garbage_component(name):
                    continue
                # Дедупликация
                key = name.lower().strip()
                if key in seen_names:
                    continue
                seen_names.add(key)
                extracted.append({"name": name, "version": ver})'''

if old_pdf_block in content:
    content = content.replace(old_pdf_block, new_pdf_block, 1)
    print("✅ PDF-обработка улучшена: фильтр колонтитулов, страниц, оглавления")
else:
    print("❌ Старый блок PDF не найден. Возможно, патч уже применён.")
    sys.exit(1)

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите локально:")
    print("   docker compose down && docker compose build --no-cache && docker compose up -d")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
