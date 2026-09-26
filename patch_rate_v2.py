#!/usr/bin/env python3
"""
Патч: Rate Limiting (правильная версия без аннотации Optional[User]).
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak_rate_v2"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch_imports(content):
    if "from collections import defaultdict" in content:
        print("ℹ️  Импорт defaultdict уже есть")
    else:
        content = content.replace(
            "import sqlite3\n",
            "import sqlite3\nimport time\nfrom collections import defaultdict\n",
            1,
        )
        print("✅ Импорты time + defaultdict добавлены")
    if "import time\n" not in content:
        content = content.replace(
            "import sqlite3\n",
            "import sqlite3\nimport time\n",
            1,
        )
        print("✅ Импорт time добавлен")
    return content


def patch_limiter(content):
    if "RATE_LIMIT_WINDOW" in content:
        print("ℹ️  Rate limiter уже добавлен")
        return content

    anchor = "PROGRESS_TRACKER = {}\n"
    code = '''PROGRESS_TRACKER = {}

# ==========================================
# RATE LIMITING
# ==========================================
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_GUEST = 5
RATE_LIMIT_PRO = 30
RATE_LIMIT_GENERAL = 120

_RATE_BUCKETS = defaultdict(list)


def _get_client_ip(request):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request, endpoint, user=None):
    """Проверяет лимит. Возвращает (allowed, remaining, retry_after)."""
    ip = _get_client_ip(request)
    key = (ip, endpoint)
    now = time.time()
    bucket = _RATE_BUCKETS[key]
    bucket[:] = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]

    if user is not None and (getattr(user, "role", None) == "admin" or getattr(user, "subscription_plan", None) in ["Pro", "Unlimited"]):
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
        content = content.replace(anchor, code, 1)
        print("✅ Rate limiter добавлен")
    else:
        print("⚠️ Якорь PROGRESS_TRACKER не найден")
    return content


def patch_upload(content):
    if "# --- RATE LIMITING ---" in content:
        print("ℹ️  /upload уже защищён")
        return content

    anchor = '''    free_left = get_free_checks_left(user, request)
    unlimited = is_unlimited(user)

    if not unlimited and free_left <= 0:
        return RedirectResponse(url="/pricing", status_code=status.HTTP_303_SEE_OTHER)'''

    code = '''    allowed, remaining, retry_after = check_rate_limit(request, "/upload", user)
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
              <p><a href="/pricing" style="color:#3182ce;font-weight:600;">Тариф Pro → 30 проверок/мин</a></p>
              <p><a href="/" style="color:#718096;">← На главную</a></p>
            </div>
            </body></html>""",
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    free_left = get_free_checks_left(user, request)
    unlimited = is_unlimited(user)

    if not unlimited and free_left <= 0:
        return RedirectResponse(url="/pricing", status_code=status.HTTP_303_SEE_OTHER)'''

    if anchor in content:
        content = content.replace(anchor, code, 1)
        print("✅ /upload защищён")
    else:
        print("⚠️ Якорь /upload не найден")
    return content


def patch_register(content):
    old = '''async def register(company_name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   terms_accepted: str = Form(None), db: Session = Depends(get_db)):
    if not terms_accepted:'''

    new = '''async def register(request: Request, company_name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   terms_accepted: str = Form(None), db: Session = Depends(get_db)):
    allowed, _, retry_after = check_rate_limit(request, "/register")
    if not allowed:
        raise HTTPException(status_code=429,
                            detail=f"Слишком много попыток. Подождите {retry_after} сек.",
                            headers={"Retry-After": str(retry_after)})
    if not terms_accepted:'''

    if old in content:
        content = content.replace(old, new, 1)
        print("✅ /register защищён")
    else:
        print("⚠️ Якорь /register не найден (возможно, уже добавлен request)")
    return content


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Rate Limiting v2 (fix Optional[User])")
    print("=" * 60)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        c = f.read()

    c = patch_imports(c)
    c = patch_limiter(c)
    c = patch_upload(c)
    c = patch_register(c)

    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(c)

    if not verify():
        sys.exit(1)

    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
