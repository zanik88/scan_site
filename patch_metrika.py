#!/usr/bin/env python3
"""Добавляет Яндекс.Метрику (ID 113107006) через middleware на все страницы."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_metrika"

shutil.copy2(MAIN, BAK)
print("Backup:", BAK)

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Проверка: если уже добавлено — выйти
if "mc.yandex.ru/metrika" in content:
    print("ИНФО: Метрика уже добавлена в код.")
    sys.exit(0)

# Найти middleware log_visits и добавить ДО него наш middleware
anchor = '@app.middleware("http")\nasync def log_visits('

metrika_code = '''METRIKA_ID = "113107006"

METRIKA_SCRIPT = """<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
    m[i].l=1*new Date();
    for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
    k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
    (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

    ym(""" + METRIKA_ID + """, "init", {
        ssr: true,
        webvisor: true,
        clickmap: true,
        ecommerce: "dataLayer",
        accurateTrackBounce: true,
        trackLinks: true
    });
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/""" + METRIKA_ID + """" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->"""


@app.middleware("http")
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
    return response


@app.middleware("http")
async def log_visits('''

if anchor in content:
    content = content.replace(anchor, metrika_code, 1)
    print("OK: middleware add_metrika добавлен")
else:
    print("ОШИБКА: middleware log_visits не найден")
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
