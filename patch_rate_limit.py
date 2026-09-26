#!/usr/bin/env python3
"""
Патч: Rate Limiting для защиты от спама.
- Гость/Free: 5 /upload в минуту
- Pro/Admin: 30 /upload в минуту
- Общий лимит: 120 запросов в минуту на любой эндпоинт
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak_rate"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch_imports(content: str) -> tuple:
    """Добавляет import time и defaultdict."""
    anchor = "import secrets\nimport sqlite3\n"
    new_imports = "import secrets\nimport sqlite3\nimport time\nfrom collections import defaultdict\n"
    if anchor in content:
        content = content.replace(anchor, new_imports, 1)
        print("✅ Патч 1: импорты time и defaultdict добавлены")
        return content, True
    print("⚠️ Патч 1: якорь импортов не найден")
    return content, False


def patch_rate_limiter(content: str) -> tuple:
    """Добавляет класс RateLimiter и функцию проверки."""
    # Вставим после PROGRESS_TRACKER = {}
    anchor = "PROGRESS_TRACKER = {}\n"
    rate_limiter_code = '''PROGRESS_TRACKER = {}

# ==========================================
# RATE LIMITING
# ==========================================
RATE_LIMIT_WINDOW = 60          # окно в секундах
RATE_LIMIT_GUEST = 5            # для гостей и Free
RATE_LIMIT_PRO = 30             # для Pro и Admin
RATE_LIMIT_GENERAL = 120        # общий лимит для всех эндпоинтов

# Хранилище: {(ip, endpoint): [timestamp1, timestamp2, ...]}
_RATE_BUCKETS = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    """Извлекает IP клиента с учётом Nginx reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, endpoint: str, user: Optional[User] = None) -> tuple:
    """
    Проверяет лимит запросов.
    Возвращает (allowed: bool, remaining: int, retry_after: int).
    """
    ip = _get_client_ip(request)
    key = (ip, endpoint)
    now = time.time()

    # Убираем старые timestamps
    bucket = _RATE_BUCKETS[key]
    _RATE_BUCKETS[key] = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    bucket = _RATE_BUCKETS[key]

    # Определяем лимит по роли
    if user and (user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]):
        limit = RATE_LIMIT_PRO
    elif endpoint == "/upload":
        limit = RATE_LIMIT_GUEST
    else:
        limit = RATE_LIMIT_GENERAL

    if len(bucket) >= limit:
        retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
        return False, 0, retry_after

    bucket.append(now)
    return True, limit - len(bucket), 0

