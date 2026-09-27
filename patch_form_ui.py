#!/usr/bin/env python3
"""Улучшает внешний вид формы загрузки (FILE_UPLOAD_HTML + submit-btn CSS)."""
import shutil, os, sys, re

MAIN = "main.py"
BAK = "main.py.bak_form_ui"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Заменить FILE_UPLOAD_HTML целиком
# ============================================================
new_form = '''FILE_UPLOAD_HTML = """
<div style="background: linear-gradient(135deg, #f8fafc 0%, #edf2f7 100%); border-radius: 14px; padding: 30px 25px; margin: 25px 0; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">

    <!-- Заголовок -->
    <div style="text-align: center; margin-bottom: 25px;">
        <div style="font-size: 36px; margin-bottom: 6px; line-height: 1;">📂</div>
        <h3 style="color: #1a365d; margin: 0 0 6px 0; font-size: 22px; font-weight: 700;">Загрузите компоненты</h3>
        <p style="color: #718096; margin: 0; font-size: 13px;">Файл, текст или список зависимостей для аудита</p>
    </div>

    <!-- Выбор ИИ -->
    <div style="display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 25px; flex-wrap: wrap;">
        <label style="font-size: 13px; font-weight: 600; color: #4a5568;">🧠 ИИ-анализ:</label>
        <select name="ai_provider" style="padding: 8px 16px; border-radius: 8px; border: 1px solid #cbd5e0; font-size: 13px; background: white; cursor: pointer; color: #2d3748; font-weight: 500;">
            <option value="auto" selected>🔀 Авто (GigaChat → база)</option>
            <option value="gigachat">GigaChat (Сбер)</option>
        </select>
    </div>

    <!-- Два способа: grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 5px;">

        <!-- Способ 1: Файл -->
        <div style="background: white; border-radius: 12px; padding: 22px 20px; border: 1px solid #e2e8f0; transition: all 0.2s ease;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                <span style="font-size: 22px;">📎</span>
                <div>
                    <div style="font-size: 15px; font-weight: 700; color: #2d3748;">Способ 1: Файл</div>
                    <div style="font-size: 11px; color: #718096;">Выберите файл с зависимостями</div>
                </div>
            </div>
            <input type="file" name="file" accept=".txt,.xlsx,.xls,.docx,.json" style="width: 100%; font-size: 13px; padding: 10px; border: 2px dashed #cbd5e0; border-radius: 8px; background: #f8fafc; cursor: pointer; box-sizing: border-box;">
            <div style="margin-top: 12px; display: flex; flex-wrap: wrap; gap: 5px;">
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.txt</span>
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.json</span>
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.xlsx</span>
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.docx</span>
            </div>
        </div>

        <!-- Способ 2: Текст -->
        <div style="background: white; border-radius: 12px; padding: 22px 20px; border: 1px solid #e2e8f0; transition: all 0.2s ease;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                <span style="font-size: 22px;">✏️</span>
                <div>
                    <div style="font-size: 15px; font-weight: 700; color: #2d3748;">Способ 2: Текст</div>
                    <div style="font-size: 11px; color: #718096;">Список вида имя==версия</div>
                </div>
            </div>
            <textarea name="text_input" maxlength="500" placeholder="fastapi==0.115.6&#10;pandas==2.2.3&#10;sqlalchemy==2.0.35" style="width: 100%; min-height: 100px; padding: 10px; border: 2px solid #cbd5e0; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 12px; resize: vertical; box-sizing: border-box; background: #f8fafc; line-height: 1.5;"></textarea>
        </div>

    </div>
</div>
"""'''

# Найти и заменить FILE_UPLOAD_HTML
pattern = re.compile(r'FILE_UPLOAD_HTML = """.*?"""', re.DOTALL)
if pattern.search(content):
    content = pattern.sub(new_form, content, count=1)
    patched.append("FILE_UPLOAD_HTML: современный дизайн")
else:
    print("❌ FILE_UPLOAD_HTML не найден")
    sys.exit(1)

# ============================================================
# 2. Обновить CSS для .submit-btn (в index())
# ============================================================
old_css = '''        .submit-btn {{ background: #2f855a; color: white; border: none; padding: 14px 32px; font-size: 15px; font-weight: 600; border-radius: 4px; cursor: pointer; width: 100%; margin-top: 15px; }}
        .submit-btn:hover {{ background: #276749; }}'''

new_css = '''        .submit-btn {{ background: linear-gradient(135deg, #38a169 0%, #2f855a 100%); color: white; border: none; padding: 16px 32px; font-size: 16px; font-weight: 700; border-radius: 10px; cursor: pointer; width: 100%; margin-top: 20px; box-shadow: 0 4px 12px rgba(47,133,90,0.25); transition: all 0.2s ease; letter-spacing: 0.3px; }}
        .submit-btn:hover {{ background: linear-gradient(135deg, #2f855a 0%, #276749 100%); box-shadow: 0 6px 16px rgba(47,133,90,0.35); transform: translateY(-1px); }}
        .submit-btn:active {{ transform: translateY(0); box-shadow: 0 2px 6px rgba(47,133,90,0.25); }}'''

if old_css in content:
    content = content.replace(old_css, new_css, 1)
    patched.append("CSS кнопки: градиент + hover-эффект")
else:
    print("⚠️ Старый CSS кнопки не найден (возможно, уже обновлён)")

# ============================================================
# 3. Адаптивность для мобильных (grid → 1 колонка)
# ============================================================
old_body_css = '''        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}'''
new_body_css = '''        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}
        @media (max-width: 640px) {{
            div[style*="grid-template-columns: 1fr 1fr"] {{ grid-template-columns: 1fr !important; }}
        }}'''

if old_body_css in content and "@media (max-width: 640px)" not in content:
    content = content.replace(old_body_css, new_body_css, 1)
    patched.append("Адаптивность: grid → 1 колонка на мобильных")

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
