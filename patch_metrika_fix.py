#!/usr/bin/env python3
"""Fix: правильный middleware Метрики через чтение body_iterator."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_metrika_fix"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

old_mw = '''@app.middleware("http")
async def add_metrika(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type and hasattr(response, "body"):
        try:
            body = response.body.decode("utf-8")
            if "</head>" in body and "mc.yandex.ru/metrika" not in body:
                body = body.replace("</head>", METRIKA_SCRIPT + "\\n</head>", 1)
                response.body = body.encode("utf-8")
                # Обновить Content-Length
                response.headers["content-length"] = str(len(response.body))
        except Exception as e:
            print(f"[METRIKA] error: {e}")
    return response'''

new_mw = '''@app.middleware("http")
async def add_metrika(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response
    try:
        # Собираем тело из стримингового ответа
        body_chunks = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            body_chunks.append(chunk)
        body = b"".join(body_chunks).decode("utf-8", errors="ignore")

        # Вставляем метрику перед </head>
        if "</head>" in body and "mc.yandex.ru/metrika" not in body:
            body = body.replace("</head>", METRIKA_SCRIPT + "\\n</head>", 1)
            print(f"[METRIKA] Скрипт вставлен в {request.url.path}")

        # Формируем новый ответ
        from starlette.responses import Response as StarletteResponse
        new_headers = {k: v for k, v in response.headers.items()
                       if k.lower() not in ("content-length", "content-type")}
        return StarletteResponse(
            content=body,
            status_code=response.status_code,
            headers=new_headers,
            media_type="text/html",
        )
    except Exception as e:
        print(f"[METRIKA] error: {e}")
        return response'''

if old_mw in content:
    content = content.replace(old_mw, new_mw, 1)
    print("OK: middleware заменён на версию с body_iterator")
else:
    print("ОШИБКА: старый middleware не найден")
    sys.exit(1)

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

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
