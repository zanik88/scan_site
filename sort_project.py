#!/usr/bin/env python3
"""Сортировка файлов проекта: .bak → backups/main_py/, патчи → patches/."""
import os
import shutil
from pathlib import Path

PROJECT = Path.cwd()
BACKUP_DIR = PROJECT / "backups" / "main_py"
PATCHES_DIR = PROJECT / "patches"

# Создаём папки
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
PATCHES_DIR.mkdir(parents=True, exist_ok=True)
print(f"Созданы папки:")
print(f"  {BACKUP_DIR}")
print(f"  {PATCHES_DIR}")

# Файлы, которые НЕ трогаем (в корне)
KEEP_IN_ROOT = {
    "main.py", "version.py", "release.sh", "backup.sh", "restore.sh",
    "sort_project.py",  # сам скрипт
    "README.md", "LICENSE", "LICENSE.txt", "requirements.txt",
    "Dockerfile", "docker-compose.yml", ".env", ".env.example",
    ".gitignore", ".dockerignore",
}

moved_backups = 0
moved_patches = 0

for item in PROJECT.iterdir():
    if not item.is_file():
        continue
    name = item.name

    # Пропускаем файлы, которые должны остаться в корне
    if name in KEEP_IN_ROOT:
        continue

    # .bak файлы → backups/main_py/
    if ".bak" in name:
        target = BACKUP_DIR / name
        # Если файл с таким именем уже есть — добавим суффикс
        if target.exists():
            base = target.stem
            ext = target.suffix
            counter = 1
            while (BACKUP_DIR / f"{base}_{counter}{ext}").exists():
                counter += 1
            target = BACKUP_DIR / f"{base}_{counter}{ext}"
        shutil.move(str(item), str(target))
        moved_backups += 1
        continue

    # main.py.working.* → backups/main_py/
    if name.startswith("main.py.working"):
        target = BACKUP_DIR / name
        if target.exists():
            base = target.stem
            ext = target.suffix
            counter = 1
            while (BACKUP_DIR / f"{base}_{counter}{ext}").exists():
                counter += 1
            target = BACKUP_DIR / f"{base}_{counter}{ext}"
        shutil.move(str(item), str(target))
        moved_backups += 1
        continue

    # patch_*.py и fix_*.py → patches/
    if (name.startswith("patch_") or name.startswith("fix_")) and name.endswith(".py"):
        target = PATCHES_DIR / name
        if target.exists():
            base = target.stem
            counter = 1
            while (PATCHES_DIR / f"{base}_{counter}.py").exists():
                counter += 1
            target = PATCHES_DIR / f"{base}_{counter}.py"
        shutil.move(str(item), str(target))
        moved_patches += 1
        continue

print()
print(f"Перемещено:")
print(f"  .bak-файлов: {moved_backups}")
print(f"  патчей: {moved_patches}")

# Обновляем .gitignore
gitignore = PROJECT / ".gitignore"
if gitignore.exists():
    with open(gitignore, "r", encoding="utf-8") as f:
        gitignore_content = f.read()

    additions = []
    for pattern in ["backups/main_py/", "patches/", "*.bak", "main.py.bak*", "main.py.working*"]:
        if pattern not in gitignore_content:
            additions.append(pattern)

    if additions:
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write("\n# Автоматическая сортировка проекта\n")
            for a in additions:
                f.write(a + "\n")
        print()
        print(f"Обновлён .gitignore: добавлено {len(additions)} паттернов")
    else:
        print()
        print(".gitignore уже содержит нужные паттерны")
else:
    print()
    print("ВНИМАНИЕ: .gitignore не найден")

print()
print("=" * 50)
print("Готово! Проверьте содержимое папки.")
print("=" * 50)
