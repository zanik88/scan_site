#!/usr/bin/env python3
"""Добавляет кэширование ответов ИИ в SQLite."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_ai_cache"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Добавить модель AILicenseCache перед Base.metadata.create_all
# ============================================================
anchor1 = "Base.metadata.create_all(bind=engine)"
new_model = '''class AILicenseCache(Base):
    __tablename__ = "ai_license_cache"
    id = Column(Integer, primary_key=True, index=True)
    component_name = Column(String, unique=True, index=True, nullable=False)
    license = Column(String, nullable=False)
    status = Column(String, nullable=False)
    recommendation = Column(Text, nullable=True)
    provider = Column(String, nullable=True)
    is_failure = Column(Boolean, default=False)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)'''

if "class AILicenseCache" not in content and anchor1 in content:
    content = content.replace(anchor1, new_model, 1)
    patched.append("Модель AILicenseCache добавлена")
else:
    print("ℹ️  Модель AILicenseCache уже есть или якорь не найден")

# ============================================================
# 2. Добавить функции кэша перед ask_ai_for_license
# ============================================================
anchor2 = "async def ask_ai_for_license(component_name: str, provider: str = \"auto\") -> tuple:"
cache_funcs = '''async def _get_ai_cache(component_name: str):
    """Получает запись из кэша ИИ-ответов. Возвращает (license, status, rec, provider) или None."""
    def query():
        db = SessionLocal()
        try:
            key = (component_name or "").lower().strip()
            if not key:
                return None
            now = datetime.utcnow()
            cache = db.query(AILicenseCache).filter(AILicenseCache.component_name == key).first()
            if not cache:
                return None
            ttl_days = 7 if cache.is_failure else 90
            age_days = (now - cache.created_at).days if cache.created_at else 0
            if age_days > ttl_days:
                db.delete(cache)
                db.commit()
                return None
            cache.hit_count = (cache.hit_count or 0) + 1
            cache.last_used = now
            db.commit()
            return (cache.license, cache.status, cache.recommendation or "", cache.provider or "")
        except Exception as e:
            print(f"[AI CACHE] Ошибка чтения: {e}")
            return None
        finally:
            db.close()
    return await asyncio.to_thread(query)


async def _save_ai_cache(component_name, license_, status, recommendation, provider, is_failure=False):
    """Сохраняет ответ ИИ в кэш."""
    def save():
        db = SessionLocal()
        try:
            key = (component_name or "").lower().strip()
            if not key:
                return
            existing = db.query(AILicenseCache).filter(AILicenseCache.component_name == key).first()
            if existing:
                existing.license = license_
                existing.status = status
                existing.recommendation = recommendation
                existing.provider = provider
                existing.is_failure = is_failure
                existing.created_at = datetime.utcnow()
            else:
                db.add(AILicenseCache(
                    component_name=key,
                    license=license_,
                    status=status,
                    recommendation=recommendation,
                    provider=provider,
                    is_failure=is_failure,
                ))
            db.commit()
        except Exception as e:
            print(f"[AI CACHE] Ошибка записи: {e}")
            db.rollback()
        finally:
            db.close()
    await asyncio.to_thread(save)


def cleanup_ai_cache():
    """Удаляет устаревшие записи кэша ИИ."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        old_success = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == False,
            AILicenseCache.created_at < now - timedelta(days=90)
        ).delete()
        old_failure = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == True,
            AILicenseCache.created_at < now - timedelta(days=7)
        ).delete()
        db.commit()
        if old_success or old_failure:
            print(f"[AI CACHE] Очищено: {old_success} успешных, {old_failure} неудачных")
    except Exception as e:
        print(f"[AI CACHE] Ошибка очистки: {e}")
    finally:
        db.close()


''' + anchor2

if "_get_ai_cache" not in content and anchor2 in content:
    content = content.replace(anchor2, cache_funcs, 1)
    patched.append("Функции кэша добавлены")
else:
    print("ℹ️  Функции кэша уже есть или якорь ask_ai_for_license не найден")

# ============================================================
# 3. Вставить проверку кэша в начало ask_ai_for_license
# ============================================================
anchor3 = '''async def ask_ai_for_license(component_name: str, provider: str = "auto") -> tuple:
    prompt = AI_PROMPT_TEMPLATE.format(component=component_name)'''

new_ask_start = '''async def ask_ai_for_license(component_name: str, provider: str = "auto") -> tuple:
    # --- Проверка кэша ---
    cached = await _get_ai_cache(component_name)
    if cached:
        lic, st, rec, prov = cached
        print(f"[AI CACHE] ✅ Хит для '{component_name}': {lic}")
        cache_note = f" (из кэша: {prov})" if prov else " (из кэша)"
        return (lic, st, rec + cache_note)

    prompt = AI_PROMPT_TEMPLATE.format(component=component_name)'''

if "[AI CACHE] ✅ Хит" not in content and anchor3 in content:
    content = content.replace(anchor3, new_ask_start, 1)
    patched.append("Проверка кэша встроена в ask_ai_for_license")
else:
    print("ℹ️  Проверка кэша уже есть или якорь не найден")

# ============================================================
# 4. Сохранять успешный ответ в кэш
# ============================================================
anchor4 = '''                return (result["license"], result.get("status", "⚠️ Требует внимания"), f"{rec} (ИИ: {result['provider']})")'''

new_success = '''                final_rec = f"{rec} (ИИ: {result['provider']})"
                final_status = result.get("status", "⚠️ Требует внимания")
                await _save_ai_cache(component_name, result["license"], final_status, final_rec, result["provider"], is_failure=False)
                return (result["license"], final_status, final_rec)'''

if "_save_ai_cache(component_name, result" not in content and anchor4 in content:
    content = content.replace(anchor4, new_success, 1)
    patched.append("Сохранение успешного ответа добавлено")
else:
    print("ℹ️  Сохранение успешного ответа уже есть")

# ============================================================
# 5. Сохранять неудачный ответ в кэш (TTL 7 дней)
# ============================================================
anchor5 = '''    print(f"[AI] ❌ Все ИИ недоступны для '{component_name}'.")
    return ("Не определена", "⚠️ Требует внимания", f"Не удалось определить лицензию для '{component_name}'. Требуется ручная проверка.")'''

new_failure = '''    print(f"[AI] ❌ Все ИИ недоступны для '{component_name}'.")
    fail_msg = f"Не удалось определить лицензию для '{component_name}'. Требуется ручная проверка."
    await _save_ai_cache(component_name, "Не определена", "⚠️ Требует внимания", fail_msg, None, is_failure=True)
    return ("Не определена", "⚠️ Требует внимания", fail_msg)'''

if "_save_ai_cache(component_name, \"Не определена\"" not in content and anchor5 in content:
    content = content.replace(anchor5, new_failure, 1)
    patched.append("Сохранение неудачного ответа добавлено")
else:
    print("ℹ️  Сохранение неудачного ответа уже есть")

# ============================================================
# 6. Запускать cleanup при старте (после sync_rules())
# ============================================================
anchor6 = "sync_rules()\n"
if "cleanup_ai_cache()" not in content and anchor6 in content:
    content = content.replace(anchor6, "sync_rules()\ncleanup_ai_cache()\n", 1)
    patched.append("Автоочистка кэша при старте добавлена")

# ============================================================
# Записать
# ============================================================
with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

# ============================================================
# Проверка синтаксиса
# ============================================================
print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
