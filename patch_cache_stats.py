#!/usr/bin/env python3
"""Добавляет статистику AI-кэша в админ-панель."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_cache_stats"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Подсчёт статистики кэша — добавляем после total_visits
# ============================================================
anchor1 = "    total_visits = db.query(VisitLog).count()"
new1 = '''    total_visits = db.query(VisitLog).count()
    # --- Статистика AI-кэша ---
    try:
        cache_total = db.query(AILicenseCache).count()
        cache_success = db.query(AILicenseCache).filter(AILicenseCache.is_failure == False).count()
        cache_failures = db.query(AILicenseCache).filter(AILicenseCache.is_failure == True).count()
        cache_hits_raw = db.query(AILicenseCache).all()
        total_hits = sum((c.hit_count or 0) for c in cache_hits_raw)
        # Экономия: 15 секунд на запрос к ИИ
        savings_sec = total_hits * 15
        savings_min = savings_sec / 60
        # Экономия запросов к API (примерная стоимость ~0.01 USD за 1000 токенов, среднее ~500 токенов)
        savings_requests = total_hits
    except Exception as e:
        print(f"[CACHE STATS] Ошибка: {e}")
        cache_total = 0
        cache_success = 0
        cache_failures = 0
        total_hits = 0
        savings_sec = 0
        savings_min = 0
        savings_requests = 0'''

if "cache_total = db.query(AILicenseCache).count()" not in content and anchor1 in content:
    content = content.replace(anchor1, new1, 1)
    patched.append("Подсчёт статистики кэша")

# ============================================================
# 2. Добавить карточку в блок .stats
# ============================================================
anchor2 = '''        <div class="stat" style="border-left-color:#3182ce;"><h4>Просмотров</h4><p>{total_visits}</p></div>
    </div>'''

new2 = '''        <div class="stat" style="border-left-color:#3182ce;"><h4>Просмотров</h4><p>{total_visits}</p></div>
        <div class="stat" style="border-left-color:#38a169;"><h4>🧠 Кэш ИИ</h4><p>{cache_total} <small style="color:#4a5568;font-size:14px;">записей</small></p></div>
        <div class="stat" style="border-left-color:#805ad5;"><h4>⚡ Хитов кэша</h4><p>{total_hits} <small style="color:#4a5568;font-size:14px;">(≈{savings_min:.1f} мин)</small></p></div>
    </div>'''

if "🧠 Кэш ИИ" not in content and anchor2 in content:
    content = content.replace(anchor2, new2, 1)
    patched.append("Карточки кэша в статистике")
else:
    print("⚠️ Якорь карточек статистики не найден")

# ============================================================
# 3. Добавить подробный блок кэша после блока пользователей
# ============================================================
anchor3 = '''    <div class="card" style="overflow-x:auto;">
    <h3 style="margin-top:0;">Все проверки ({len(all_reports)})</h3>'''

new3 = '''    <div class="card" style="border-top-color:#38a169;">
    <h3 style="margin-top:0;">🧠 Кэш ИИ-ответов</h3>
    <p style="font-size:13px;color:#4a5568;">Кэш хранит ответы GigaChat на 90 дней (или 7 дней для неудачных запросов). При повторной проверке того же компонента ИИ не вызывается — экономится время и деньги.</p>
    <div style="display:flex;gap:20px;flex-wrap:wrap;margin:20px 0;">
        <div style="flex:1;min-width:180px;background:#f0fff4;padding:18px 22px;border-radius:6px;border-left:4px solid #38a169;">
            <div style="color:#4a5568;font-size:12px;">Всего записей</div>
            <div style="font-size:26px;font-weight:bold;color:#2f855a;">{cache_total}</div>
        </div>
        <div style="flex:1;min-width:180px;background:#ebf8ff;padding:18px 22px;border-radius:6px;border-left:4px solid #3182ce;">
            <div style="color:#4a5568;font-size:12px;">Успешных ответов</div>
            <div style="font-size:26px;font-weight:bold;color:#2b6cb0;">{cache_success}</div>
        </div>
        <div style="flex:1;min-width:180px;background:#fffaf0;padding:18px 22px;border-radius:6px;border-left:4px solid #dd6b20;">
            <div style="color:#4a5568;font-size:12px;">Неудачных</div>
            <div style="font-size:26px;font-weight:bold;color:#c05621;">{cache_failures}</div>
        </div>
        <div style="flex:1;min-width:180px;background:#faf5ff;padding:18px 22px;border-radius:6px;border-left:4px solid #805ad5;">
            <div style="color:#4a5568;font-size:12px;">Хитов кэша</div>
            <div style="font-size:26px;font-weight:bold;color:#6b46c1;">{total_hits}</div>
        </div>
    </div>
    <div style="background:#edf2f7;padding:14px 18px;border-radius:6px;font-size:14px;color:#2d3748;">
        💰 <b>Экономия:</b> примерно <b>{savings_requests}</b> запросов к GigaChat и <b>{savings_min:.1f} минут</b> ожидания пользователями (при среднем времени ответа ИИ ≈ 15 сек).
    </div>
    <div style="margin-top:15px;">
        <form method="POST" action="/admin/clear-ai-cache" style="display:inline;">
            <button type="submit" onclick="return confirm('Очистить весь кэш ИИ? Это удалит все сохранённые ответы.');" style="background:#e53e3e;color:white;border:none;border-radius:4px;padding:8px 16px;font-size:13px;cursor:pointer;font-weight:600;">🗑️ Очистить кэш</button>
        </form>
    </div>
    </div>

    <div class="card" style="overflow-x:auto;">
    <h3 style="margin-top:0;">Все проверки ({len(all_reports)})</h3>'''

if "🧠 Кэш ИИ-ответов" not in content and anchor3 in content:
    content = content.replace(anchor3, new3, 1)
    patched.append("Блок статистики кэша")
else:
    print("⚠️ Якорь блока проверок не найден")

# ============================================================
# 4. Эндпоинт для очистки кэша
# ============================================================
anchor4 = '''@app.post("/admin/feedback/mark-read/{feedback_id}")'''

new4 = '''@app.post("/admin/clear-ai-cache")
async def admin_clear_ai_cache(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    deleted = db.query(AILicenseCache).delete()
    db.commit()
    print(f"[ADMIN] Очищено записей кэша: {deleted}")
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/feedback/mark-read/{feedback_id}")'''

if "async def admin_clear_ai_cache" not in content and anchor4 in content:
    content = content.replace(anchor4, new4, 1)
    patched.append("Эндпоинт очистки кэша")
else:
    print("⚠️ Якорь эндпоинта feedback не найден")

# ============================================================
# Записать результат
# ============================================================
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
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
