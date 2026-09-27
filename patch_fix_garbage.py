#!/usr/bin/env python3
"""
Fix: восстанавливает _is_garbage_component (потерянную в parser_v3).
Плюс проверяет _is_license_like.
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_fix_garbage"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Проверить, что есть _is_license_like
# ============================================================
if "def _is_license_like(" not in content:
    print("⚠️ _is_license_like тоже потерян — восстанавливаем")
    # Добавим перед parse_uploaded_file
    anchor = "def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:"
    lic_func = '''def _is_license_like(text: str) -> bool:
    """Проверяет, похоже ли значение на название лицензии, а не на версию."""
    if not text:
        return False
    t = str(text).strip().lower()
    if not t or t == "unknown":
        return False
    license_markers = [
        "mit", "apache", "bsd", "gpl", "lgpl", "mpl", "epl",
        "isc", "cc0", "cc-by", "unlicense", "public domain",
        "proprietary", "commercial", "eula", "sspl", "bsl",
        "artistic", "cddl", "zlib", "wtfpl", "agpl",
    ]
    if t in license_markers:
        return True
    for m in license_markers:
        if t.startswith(m) or t.endswith(m):
            return True
    if not any(c.isdigit() for c in t):
        return True
    return False


def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:'''
    if anchor in content:
        content = content.replace(anchor, lic_func, 1)
        patched.append("Восстановлена _is_license_like")
else:
    print("✅ _is_license_like на месте")

# ============================================================
# 2. Восстановить _is_garbage_component
# ============================================================
if "def _is_garbage_component(" not in content:
    anchor2 = "def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:"
    garbage_func = '''def _is_garbage_component(name: str) -> bool:
    """Отсеивает авторов, пространства имён и метаданные."""
    if not name:
        return True
    n = name.strip()
    if len(n) < 2:
        return True
    if n.startswith('['):
        return True
    if "," in n and len(n.split(",")) > 1:
        return True
    lower = n.lower()
    if lower.startswith(("author", "copyright", "company", "namespace", "project",
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
    # Пронумерованные заголовки
    if re.match(r'^\\d+\\.\\s+[А-ЯA-Z]', n):
        rest = re.sub(r'^\\d+\\.\\s+', '', n)
        if len(rest.split()) > 3:
            return True
    # Многоточия из оглавления
    if "..." in n or " . . " in n or "…" in n:
        return True
    # Слишком длинные строки
    if len(n) > 100:
        return True
    # Номер страницы в конце длинной строки
    if re.search(r'\\s+\\d+$', n) and len(n.split()) > 2:
        return True
    # Только число
    if re.match(r'^\\d+$', n):
        return True
    # Приватные/служебные строки
    if lower.startswith(("дополненная", "указанные", "таким образом", "в ходе", "в составе")):
        return True
    # URL
    if lower.startswith(("http://", "https://", "www.")):
        return True
    # Строки с "для установки", "this document"
    if "для установки" in lower or "this document" in lower:
        return True
    return False


def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:'''
    if anchor2 in content:
        content = content.replace(anchor2, garbage_func, 1)
        patched.append("Восстановлена _is_garbage_component")
else:
    print("✅ _is_garbage_component на месте")

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
