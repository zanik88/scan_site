#!/usr/bin/env python3
"""
Cleanup дублей rate-limiter в main.py.
Оставляет только первый вызов check_rate_limit в /upload и /register.
"""
import shutil, sys, os, re

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak_cleanup"


def backup():
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def cleanup(content):
    # --- 1. Удалить дублирующийся блок check_rate_limit (второй) ---
    # Паттерн: def check_rate_limit(...) ... return True, limit - len(bucket), 0
    pattern = re.compile(
        r"def check_rate_limit\(request, endpoint, user=None\):.*?return True, limit - len\(bucket\), 0\n",
        re.DOTALL,
    )
    matches = pattern.findall(content)
    print(f"🔍 Найдено определений check_rate_limit: {len(matches)}")

    if len(matches) > 1:
        # Оставляем первое, удаляем остальные
        first_match = matches[0]
        # Заменяем все остальные вхождения на пустоту (кроме первого)
        parts = pattern.split(content)
        # parts[0] — до первого, parts[1] — между 1 и 2, parts[2] — после 2
        if len(parts) >= 3:
            content = parts[0] + first_match + "".join(parts[2:])
            print("✅ Дублирующиеся определения check_rate_limit удалены")

    # --- 2. Удалить дублирующиеся вызовы check_rate_limit в /upload ---
    # Ищем подряд идущие одинаковые блоки
    call_pattern = re.compile(
        r'(    allowed, remaining, retry_after = check_rate_limit\(request, "/upload", user\)\n'
        r'.*?status_code=429,\n.*?retry_after\},\n        \)\n)',
        re.DOTALL,
    )
    matches = call_pattern.findall(content)
    print(f"🔍 Найдено вызовов check_rate_limit в /upload: {len(matches)}")

    if len(matches) > 1:
        first = matches[0]
        # Оставляем первое, остальные заменяем
        parts = call_pattern.split(content)
        # parts[0] + первое + parts[1] + ... + удалить остальные
        if len(parts) >= 3:
            content = parts[0] + first + "".join(parts[2:])
            print("✅ Дублирующиеся вызовы в /upload удалены")

    # --- 3. Удалить дублирующиеся определения RATE_LIMIT_* ---
    if content.count("RATE_LIMIT_WINDOW = 60") > 1:
        # Оставляем первое определение, остальные вместе с _RATE_BUCKETS удаляем
        parts = content.split("RATE_LIMIT_WINDOW = 60")
        if len(parts) > 2:
            # Найти блок второго определения и удалить
            second_block_match = re.search(
                r"# окно в секундах\nRATE_LIMIT_GUEST.*?_RATE_BUCKETS = defaultdict\(list\)\n",
                "RATE_LIMIT_WINDOW = 60" + parts[2],
                re.DOTALL,
            )
            if second_block_match:
                content = parts[0] + "RATE_LIMIT_WINDOW = 60" + parts[1]
                rest = parts[2].replace(second_block_match.group(0), "", 1)
                content += rest
                print("✅ Дублирующиеся RATE_LIMIT_* удалены")

    return content


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    return False


if __name__ == "__main__":
    print("=" * 55)
    print("🔧 Cleanup дублей rate limiter")
    print("=" * 55)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        c = f.read()
    c = cleanup(c)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(c)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down && docker compose up -d --build")
