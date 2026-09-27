#!/usr/bin/env python3
"""
Патч v4: убирает обрезку многословных названий до первого слова.
- Если нет явного разделителя (==, —, :) — возвращаем всю строку
- Улучшен фильтр имён людей
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_parser_v4"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Заменить fallback в _split_name_version
# ============================================================
old_fallback = '''    # --- Fallback: первое слово — имя, второе — версия (если цифры) ---
    parts = re.split(r'\\s+', line_clean, maxsplit=2)
    if len(parts) >= 2:
        name = parts[0].strip()
        ver = parts[1].strip().lstrip("^~v=")
        if re.match(r'^[\\d]', ver):
            return (name, ver)
        return (name, "unknown")
    return (line_clean, "unknown")'''

new_fallback = '''    # --- Fallback: возвращаем всю строку как имя, версия unknown ---
    # Если в строке есть цифры в конце — попробуем извлечь как версию
    m = re.match(r'^([^\\d]+?)\\s+([\\d][\\d\\.\\-\\w]*)$', line_clean)
    if m:
        name = m.group(1).strip()
        ver = m.group(2).strip()
        if len(name) >= 2:
            return (name, ver)
    # Иначе — вся строка как имя
    return (line_clean, "unknown")'''

if old_fallback in content:
    content = content.replace(old_fallback, new_fallback, 1)
    patched.append("_split_name_version: убрана обрезка до первого слова")
else:
    print("⚠️ Старый fallback не найден")

# ============================================================
# 2. Улучшить _is_garbage_component — фильтр имён людей
# ============================================================
old_people_check = '''    if "," in n and len(n.split(",")) > 1:
        return True'''

new_people_check = '''    if "," in n and len(n.split(",")) > 1:
        return True
    # Имена людей: два-три слова с заглавной буквы (не название)
    words = n.split()
    if 2 <= len(words) <= 3:
        if all(w[0].isupper() for w in words if w):
            # Проверить, что это не название продукта
            product_markers = [
                "server", "windows", "linux", "oracle", "microsoft", "ibm",
                "sap", "adobe", "amazon", "google", "docker", "kubernetes",
                "red hat", "enterprise", "community", "edition", "runtime",
                "toolkit", "framework", "python", "java", "node", "npm",
                "apache", "nginx", "postgres", "mysql", "redis", "kafka",
                "grafana", "zabbix", "prometheus", "unity", "unreal",
                "active", "director", "visual", "studio", "source",
                "git", "gitlab", "jenkins", "teamcity", "sonar",
                "hashicorp", "vault", "consul", "nomad", "boundary",
                "elastic", "opensearch", "fluent", "opentelemetry",
                "py", "torch", "tensor", "flow", "open", "policy",
            ]
            lower = n.lower()
            if not any(m in lower for m in product_markers):
                return True'''

if old_people_check in content:
    content = content.replace(old_people_check, new_people_check, 1)
    patched.append("_is_garbage_component: фильтр имён людей")
else:
    print("⚠️ Якорь с запятыми не найден")

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
