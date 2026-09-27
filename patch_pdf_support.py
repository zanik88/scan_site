#!/usr/bin/env python3
"""
Патч: поддержка PDF в парсере.
Извлекает текст через pypdf и обрабатывает построчно,
как обычный текстовый файл.
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_pdf_support"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Вставляем ветку "elif ext == 'pdf':" перед финальным else в parse_uploaded_file
# Ищем уникальный якорь — блок с dependencies и следующим else
anchor = '''            elif "dependencies" in data:
                for dep, ver in data.get("dependencies", {}).items():
                    if not _is_garbage_component(dep):
                        extracted.append({"name": dep, "version": str(ver)})
        else:'''

new_block = '''            elif "dependencies" in data:
                for dep, ver in data.get("dependencies", {}).items():
                    if not _is_garbage_component(dep):
                        extracted.append({"name": dep, "version": str(ver)})
        elif ext == "pdf":
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
                    extracted.append({"name": name, "version": ver})
        else:'''

if anchor in content:
    content = content.replace(anchor, new_block, 1)
    print("✅ Ветка 'elif ext == \"pdf\"' добавлена в parse_uploaded_file")
else:
    print("❌ Якорь не найден. Проверьте структуру parse_uploaded_file.")
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