'''
    if anchor in content:
        content = content.replace(anchor, rate_limiter_code, 1)
        print("✅ Патч 2: RateLimiter добавлен")
        return content, True
    print("⚠️ Патч 2: якорь PROGRESS_TRACKER не найден")
    return content, False


def patch_upload_endpoint(content: str) -> tuple:
    """Добавляет проверку в /upload."""
    # Найдём начало upload_file после get_free_checks_left
    anchor = '''    free_left = get_free_checks_left(user, request)
    unlimited = is_unlimited(user)

    if not unlimited and free_left <= 0:
        return RedirectResponse(url="/pricing", status_code=status.HTTP_303_SEE_OTHER)'''

    new_code = '''    # --- RATE LIMITING ---
    allowed, remaining, retry_after = check_rate_limit(request, "/upload", user)
    if not allowed:
        return HTMLResponse(
            f"""<html><head><meta charset="UTF-8"><title>429 — Слишком много запросов</title>
            <style>body{{font-family:sans-serif;text-align:center;padding:60px;background:#f7fafc;}}
            .card{{background:white;max-width:520px;margin:0 auto;padding:40px;border-radius:8px;
            border-top:5px solid #e53e3e;box-shadow:0 4px 12px rgba(0,0,0,0.05);}}
            h1{{color:#e53e3e;}} p{{color:#4a5568;line-height:1.6;}}</style></head><body>
            <div class="card">
              <h1>⏱ Слишком много запросов</h1>
              <p>Вы превысили лимит: <b>{RATE_LIMIT_GUEST} проверок в минуту</b> для бесплатного плана.</p>
              <p>Подождите <b>{retry_after} секунд</b> и попробуйте снова.</p>
              <p style="font-size:13px;">Для увеличения лимита перейдите на тариф Pro
              (30 проверок в минуту).</p>
              <p><a href="/pricing" style="color:#3182ce;font-weight:600;">Посмотреть тарифы →</a></p>
              <p><a href="/" style="color:#718096;">← Вернуться на главную</a></p>
            </div>
            </body></html>""",
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )
    # --- /RATE LIMITING ---

    free_left = get_free_checks_left(user, request)
    unlimited = is_unlimited(user)

    if not unlimited and free_left <= 0:
        return RedirectResponse(url="/pricing", status_code=status.HTTP_303_SEE_OTHER)'''

    if anchor in content:
        content = content.replace(anchor, new_code, 1)
        print("✅ Патч 3: Rate limiting в /upload добавлен")
        return content, True
    print("⚠️ Патч 3: якорь /upload не найден")
    return content, False


def patch_register_endpoint(content: str) -> tuple:
    """Добавляет проверку в /register (POST)."""
    anchor = '''async def register(company_name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   terms_accepted: str = Form(None), db: Session = Depends(get_db)):
    if not terms_accepted:'''

    new_code = '''async def register(request: Request, company_name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   terms_accepted: str = Form(None), db: Session = Depends(get_db)):
    # --- RATE LIMITING ---
    allowed, _, retry_after = check_rate_limit(request, "/register")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много попыток регистрации. Подождите {retry_after} секунд.",
            headers={"Retry-After": str(retry_after)}
        )
    # --- /RATE LIMITING ---
    if not terms_accepted:'''

    if anchor in content:
        content = content.replace(anchor, new_code, 1)
        print("✅ Патч 4: Rate limiting в /register добавлен")
        return content, True
    print("⚠️ Патч 4: якорь /register не найден")
    return content, False


def patch_feedback_endpoint(content: str) -> tuple:
    """Добавляет проверку в /feedback (POST)."""
    anchor = '''async def feedback_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form("Другое"),
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:'''

    new_code = '''async def feedback_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form("Другое"),
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # --- RATE LIMITING ---
    allowed, _, retry_after = check_rate_limit(request, "/feedback")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много обращений. Подождите {retry_after} секунд.",
            headers={"Retry-After": str(retry_after)}
        )
    # --- /RATE LIMITING ---
    try:'''

    if anchor in content:
        content = content.replace(anchor, new_code, 1)
        print("✅ Патч 5: Rate limiting в /feedback добавлен")
        return content, True
    print("⚠️ Патч 5: якорь /feedback не найден")
    return content, False


def patch_nginx_hint(content: str) -> tuple:
    """Добавляет комментарий про Nginx в конце файла."""
    anchor = '''@app.post("/admin/feedback/delete/{feedback_id}")'''
    if anchor in content:
        print("ℹ️  Подсказка: убедитесь, что Nginx передаёт заголовок X-Forwarded-For")
        return content, True
    return content, False


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем из backup...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    print("✅ Восстановлено")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Патч: Rate Limiting")
    print("=" * 60)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    results = []
    content, ok1 = patch_imports(content)
    content, ok2 = patch_rate_limiter(content)
    content, ok3 = patch_upload_endpoint(content)
    content, ok4 = patch_register_endpoint(content)
    content, ok5 = patch_feedback_endpoint(content)
    results = [ok1, ok2, ok3, ok4, ok5]

    if not any(results):
        print("\n❌ Ни один патч не применён.")
        if input("Восстановить? (y/n): ").strip().lower() == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
        sys.exit(1)

    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    if not verify():
        sys.exit(1)

    print("\n🎉 Патч применён! Пересоберите контейнер:")
    print("   docker compose down && docker compose up -d --build")
    print("\n📌 Лимиты:")
    print("   • Гость/Free: 5 запросов /upload в минуту")
    print("   • Pro/Admin:  30 запросов /upload в минуту")
    print("   • Общий:      120 запросов в минуту на любой эндпоинт")
