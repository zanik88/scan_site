#!/usr/bin/env python3
"""
Патч аналитики:
1. Флаг is_test у User (авто-помечание по email)
2. Фильтр "все/реальные/тестовые" в админ-панели
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_analytics"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Поле is_test в модель User
# ============================================================
old = """    pro_checks_used = Column(Integer, default=0, nullable=True)
    pro_period_start = Column(DateTime, default=datetime.utcnow, nullable=True)"""
new = """    pro_checks_used = Column(Integer, default=0, nullable=True)
    pro_period_start = Column(DateTime, default=datetime.utcnow, nullable=True)
    is_test = Column(Boolean, default=False, nullable=True)"""

if old in content and "    is_test = Column" not in content:
    content = content.replace(old, new, 1)
    patched.append("Поле is_test в User")

# ============================================================
# 2. Миграция is_test
# ============================================================
old = """                ("pro_period_start", "ALTER TABLE users ADD COLUMN pro_period_start DATETIME;"),
            ]:"""
new = """                ("pro_period_start", "ALTER TABLE users ADD COLUMN pro_period_start DATETIME;"),
                ("is_test", "ALTER TABLE users ADD COLUMN is_test BOOLEAN DEFAULT 0;"),
            ]:"""

if old in content:
    content = content.replace(old, new, 1)
    patched.append("Миграция is_test")

# ============================================================
# 3. Функция _is_test_email перед hash_password
# ============================================================
anchor = "def hash_password(password: str) -> str:"
func = '''def _is_test_email(email: str) -> bool:
    """Определяет тестовые email по паттернам."""
    if not email:
        return False
    e = email.lower().strip()
    test_patterns = ["@t.ru", "@test.ru", "@example.ru", "@example.com",
                     "@test.com", "@localhost"]
    if any(e.endswith(p) for p in test_patterns):
        return True
    local = e.split("@")[0]
    if local.startswith(("u", "q", "z", "reg", "test")) and local[-1:].isdigit():
        return True
    return False


''' + anchor

if "_is_test_email" not in content and anchor in content:
    content = content.replace(anchor, func, 1)
    patched.append("Функция _is_test_email")

# ============================================================
# 4. Установить is_test при регистрации
# ============================================================
old = """    assigned_role = "admin" if db.query(User).count() == 0 else "user"
    db.add(User(company_name=company_name, email=email, hashed_password=hash_password(password),
                role=assigned_role, subscription_plan="Pro" if assigned_role == "admin" else "Free",
                free_checks_used=0))"""
new = """    assigned_role = "admin" if db.query(User).count() == 0 else "user"
    is_test_user = _is_test_email(email)
    db.add(User(company_name=company_name, email=email, hashed_password=hash_password(password),
                role=assigned_role, subscription_plan="Pro" if assigned_role == "admin" else "Free",
                free_checks_used=0, is_test=is_test_user))"""

if old in content:
    content = content.replace(old, new, 1)
    patched.append("is_test при регистрации")

# ============================================================
# 5. Авто-пометка существующих после sync_rules()
# ============================================================
anchor = "sync_rules()\n"
new = """sync_rules()


def _mark_test_users():
    db = SessionLocal()
    try:
        all_users = db.query(User).all()
        changed = 0
        for u in all_users:
            if u.is_test is None:
                u.is_test = _is_test_email(u.email)
                changed += 1
        if changed:
            db.commit()
            print(f"[MIGRATION] Помечено тестовых: {changed}")
    except Exception as e:
        print(f"[MIGRATION] is_test error: {e}")
        db.rollback()
    finally:
        db.close()


_mark_test_users()
"""
if "def _mark_test_users" not in content and anchor in content:
    content = content.replace(anchor, new, 1)
    patched.append("Авто-пометка существующих")

# ============================================================
# 6. Фильтр в admin_panel — принять параметр filter_mode
# ============================================================
old = """async def admin_panel(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return HTMLResponse("<h1 style='color:red;text-align:center;font-family:sans-serif;margin-top:100px;'>403 Доступ запрещён</h1>", status_code=403)

    all_users = db.query(User).all()"""

new = """async def admin_panel(request: Request, filter_mode: str = "all", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return HTMLResponse("<h1 style='color:red;text-align:center;font-family:sans-serif;margin-top:100px;'>403 Доступ запрещён</h1>", status_code=403)

    query = db.query(User)
    if filter_mode == "real":
        query = query.filter((User.is_test == False) | (User.is_test == None))
    elif filter_mode == "test":
        query = query.filter(User.is_test == True)
    all_users = query.all()"""

if old in content:
    content = content.replace(old, new, 1)
    patched.append("Фильтр filter_mode в admin_panel")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: admin_panel не найден — пропускаем фильтр")
    patched.append("Фильтр не применён (админка уже изменена)")

# ============================================================
# 7. Кнопки фильтра в HTML админки
# ============================================================
old = """    <div class="card" style="overflow-x:auto;">
    <h3 style="margin-top:0;">Управление пользователями</h3>
    <p style="font-size:12px;color:#718096;">♻️ — сбросить счётчик бесплатных проверок</p>
    <table><tr><th>ID</th><th>Компания</th><th>Email</th><th>Роль</th><th>Тариф / Проверки</th><th>Статус</th><th>Действия</th></tr>{users_html}</table>
    </div>"""

new = """    <div class="card" style="overflow-x:auto;">
    <h3 style="margin-top:0;">Управление пользователями</h3>
    <p style="font-size:12px;color:#718096;">♻️ — сбросить счётчик бесплатных проверок</p>
    <div style="display:flex; gap:10px; margin:15px 0; flex-wrap:wrap;">
        <a href="/admin?filter_mode=all" style="padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600; font-size:13px; {'background:#3182ce; color:white;' if filter_mode == 'all' else 'background:#edf2f7; color:#2d3748;'}">👥 Все ({len(all_users)})</a>
        <a href="/admin?filter_mode=real" style="padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600; font-size:13px; {'background:#38a169; color:white;' if filter_mode == 'real' else 'background:#edf2f7; color:#2d3748;'}">✅ Реальные</a>
        <a href="/admin?filter_mode=test" style="padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600; font-size:13px; {'background:#dd6b20; color:white;' if filter_mode == 'test' else 'background:#edf2f7; color:#2d3748;'}">🧪 Тестовые</a>
    </div>
    <table><tr><th>ID</th><th>Компания</th><th>Email</th><th>Роль</th><th>Тариф / Проверки</th><th>Статус</th><th>Действия</th></tr>{users_html}</table>
    </div>"""

if old in content:
    content = content.replace(old, new, 1)
    patched.append("Кнопки фильтра в UI админки")
else:
    print("ПРЕДУПРЕЖДЕНИЕ: блок управления пользователями не найден")

# ============================================================
# 8. Метка 'тестовый' в строке пользователя
# ============================================================
old = """        users_html += f"<tr><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.id}</td>"""
new = """        test_badge = " <span style='background:#fefcbf; color:#744210; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600;'>ТЕСТ</span>" if u.is_test else ""
        users_html += f"<tr><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.id}</td>"""

if old in content:
    content = content.replace(old, new, 1)
    # Добавить badge в email-ячейку
    old2 = """<td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.email}</td>"""
    new2 = """<td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.email}{test_badge}</td>"""
    if old2 in content:
        content = content.replace(old2, new2, 1)
        patched.append("Метка 'ТЕСТ' у тестовых пользователей")

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
