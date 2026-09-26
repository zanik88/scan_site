#!/usr/bin/env python3
"""
Патч GigaChat OAuth: обмен Authorization Key на access_token.
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_gigachat"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Добавить кэш токена после GIGACHAT_API_KEY
anchor1 = 'GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")\n'
new1 = '''GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")

# Кэш access_token для GigaChat
_GIGACHAT_TOKEN_CACHE = {"token": None, "expires_at": 0}
'''
if "_GIGACHAT_TOKEN_CACHE" not in content:
    content = content.replace(anchor1, new1, 1)
    print("✅ Кэш токена добавлен")

# 2. Заменить функцию _call_gigachat
old_func = '''async def _call_gigachat(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    if not GIGACHAT_API_KEY:
        return None
    try:
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GIGACHAT_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "GigaChat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        async with session.post(url, headers=headers, json=payload, ssl=False, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                data = await resp.json()
                parsed = _extract_json(data["choices"][0]["message"]["content"])
                if parsed:
                    parsed["provider"] = "GigaChat"
                    return parsed
    except Exception as e:
        print(f"[AI] GigaChat error: {e}")
    return None'''

new_func = '''async def _get_gigachat_token(session: aiohttp.ClientSession) -> Optional[str]:
    """Обменивает Authorization Key на access_token (OAuth)."""
    now = time.time()
    if _GIGACHAT_TOKEN_CACHE["token"] and now < _GIGACHAT_TOKEN_CACHE["expires_at"] - 60:
        return _GIGACHAT_TOKEN_CACHE["token"]

    if not GIGACHAT_API_KEY:
        return None

    try:
        import uuid
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {GIGACHAT_API_KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"scope": "GIGACHAT_API_PERS"}
        async with session.post(url, headers=headers, data=data, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                result = await resp.json()
                token = result.get("access_token")
                expires = result.get("expires_at", 0) / 1000  # мс → сек
                _GIGACHAT_TOKEN_CACHE["token"] = token
                _GIGACHAT_TOKEN_CACHE["expires_at"] = expires
                print(f"[AI] GigaChat: получен новый токен (до {datetime.fromtimestamp(expires).strftime('%H:%M:%S')})")
                return token
            else:
                err = await resp.text()
                print(f"[AI] GigaChat OAuth ошибка: {resp.status} {err[:200]}")
    except Exception as e:
        print(f"[AI] GigaChat OAuth исключение: {e}")
    return None


async def _call_gigachat(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    if not GIGACHAT_API_KEY:
        return None
    try:
        token = await _get_gigachat_token(session)
        if not token:
            return None
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"model": "GigaChat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        async with session.post(url, headers=headers, json=payload, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                parsed = _extract_json(data["choices"][0]["message"]["content"])
                if parsed:
                    parsed["provider"] = "GigaChat"
                    return parsed
            else:
                err = await resp.text()
                print(f"[AI] GigaChat chat ошибка: {resp.status} {err[:200]}")
    except Exception as e:
        print(f"[AI] GigaChat error: {e}")
    return None'''

if old_func in content:
    content = content.replace(old_func, new_func, 1)
    print("✅ Функция _call_gigachat обновлена (OAuth)")
else:
    print("⚠️ Старая функция _call_gigachat не найдена — возможно, уже обновлена")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

# Проверка синтаксиса
print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("❌ Ошибка! Восстанавливаем из backup...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
