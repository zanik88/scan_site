#!/usr/bin/env python3
"""Улучшает отображение колонки «Категория» — цветные бейджи фиксированной ширины."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_cat_ui"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Добавить функцию _category_badge() перед _detect_category
# ============================================================
anchor1 = "def _detect_category(name: str) -> str:"
badge_func = '''def _category_badge(cat: str) -> str:
    """Возвращает HTML-бейдж для категории с фиксированным цветом."""
    colors = {
        "Операционные системы": "#e53e3e",
        "СУБД и хранилища": "#dd6b20",
        "Языки и рантаймы": "#3182ce",
        "Фреймворки": "#805ad5",
        "Библиотеки": "#38a169",
        "Мониторинг и логирование": "#319795",
        "Очереди сообщений": "#5a67d8",
        "Контейнеризация и оркестрация": "#00b5d8",
        "Облачные сервисы": "#0ea5e9",
        "Игровые движки": "#ed64a6",
        "ИИ и ML": "#d53f8c",
        "Инструменты разработки": "#718096",
        "IDE и редакторы": "#2c5282",
        "Системные библиотеки": "#4a5568",
        "Прочее": "#a0aec0",
    }
    color = colors.get(cat, "#a0aec0")
    # Короткие метки для длинных категорий
    short = {
        "Мониторинг и логирование": "Мониторинг",
        "Контейнеризация и оркестрация": "Контейнеры",
        "Инструменты разработки": "Инструменты",
        "Операционные системы": "ОС",
        "СУБД и хранилища": "СУБД",
        "Языки и рантаймы": "Языки",
        "Игровые движки": "Геймдев",
        "Очереди сообщений": "Очереди",
        "Облачные сервисы": "Облако",
        "IDE и редакторы": "IDE",
    }
    label = short.get(cat, cat)
    return f'<span style="display:inline-block;background:{color};color:white;padding:4px 10px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;min-width:80px;text-align:center;">{label}</span>'


def _detect_category(name: str) -> str:'''

if "_category_badge" not in content and anchor1 in content:
    content = content.replace(anchor1, badge_func, 1)
    patched.append("Функция _category_badge добавлена")

# ============================================================
# 2. Заменить старую вставку категории на бейдж
# ============================================================
old_td = '''<td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;'><span style='background:#edf2f7;padding:3px 8px;border-radius:4px;font-size:12px;'>{cat}</span></td>'''
new_td = '''<td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;text-align:center;width:120px;'>{_category_badge(cat)}</td>'''

if old_td in content:
    content = content.replace(old_td, new_td, 1)
    patched.append("HTML категории заменён на бейдж")

# ============================================================
# 3. Заголовок колонки — центрировать и задать ширину
# ============================================================
old_th = '''<th onclick="sortTable(3)">Категория <span class="sort-arrow"></span></th>'''
new_th = '''<th onclick="sortTable(3)" style="text-align:center;width:120px;">Категория <span class="sort-arrow"></span></th>'''

if old_th in content:
    content = content.replace(old_th, new_th, 1)
    patched.append("Заголовок колонки отцентрирован")

# ============================================================
# Записать
# ============================================================
with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.2.1")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
