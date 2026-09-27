#!/usr/bin/env python3
"""
Улучшение парсера v2:
1. Поддержка формата "name — version — url" (em-dash)
2. Фильтрация заголовков (Оглавление, FRONTEND, BACKEND, Пояснительная)
3. Дедупликация компонентов
4. Пауза между ИИ-запросами 1.5 → 0.7 сек
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_parser_v2"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Улучшить _split_name_version — поддержка em-dash "name — version — url"
# ============================================================
old_split = '''def _split_name_version(line: str) -> tuple:
    line = line.strip()
    m = re.match(r'^([A-Za-z0-9_\\-\\.]+)\\s*(==|>=|<=|~=|!=|>|<|=)\\s*([^\\s,;#]+)', line)
    if m:
        return m.group(1).strip(), m.group(3).strip()'''

new_split = '''def _split_name_version(line: str) -> tuple:
    line = line.strip()
    # Формат "name — version — url" (em-dash или en-dash)
    if "—" in line or "–" in line:
        parts = re.split(r'\\s*[—–]\\s*', line)
        if len(parts) >= 2:
            name = parts[0].strip()
            ver = parts[1].strip().lstrip("^~v=")
            # Отсеять мусорные имена (номера, слишком короткие)
            name = re.sub(r'^\\d+\\.\\s*', '', name)  # убрать "1. "
            if len(name) >= 2 and ver:
                return name, ver if ver else "unknown"
    # Формат "name: version" или "name == version"
    m = re.match(r'^([A-Za-z0-9_\\-\\.\\@/]+)\\s*(==|>=|<=|~=|!=|>|<|=)\\s*([^\\s,;#]+)', line)
    if m:
        return m.group(1).strip(), m.group(3).strip()'''

if old_split in content:
    content = content.replace(old_split, new_split, 1)
    patched.append("_split_name_version: поддержка формата с тире")

# ============================================================
# 2. Улучшить _is_garbage_component — фильтр заголовков
# ============================================================
old_garbage = '''    if lower.startswith(("author", "copyright", "company", "namespace", "project",
                          "creator", "maintainer", "owner", "publisher")):
        return True
    if lower in ("name", "название", "компонент", "component"):
        return True'''

new_garbage = '''    if lower.startswith(("author", "copyright", "company", "namespace", "project",
                          "creator", "maintainer", "owner", "publisher")):
        return True
    if lower in ("name", "название", "компонент", "component"):
        return True
    # Заголовки и разделы документа
    headers = (
        "оглавление", "содержание", "frontend", "backend", "введение",
        "пояснительная", "заключение", "приложение", "раздел", "глава",
        "список", "перечень", "описание", "аннотация", "титульный",
        "table of contents", "contents", "introduction", "conclusion",
        "appendix", "chapter", "section", "list of",
    )
    if any(lower.startswith(h) for h in headers):
        return True
    # Пронумерованные заголовки: "1. Список основных библиотек..."
    if re.match(r'^\\d+\\.\\s+[А-ЯA-Z]', n):
        # Но не "1. react" — если после цифры идёт слово с маленькой или дефис
        # Проверяем: если больше 4 слов — это заголовок
        rest = re.sub(r'^\\d+\\.\\s+', '', n)
        if len(rest.split()) > 3:
            return True
    # Строки с многоточием (оглавление): "1. FRONTEND . . . . 1"
    if "..." in n or " . . " in n or "…" in n:
        return True
    # Слишком длинные строки (описания, а не названия)
    if len(n) > 100:
        return True
    # Номера страниц в конце
    if re.search(r'\\s+\\d+$', n) and len(n.split()) > 2:
        return True'''

if old_garbage in content:
    content = content.replace(old_garbage, new_garbage, 1)
    patched.append("_is_garbage_component: фильтр заголовков")

# ============================================================
# 3. Дедупликация в parse_uploaded_file
# ============================================================
old_dedup = '''    except Exception as e:
        print(f"Parse error {filename}: {e}")
    # Нормализация: если "версия" на самом деле лицензия — сбрасываем
    for item in extracted:
        if _is_license_like(item.get("version", "")):
            item["version"] = "unknown"
    if not extracted:
        extracted = [{"name": filename.split(".")[0], "version": "1.0.0"}]
    return extracted'''

new_dedup = '''    except Exception as e:
        print(f"Parse error {filename}: {e}")
    # Нормализация: если "версия" на самом деле лицензия — сбрасываем
    for item in extracted:
        if _is_license_like(item.get("version", "")):
            item["version"] = "unknown"
    # Дедупликация по имени (без учёта регистра)
    seen = set()
    unique = []
    for item in extracted:
        key = (item.get("name") or "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    extracted = unique
    if not extracted:
        extracted = [{"name": filename.split(".")[0], "version": "1.0.0"}]
    return extracted'''

if old_dedup in content:
    content = content.replace(old_dedup, new_dedup, 1)
    patched.append("Дедупликация компонентов")

# ============================================================
# 4. Уменьшить паузу между ИИ-запросами 1.5 → 0.7 сек
# ============================================================
old_pause = 'await asyncio.sleep(1.5)'
new_pause = 'await asyncio.sleep(0.7)'

if old_pause in content:
    content = content.replace(old_pause, new_pause, 1)
    patched.append("Пауза между ИИ-запросами: 1.5 → 0.7 сек")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.3.2")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
