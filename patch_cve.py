#!/usr/bin/env python3
"""
Скрипт для точечного патча main.py:
1. Делает резервную копию main.py.bak
2. Заменяет логику отображения CVE на более строгую (CRITICAL/HIGH → Требует внимания)
3. Проверяет синтаксис после замены
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия создана: {BACKUP_FILE}")


def patch_file():
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Патч 1: для process_audit_task
    old_block_audit = '''                if r["cve_count"] > 0 and "❌" not in str(r.get("status", "")):
                    r["status"] = r["status"] + f" <br><small style='color:#e53e3e;'>🔒 Найдено {r['cve_count']} уязвимостей</small>"'''

    new_block_audit = '''                if r["cve_count"] > 0 and "❌" not in str(r.get("status", "")):
                    has_critical = any(v.get("severity") in ("CRITICAL", "HIGH") for v in r.get("cve_list", []))
                    if has_critical and "⚠️" not in str(r.get("status", "")):
                        r["status"] = "⚠️ Требует внимания <br><small style='color:#e53e3e;'>🔒 " + str(r["cve_count"]) + " уязвимостей (CRITICAL/HIGH)</small>"
                    else:
                        r["status"] = r["status"] + f" <br><small style='color:#e53e3e;'>🔒 Найдено {r['cve_count']} уязвимостей</small>"'''

    # Патч 2: для process_docker_scan_task
    old_block_docker = '''                for r in report_data:
                    vulns = vuln_results.get(r.get("name", ""), {})
                    r["cve_count"] = vulns.get("count", 0)
                    r["cve_list"] = vulns.get("vulns", [])
                    if r["cve_count"] > 0 and "❌" not in str(r.get("status", "")):
                        r["status"] = r["status"] + f" <br><small style='color:#e53e3e;'>🔒 Найдено {r['cve_count']} уязвимостей</small>"'''

    new_block_docker = '''                for r in report_data:
                    vulns = vuln_results.get(r.get("name", ""), {})
                    r["cve_count"] = vulns.get("count", 0)
                    r["cve_list"] = vulns.get("vulns", [])
                    if r["cve_count"] > 0 and "❌" not in str(r.get("status", "")):
                        has_critical = any(v.get("severity") in ("CRITICAL", "HIGH") for v in r.get("cve_list", []))
                        if has_critical and "⚠️" not in str(r.get("status", "")):
                            r["status"] = "⚠️ Требует внимания <br><small style='color:#e53e3e;'>🔒 " + str(r["cve_count"]) + " уязвимостей (CRITICAL/HIGH)</small>"
                        else:
                            r["status"] = r["status"] + f" <br><small style='color:#e53e3e;'>🔒 Найдено {r['cve_count']} уязвимостей</small>"'''

    patched_count = 0

    if old_block_audit in content:
        content = content.replace(old_block_audit, new_block_audit, 1)
        patched_count += 1
        print("✅ Патч 1 применён (process_audit_task)")
    else:
        print("⚠️ Патч 1: блок не найден (возможно, уже пропатчен или отступы отличаются)")

    if old_block_docker in content:
        content = content.replace(old_block_docker, new_block_docker, 1)
        patched_count += 1
        print("✅ Патч 2 применён (process_docker_scan_task)")
    else:
        print("⚠️ Патч 2: блок не найден (возможно, уже пропатчен или отступы отличаются)")

    if patched_count == 0:
        print("\n❌ Ничего не заменено. Проверьте, что версия main.py актуальна.")
        print("   Возможно, патч уже применён или код был изменён вручную.")
        restore = input("Восстановить из резервной копии? (y/n): ").strip().lower()
        if restore == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
            print("✅ Восстановлено из резервной копии")
        sys.exit(1)

    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✅ Записано {patched_count} патч(ей) в {MAIN_FILE}")


def verify_syntax():
    print("\n🔍 Проверка синтаксиса...")
    result = os.system("python3 -m py_compile main.py")
    if result == 0:
        print("✅ Синтаксис корректен")
        return True
    else:
        print("❌ Ошибка синтаксиса! Восстанавливаем из резервной копии...")
        shutil.copy2(BACKUP_FILE, MAIN_FILE)
        print("✅ Файл восстановлен из main.py.bak")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("🔧 Патч CVE-логики для main.py")
    print("=" * 50)
    backup()
    patch_file()
    if not verify_syntax():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите контейнер:")
    print("   docker compose down -v && docker compose up -d --build")
