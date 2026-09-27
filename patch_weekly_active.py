#!/usr/bin/env python3
"""Добавляет карточку 'Активные за 7 дней' в админ-панель."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_weekly"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Подсчёт статистики — рядом с online_count
# ============================================================
old1 = "    online_count = sum(1 for u in all_users if u.last_active and (now - u.last_active) < timedelta(minutes=15))"
new1 = """    online_count = sum(1 for u in all_users if u.last_active and (now - u.last_active) < timedelta(minutes=15))
    week_ago = now - timedelta(days=7)
    monthly_ago = now - timedelta(days=30)
    active_7d = sum(1 for u in all_users if u.last_active and u.last_active > week_ago)
    active_30d = sum(1 for u in all_users if u.last_active and u.last_active > monthly_ago)
    # Активные из них — не админы
    real_7d = sum(1 for u in all_users if u.role != "admin" and u.last_active and u.last_active > week_ago)
    # Регистрации за 7 дней
    new_7d = sum(1 for u in all_users if u.created_at and u.created_at > week_ago)"""

if old1 in content:
    content = content.replace(old1, new1, 1)
    patched.append("Подсчёт active_7d / active_30d / new_7d")
else:
    print("ОШИБКА: онлайн-счётчик не найден")
    sys.exit(1)

# ============================================================
# 2. Добавить карточку в блок stats
# ============================================================
old2 = """        <div class="stat" style="border-left-color:#38a169;"><h4>🧠 Кэш ИИ</h4><p>{cache_total} <small style="color:#4a5568;font-size:14px;">записей</small></p></div>"""

new2 = """        <div class="stat" style="border-left-color:#3182ce;"><h4>📊 Активные за 7 дней</h4><p>{active_7d} <small style="color:#718096;font-size:13px;">({real_7d} без админов)</small></p></div>
        <div class="stat" style="border-left-color:#805ad5;"><h4>📈 Активные за 30 дней</h4><p>{active_30d}</p></div>
        <div class="stat" style="border-left-color:#38a169;"><h4>🧠 Кэш ИИ</h4><p>{cache_total} <small style="color:#4a5568;font-size:14px;">записей</small></p></div>"""

if old2 in content:
    content = content.replace(old2, new2, 1)
    patched.append("Карточки 'Активные за 7/30 дней'")
else:
    print("ОШИБКА: карточка кэша не найдена")
    sys.exit(1)

# ============================================================
# 3. Блок "Сводка за неделю" после stats
# ============================================================
old3 = """    <div class="card" style="overflow-x:auto; border-top-color:#805ad5;">
    <h3 style="margin-top:0;">📮 Обратная связь{feedback_badge}</h3>"""

new3 = """    <div class="card" style="border-top-color:#38a169; background:linear-gradient(135deg,#f0fff4 0%,#ffffff 100%);">
        <h3 style="margin-top:0; color:#1a365d;">📅 Сводка за последние 7 дней</h3>
        <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px;">
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #3182ce;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Новые регистрации</div>
                <div style="font-size:24px; font-weight:700; color:#2b6cb0; margin-top:4px;">{new_7d}</div>
            </div>
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #38a169;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Заходили в сервис</div>
                <div style="font-size:24px; font-weight:700; color:#2f855a; margin-top:4px;">{active_7d}</div>
            </div>
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #dd6b20;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Онлайн сейчас</div>
                <div style="font-size:24px; font-weight:700; color:#c05621; margin-top:4px;">{online_count}</div>
            </div>
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #805ad5;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Всего пользователей</div>
                <div style="font-size:24px; font-weight:700; color:#6b46c1; margin-top:4px;">{len(all_users)}</div>
            </div>
        </div>
    </div>

    <div class="card" style="overflow-x:auto; border-top-color:#805ad5;">
    <h3 style="margin-top:0;">📮 Обратная связь{feedback_badge}</h3>"""

if old3 in content:
    content = content.replace(old3, new3, 1)
    patched.append("Блок 'Сводка за 7 дней'")
else:
    print("ОШИБКА: блок обратной связи не найден")
    sys.exit(1)

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
