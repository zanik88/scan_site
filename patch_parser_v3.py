#!/usr/bin/env python3
"""
Парсер v3:
1. Maven-координаты: group:artifact:jar:version:scope
2. npm: @scope/package — ^version — npm: ...
3. Приватные библиотеки: ru.logic.bpm:*, @logicbpm/*, ru.logic.bpm
4. Улучшенный фильтр мусора
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_parser_v3"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Заменить _split_name_version целиком
# ============================================================
old_split_start = "def _split_name_version(line: str) -> tuple:"
old_split_end = "def _is_license_like(text: str) -> bool:"

new_split = '''def _split_name_version(line: str) -> tuple:
    """Разбирает строку на имя и версию. Поддерживает Maven, npm, pip."""
    line = line.strip()
    if not line:
        return ("", "unknown")

    # Убираем нумерацию в начале: "1. ", "169. "
    line_clean = re.sub(r'^\\d+\\.\\s*', '', line)

    # --- Maven-координаты: group:artifact:jar:version:scope ---
    maven_match = re.match(
        r'^([a-zA-Z0-9_\\-\\.]+:[a-zA-Z0-9_\\-\\.]+):(jar|war|pom|aar|bundle):([^:]+):(compile|runtime|test|provided|system)',
        line_clean
    )
    if maven_match:
        name = maven_match.group(1)
        version = maven_match.group(3)
        return (name, version)

    # Упрощённый Maven: group:artifact:version
    maven_simple = re.match(
        r'^([a-zA-Z0-9_\\-\\.]+:[a-zA-Z0-9_\\-\\.]+):([\\d][^:\\s]*)',
        line_clean
    )
    if maven_simple and ':' in maven_simple.group(1):
        return (maven_simple.group(1), maven_simple.group(2))

    # --- npm с em-dash: @scope/package — ^version — npm: ... ---
    if "—" in line_clean or "–" in line_clean:
        parts = re.split(r'\\s*[—–]\\s*', line_clean)
        if len(parts) >= 2:
            name = parts[0].strip()
            ver_raw = parts[1].strip()
            # Убираем ^ ~ v = из версии
            ver_clean = re.sub(r'^[\\^~v=\\s]+', '', ver_raw)
            # Если версия начинается с цифры — берём
            ver_match = re.match(r'^([\\d][^\\s,]*)', ver_clean)
            if ver_match:
                version = ver_match.group(1)
            else:
                version = ver_clean if ver_clean else "unknown"
            if len(name) >= 2:
                return (name, version)

    # --- pip: name==version ---
    m = re.match(r'^([A-Za-z0-9_\\-\\.]+)\\s*(==|>=|<=|~=|!=|>|<|=)\\s*([^\\s,;#]+)', line_clean)
    if m:
        return m.group(1).strip(), m.group(3).strip()

    # --- Формат "name: version" ---
    m = re.match(r'^["\\']?([A-Za-z0-9_\\-\\.@/]+)["\\']?\\s*:\\s*["\\']?[\\^~v=]?([\\d][^\\s,;"\\']*)', line_clean)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # --- Fallback: первое слово — имя, второе — версия (если цифры) ---
    parts = re.split(r'\\s+', line_clean, maxsplit=2)
    if len(parts) >= 2:
        name = parts[0].strip()
        ver = parts[1].strip().lstrip("^~v=")
        if re.match(r'^[\\d]', ver):
            return (name, ver)
        return (name, "unknown")
    return (line_clean, "unknown")


def _is_private_library(name: str) -> bool:
    """Определяет私有 библиотеки компании."""
    n = (name or "").lower().strip()
    if not n:
        return False
    private_markers = [
        "ru.logic.bpm", "logicbpm", "@logicbpm", "logic.bpm",
        "tenant-encryption", "tenant-interceptor", "tenant-kafka",
        "tenant-security", "tenant-storage",
    ]
    return any(marker in n for marker in private_markers)


'''

if old_split_start in content and old_split_end in content:
    start_idx = content.index(old_split_start)
    end_idx = content.index(old_split_end)
    content = content[:start_idx] + new_split + content[end_idx:]
    patched.append("_split_name_version: Maven/npm/pip + _is_private_library")
else:
    print("⚠️ Якоря _split_name_version / _is_license_like не найдены")

# ============================================================
# 2. Улучшить _is_garbage_component — добавить фильтры для мусора
# ============================================================
old_garbage_marker = '''    # Номера страниц в конце
    if re.search(r'\\s+\\d+$', n) and len(n.split()) > 2:
        return True'''

new_garbage_marker = '''    # Номера страниц в конце
    if re.search(r'\\s+\\d+$', n) and len(n.split()) > 2:
        return True
    # Только число (номер страницы)
    if re.match(r'^\\d+$', n):
        return True
    # Точки-разделители из оглавления
    if " . . " in n or "...." in n:
        return True
    # Строки с "— собственная разработка — приватный"
    if "приватный" in lower and "разработка" in lower and len(n.split()) > 5:
        return True
    # Заголовки типа "4.1. 1. Сервисы хранения данных"
    if re.match(r'^\\d+\\.\\d+\\.\\s+\\d+\\.', n):
        return True
    # Строки с "Дополненная версия документа"
    if lower.startswith(("дополненная", "указанные", "таким образом", "в ходе", "в составе")):
        return True'''

if old_garbage_marker in content:
    content = content.replace(old_garbage_marker, new_garbage_marker, 1)
    patched.append("_is_garbage_component: расширенный фильтр мусора")

# ============================================================
# 3. В parse_uploaded_file — пометка приватных библиотек
# ============================================================
old_extract_end = '''    # Дедупликация по имени (без учёта регистра)
    seen = set()
    unique = []
    for item in extracted:
        key = (item.get("name") or "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    extracted = unique'''

new_extract_end = '''    # Пометка приватных библиотек
    for item in extracted:
        if _is_private_library(item.get("name", "")):
            item["_private"] = True
            item["license"] = "Собственная разработка"
            item["status"] = "✅ Разрешено <br><small style='color:#2f855a;'>💡 Собственная разработка компании (не в публичных реестрах)</small>"
    # Дедупликация по имени (без учёта регистра)
    seen = set()
    unique = []
    for item in extracted:
        key = (item.get("name") or "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    extracted = unique'''

if old_extract_end in content:
    content = content.replace(old_extract_end, new_extract_end, 1)
    patched.append("Пометка приватных библиотек")

# ============================================================
# 4. В fetch_package_info_with_version — не спрашивать ИИ о приватных
# ============================================================
anchor_ai = '''    search_clean = sanitize_string(package_name)'''
new_ai = '''    search_clean = sanitize_string(package_name)

    # Приватные библиотеки — сразу возвращаем результат без ИИ
    if _is_private_library(package_name):
        return {"name": package_name, "version": table_version,
                "license": "Собственная разработка",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Собственная разработка компании</small>"}
'''

if "Приватные библиотеки — сразу возвращаем" not in content and anchor_ai in content:
    content = content.replace(anchor_ai, new_ai, 1)
    patched.append("Приватные библиотеки не отправляются в ИИ")

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
