#!/usr/bin/env python3
"""Добавляет страницу /about + показывает версию из git-тега."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_version"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Импорт version
# ============================================================
anchor1 = 'load_dotenv()\n'
new1 = '''load_dotenv()

from version import __version__ as APP_VERSION, get_version_info
'''
if "from version import" not in content and anchor1 in content:
    content = content.replace(anchor1, new1, 1)
    patched.append("Импорт version")

# ============================================================
# 2. Заменить статичную версию в FastAPI
# ============================================================
old2 = 'app = FastAPI(title="Платформа «Компонент-Эксперт» - ПП РФ № 1236", version="9.0.0")'
new2 = 'app = FastAPI(title="Платформа «Компонент-Эксперт» - ПП РФ № 1236", version=APP_VERSION)'
if old2 in content:
    content = content.replace(old2, new2, 1)
    patched.append("Динамическая версия в FastAPI")

# ============================================================
# 3. Обновить /health — отдавать актуальную версию
# ============================================================
old3 = 'return {"status": "ok", "service": "component-expert", "version": "8.9.0"}'
new3 = 'return {"status": "ok", "service": "component-expert", "version": APP_VERSION}'
if old3 in content:
    content = content.replace(old3, new3, 1)
    patched.append("Версия в /health")
elif 'version": "8.9.0"' in content:
    content = content.replace('version": "8.9.0"', 'version": APP_VERSION', 1)
    patched.append("Версия в /health (alt)")

# ============================================================
# 4. Добавить страницу /about перед /download_excel
# ============================================================
anchor4 = '@app.get("/download_excel/{filename}")'
about_page = '''@app.get("/about", response_class=HTMLResponse)
async def about_page(user: User = Depends(get_current_user)):
    info = get_version_info()
    changelog_html = ""
    for entry in info["changelog"]:
        changes_li = "".join([f"<li>{c}</li>" for c in entry["changes"]])
        changelog_html += f"""
        <div style="border-left:4px solid #3182ce;padding:15px 20px;margin-bottom:20px;background:#f8fafc;border-radius:6px;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:10px;">
                <h3 style="margin:0;color:#1a365d;font-size:22px;">v{entry['version']}</h3>
                <span style="color:#718096;font-size:13px;">{entry['date']}</span>
            </div>
            <ul style="margin:0;padding-left:20px;font-size:14px;color:#2d3748;line-height:1.8;">
                {changes_li}
            </ul>
        </div>"""

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>О сервисе</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}
        .nav {{ display: flex; justify-content: space-between; padding: 15px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 30px; font-size: 14px; flex-wrap: wrap; gap: 10px; }}
        .nav-brand {{ font-weight: 800; color: #1a365d; font-size: 16px; }}
        .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 4px solid #1a365d; margin-bottom: 20px; }}
        h1 {{ color: #1a365d; margin-top: 0; }}
        .version-badge {{ display: inline-block; background: #3182ce; color: white; padding: 6px 16px; border-radius: 20px; font-size: 14px; font-weight: 600; margin-left: 10px; }}
        .tech {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 15px 0; }}
        .tech span {{ background: #edf2f7; padding: 4px 12px; border-radius: 12px; font-size: 13px; color: #2d3748; }}
        a {{ color: #3182ce; }}
    </style></head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт</div><div>{_build_nav(user)}</div></div>

    <div class="card">
        <h1>О сервисе <span class="version-badge">v{info['version']}</span></h1>
        <p><b>Платформа «Компонент-Эксперт»</b> — веб-сервис автоматизированного аудита программного обеспечения на соответствие Постановлению Правительства РФ № 1236.</p>

        <h3 style="color:#1a365d;margin-top:30px;">Дата сборки</h3>
        <p style="font-size:14px;color:#4a5568;">{info['build_date']}</p>

        <h3 style="color:#1a365d;margin-top:30px;">Технологии</h3>
        <div class="tech">
            <span>Python 3.12</span>
            <span>FastAPI</span>
            <span>SQLAlchemy 2.0</span>
            <span>SQLite</span>
            <span>GigaChat (OAuth 2.0)</span>
            <span>OSV API</span>
            <span>Docker</span>
            <span>Nginx</span>
        </div>

        <h3 style="color:#1a365d;margin-top:30px;">Ссылки</h3>
        <ul style="font-size:14px;line-height:1.8;">
            <li><a href="https://github.com/zanik88/scan_site" target="_blank">GitHub-репозиторий</a></li>
            <li><a href="https://reestr.digital.gov.ru/" target="_blank">Единый реестр российского ПО</a></li>
            <li><a href="/terms">Пользовательское соглашение</a></li>
            <li><a href="/feedback">Обратная связь</a></li>
        </ul>
    </div>

    <div class="card">
        <h1 style="font-size:26px;">История версий</h1>
        {changelog_html}
    </div>

    {FOOTER_HTML}
    </body></html>
    """)


@app.get("/download_excel/{filename}")'''

if "async def about_page" not in content and anchor4 in content:
    content = content.replace(anchor4, about_page, 1)
    patched.append("Страница /about")

# ============================================================
# 5. Добавить ссылку «О сервисе» в навбар
# ============================================================
old5 = '''    feedback_link = "<a href='/feedback' style='color:#3182ce;text-decoration:none;font-weight:600;'>📮 Обратная связь</a>"'''
new5 = '''    feedback_link = "<a href='/feedback' style='color:#3182ce;text-decoration:none;font-weight:600;'>📮 Обратная связь</a>"
    about_link = "<a href='/about' style='color:#3182ce;text-decoration:none;font-weight:600;'>ℹ️ О сервисе</a>"'''
if "about_link = " not in content and old5 in content:
    content = content.replace(old5, new5, 1)
    patched.append("Переменная about_link")

# Добавить about_link в nav (для залогиненных и гостей)
old6 = '''f" | {feedback_link}"
                f" | <a href='/logout' style='color:#718096;text-decoration:none;'>Выйти</a>")'''
new6 = '''f" | {feedback_link}"
                f" | {about_link}"
                f" | <a href='/logout' style='color:#718096;text-decoration:none;'>Выйти</a>")'''
if old6 in content and "| {about_link}" not in content.split("def _build_nav")[1][:1500]:
    content = content.replace(old6, new6, 1)
    patched.append("О сервисе в nav (залогинен)")

old7 = '''            " | <a href='/pricing' style='color:#3182ce;text-decoration:none;font-weight:600;'>Тарифы</a>"
            f" | {feedback_link}")'''
new7 = '''            " | <a href='/pricing' style='color:#3182ce;text-decoration:none;font-weight:600;'>Тарифы</a>"
            f" | {feedback_link}"
            f" | {about_link}")'''
if old7 in content:
    content = content.replace(old7, new7, 1)
    patched.append("О сервисе в nav (гость)")

# Записать
with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

# Проверка синтаксиса
print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("❌ Ошибка! Восстанавливаем из backup...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
