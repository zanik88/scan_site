#!/usr/bin/env python3
"""
Патч тарифов:
1. Pro: 50 проверок в месяц (не безлимит)
2. Admin: остаётся безлимитным
3. Автоматический сброс счётчика Pro раз в 30 дней
4. Обновлён UI тарифов и личного кабинета
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_tariffs"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Добавить константу PRO_CHECKS_LIMIT
# ============================================================
old1 = "FREE_CHECKS_LIMIT = 5"
new1 = "FREE_CHECKS_LIMIT = 5\nPRO_CHECKS_LIMIT = 50  # проверок в месяц для Pro"

if old1 in content and "PRO_CHECKS_LIMIT" not in content:
    content = content.replace(old1, new1, 1)
    patched.append("Константа PRO_CHECKS_LIMIT = 50")

# ============================================================
# 2. Добавить поля pro_checks_used и pro_period_start в модель User
# ============================================================
old2 = '''    free_checks_used = Column(Integer, default=0, nullable=True)
    last_active = Column(DateTime, default=datetime.utcnow)'''
new2 = '''    free_checks_used = Column(Integer, default=0, nullable=True)
    pro_checks_used = Column(Integer, default=0, nullable=True)
    pro_period_start = Column(DateTime, default=datetime.utcnow, nullable=True)
    last_active = Column(DateTime, default=datetime.utcnow)'''

if old2 in content and "pro_checks_used" not in content:
    content = content.replace(old2, new2, 1)
    patched.append("Поля pro_checks_used + pro_period_start в User")

# ============================================================
# 3. Добавить миграцию новых полей
# ============================================================
old3 = '''                ("free_checks_used", "ALTER TABLE users ADD COLUMN free_checks_used INTEGER DEFAULT 0;"),
            ]:'''
new3 = '''                ("free_checks_used", "ALTER TABLE users ADD COLUMN free_checks_used INTEGER DEFAULT 0;"),
                ("pro_checks_used", "ALTER TABLE users ADD COLUMN pro_checks_used INTEGER DEFAULT 0;"),
                ("pro_period_start", "ALTER TABLE users ADD COLUMN pro_period_start DATETIME;"),
            ]:'''

if old3 in content and "pro_checks_used" not in content.split("run_migrations")[1][:2000]:
    content = content.replace(old3, new3, 1)
    patched.append("Миграция: pro_checks_used + pro_period_start")

# ============================================================
# 4. Обновить is_unlimited — теперь только для admin
# ============================================================
old4 = '''def is_unlimited(user: Optional[User]) -> bool:
    if not user:
        return False
    return user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]'''

new4 = '''def is_unlimited(user: Optional[User]) -> bool:
    """Безлимит только для администратора. Pro — 50 проверок/месяц."""
    if not user:
        return False
    return user.role == "admin"'''

if old4 in content:
    content = content.replace(old4, new4, 1)
    patched.append("is_unlimited: только для admin")
else:
    print("⚠️ is_unlimited не найден")

# ============================================================
# 5. Обновить get_free_checks_left — учитывать Pro-лимит и период
# ============================================================
old5 = '''def get_free_checks_left(user: Optional[User], request: Request) -> int:
    if user and user.role == "admin":
        return 999
    if user and user.subscription_plan in ["Pro", "Unlimited"]:
        return 999
    if user:
        used = user.free_checks_used or 0
        return max(0, FREE_CHECKS_LIMIT - used)
    if request:
        guest_count = int(request.cookies.get("guest_audit_count", 0))
        return max(0, FREE_CHECKS_LIMIT - guest_count)
    return FREE_CHECKS_LIMIT'''

new5 = '''def get_free_checks_left(user: Optional[User], request: Request, db: Optional[Session] = None) -> int:
    """Возвращает остаток проверок. Для Pro учитывает 30-дневный период."""
    if user and user.role == "admin":
        return 999

    if user and user.subscription_plan in ["Pro", "Unlimited"]:
        # Сброс счётчика Pro раз в 30 дней
        now = datetime.utcnow()
        period_start = user.pro_period_start or user.created_at or now
        days_passed = (now - period_start).days
        if days_passed >= 30:
            user.pro_checks_used = 0
            user.pro_period_start = now
            if db:
                try:
                    db.commit()
                except Exception:
                    db.rollback()
        used = user.pro_checks_used or 0
        return max(0, PRO_CHECKS_LIMIT - used)

    if user:
        used = user.free_checks_used or 0
        return max(0, FREE_CHECKS_LIMIT - used)
    if request:
        guest_count = int(request.cookies.get("guest_audit_count", 0))
        return max(0, FREE_CHECKS_LIMIT - guest_count)
    return FREE_CHECKS_LIMIT'''

if old5 in content:
    content = content.replace(old5, new5, 1)
    patched.append("get_free_checks_left: Pro-лимит 50 + месячный сброс")
else:
    print("⚠️ get_free_checks_left не найден")

# ============================================================
# 6. В /upload — увеличивать pro_checks_used для Pro
# ============================================================
old6 = '''    if not unlimited and user:
        user.free_checks_used = (user.free_checks_used or 0) + 1
        db.commit()'''

new6 = '''    if not unlimited and user:
        if user.subscription_plan in ["Pro", "Unlimited"]:
            user.pro_checks_used = (user.pro_checks_used or 0) + 1
        else:
            user.free_checks_used = (user.free_checks_used or 0) + 1
        db.commit()'''

if old6 in content:
    content = content.replace(old6, new6, 1)
    patched.append("/upload: увеличивает pro_checks_used для Pro")
else:
    print("⚠️ Блок увеличения счётчика в /upload не найден")

# ============================================================
# 7. Обновить вызовы get_free_checks_left — добавить db где нужно
# ============================================================
content = content.replace(
    "free_left = get_free_checks_left(user, request)",
    "free_left = get_free_checks_left(user, request, db)",
)
patched.append("Передаём db в get_free_checks_left")

# ============================================================
# 8. Обновить UI тарифов (pricing_page)
# ============================================================
old8 = '''            <ul class="pf"><li>✔️ Безлимит проверок</li><li>✔️ Docker-сканер</li><li>✔️ Excel-отчёты</li><li>✔️ Приоритетная поддержка</li></ul></div>'''
new8 = '''            <ul class="pf"><li>✔️ {PRO_CHECKS_LIMIT} проверок в месяц</li><li>✔️ Excel-отчёты</li><li>✔️ Проверка CVE</li><li>✔️ Приоритетная поддержка</li></ul></div>'''

if old8 in content:
    content = content.replace(old8, new8, 1)
    patched.append("UI тарифов: Pro = 50 проверок/мес")
else:
    print("⚠️ Блок Pro в pricing не найден")

# ============================================================
# 9. Обновить plan_badge в dashboard
# ============================================================
old9 = '''    elif user.subscription_plan in ["Pro", "Unlimited"]:
        plan_badge = "💎 Профессиональный (безлимит)"'''
new9 = '''    elif user.subscription_plan in ["Pro", "Unlimited"]:
        used_pro = user.pro_checks_used or 0
        left_pro = max(0, PRO_CHECKS_LIMIT - used_pro)
        plan_badge = f"💎 Pro (использовано {used_pro} из {PRO_CHECKS_LIMIT}, осталось {left_pro})"'''

if old9 in content:
    content = content.replace(old9, new9, 1)
    patched.append("Личный кабинет: показывает остаток Pro")

# ============================================================
# 10. Баннер "Бесплатные проверки" — обновить для Pro
# ============================================================
old10 = '''def _free_plan_banner(user: Optional[User], request: Optional[Request]) -> str:
    if user and (user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]):
        return ""

    left = get_free_checks_left(user, request)'''

new10 = '''def _free_plan_banner(user: Optional[User], request: Optional[Request]) -> str:
    if user and user.role == "admin":
        return ""

    if user and user.subscription_plan in ["Pro", "Unlimited"]:
        left = get_free_checks_left(user, request)
        if left <= 5:
            color = "#dd6b20" if left <= 2 else "#3182ce"
            bg = "#fffaf0" if left <= 2 else "#ebf8ff"
            return f"""
            <div style="background: {bg}; border-left: 5px solid {color}; padding: 15px 20px; border-radius: 8px; margin-bottom: 25px;">
                <b style="color: {color}; font-size: 14px;">💎 Pro: осталось {left} из {PRO_CHECKS_LIMIT} проверок в этом месяце</b>
                <div style="color: #4a5568; font-size: 12px; margin-top: 4px;">Лимит автоматически обновится через 30 дней.</div>
            </div>
            """
        return ""

    left = get_free_checks_left(user, request)'''

if old10 in content:
    content = content.replace(old10, new10, 1)
    patched.append("Баннер: показывает остаток Pro (когда <= 5)")

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
