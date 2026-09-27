#!/usr/bin/env python3
"""Убирает PDF из UI (accept файла + рекомендации + отклонение на бэкенде)."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_hide_pdf"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Убрать .pdf из accept в input file
# ============================================================
old_accept = 'accept=".txt,.xlsx,.xls,.docx,.pdf,.json"'
new_accept = 'accept=".txt,.xlsx,.xls,.docx,.json"'

if old_accept in content:
    content = content.replace(old_accept, new_accept, 1)
    patched.append("Убран .pdf из accept файла")

# ============================================================
# 2. Убрать упоминание PDF из рекомендаций
# ============================================================
old_guide = '''<li><b>Word / PDF:</b> Maven-координаты, списки с тире.</li>'''
new_guide = '''<li><b>Word:</b> Maven-координаты, списки с тире.</li>'''

if old_guide in content:
    content = content.replace(old_guide, new_guide, 1)
    patched.append("Убрано упоминание PDF в рекомендациях")

# ============================================================
# 3. Отклонять PDF на бэкенде с понятным сообщением
# ============================================================
old_check = '''    if not unlimited and user:
        user.free_checks_used = (user.free_checks_used or 0) + 1
        db.commit()'''

new_check = '''    # Отклоняем PDF с понятным сообщением
    if file and file.filename and file.filename.lower().endswith(".pdf"):
        return HTMLResponse(
            """<html><head><meta charset="UTF-8"><title>Формат не поддерживается</title>
            <style>body{font-family:sans-serif;text-align:center;padding:60px;background:#f7fafc;}
            .card{background:white;max-width:520px;margin:0 auto;padding:40px;border-radius:8px;
            border-top:5px solid #dd6b20;box-shadow:0 4px 12px rgba(0,0,0,0.05);}
            h1{color:#dd6b20;} p{color:#4a5568;line-height:1.6;}</style></head><body>
            <div class="card">
              <h1>📄 PDF временно не поддерживается</h1>
              <p>Извлечение компонентов из PDF даёт много ложных срабатываний.</p>
              <p>Пожалуйста, загрузите файл в одном из форматов:</p>
              <p style="font-family:monospace;background:#edf2f7;padding:10px;border-radius:4px;">
              .txt · .json · .xlsx · .docx</p>
              <p><a href="/" style="color:#3182ce;font-weight:600;">← Вернуться на главную</a></p>
            </div>
            </body></html>""",
            status_code=400,
        )

    if not unlimited and user:
        user.free_checks_used = (user.free_checks_used or 0) + 1
        db.commit()'''

if old_check in content:
    content = content.replace(old_check, new_check, 1)
    patched.append("Бэкенд отклоняет PDF с сообщением")
else:
    print("⚠️ Якорь в upload не найден")

# ============================================================
# 4. Обновить текст описания формы
# ============================================================
old_h3 = '📂 Загрузите файл или вставьте список компонентов'
new_h3 = '📂 Загрузите файл (.txt, .json, .xlsx, .docx) или вставьте список'

if old_h3 in content:
    content = content.replace(old_h3, new_h3, 1)
    patched.append("Обновлён заголовок формы")

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
