#!/usr/bin/env python3
"""
Патч №2: дополнение базы знаний из таблицы Минцифры.
Добавляет разрешённые СУБД, серверы приложений и платформы.
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak2"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch_rules(content: str) -> tuple:
    """Вставляет разрешённые компоненты из таблицы Минцифры."""
    anchor = '''    "devexpress.mvvm": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress MVVM Framework."},
}'''

    new_block = '''    "devexpress.mvvm": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress MVVM Framework."},

    # ============================================================
    # РАЗРЕШЁННЫЕ компоненты из таблицы Минцифры (open-source / дружественные страны)
    # ============================================================

    # --- СУБД с открытой лицензией ---
    "couchdb": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache CouchDB — открытая лицензия."},
    "apache couchdb": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache CouchDB."},
    "hive": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Hive."},
    "apache hive": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Hive."},
    "oracle mysql community": {"license": "GPL-2.0", "status": "✅ Разрешено", "recommendation": "Oracle MySQL Community Edition — открытая лицензия. Внимание: Commercial-версия запрещена!"},
    "mysql community": {"license": "GPL-2.0", "status": "✅ Разрешено", "recommendation": "MySQL Community Edition."},
    "tibero": {"license": "Commercial (Южная Корея)", "status": "✅ Разрешено", "recommendation": "TmaxSoft Tibero — страна не накладывает санкции."},
    "tmaxsoft tibero": {"license": "Commercial (Южная Корея)", "status": "✅ Разрешено", "recommendation": "TmaxSoft Tibero."},
    "tmax": {"license": "Commercial (Южная Корея)", "status": "✅ Разрешено", "recommendation": "TmaxSoft — Южная Корея."},

    # --- Серверы приложений с открытой лицензией ---
    "libercat": {"license": "Российское ПО", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Libercat — российский сервер приложений."},
    "enhydra": {"license": "Open Source", "status": "✅ Разрешено", "recommendation": "Enhydra Server — открытая лицензия."},
    "enhydra server": {"license": "Open Source", "status": "✅ Разрешено", "recommendation": "Enhydra Server."},

    # --- Уточнения по EnterpriseDB ---
    "enterprisedb": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "EnterpriseDB — коммерческая редакция. Замена: Postgres Pro."},
    "edb postgres": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "EnterpriseDB Postgres. Замена: Postgres Pro."},
    "edb": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "EnterpriseDB. Замена: Postgres Pro."},
}'''

    if anchor in content:
        content = content.replace(anchor, new_block, 1)
        print("✅ Патч 1: разрешённые компоненты добавлены")
        return content, True
    print("⚠️ Якорь не найден. Проверьте main.py.")
    return content, False


def patch_hardcode(content: str) -> tuple:
    """Добавляет хардкод-проверки для EnterpriseDB и разрешённых компонентов."""
    anchor = '''    # Разрешённые СУБД (open-source из таблицы Минцифры)
    if "firebird" in search_clean:'''

    new_hardcode = '''    # EnterpriseDB — принудительно запрещено (таблица Минцифры)
    if "enterprisedb" in search_clean or "edb postgres" in search_clean or search_clean == "edb":
        return {"name": package_name, "version": table_version,
                "license": "Commercial / Proprietary",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 EnterpriseDB — коммерческая редакция. Замена: Postgres Pro</small>"}

    # Разрешённые СУБД и серверы приложений из таблицы Минцифры
    allowed_db_app = [
        ("couchdb", "Apache CouchDB", "Apache-2.0"),
        ("hive", "Apache Hive", "Apache-2.0"),
        ("tibero", "TmaxSoft Tibero", "Commercial (Южная Корея)"),
        ("libercat", "Libercat", "Российское ПО"),
        ("enhydra", "Enhydra Server", "Open Source"),
    ]
    for key, label, lic in allowed_db_app:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": lic,
                    "status": f"✅ Разрешено <br><small style='color:#2f855a;'>💡 {label} — открытая лицензия</small>"}

    # Oracle MySQL Community (открытая) vs Commercial (запрещена)
    if "mysql" in search_clean and "community" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "GPL-2.0",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 MySQL Community Edition — открытая лицензия</small>"}

    # Разрешённые СУБД (open-source из таблицы Минцифры)
    if "firebird" in search_clean:'''

    if anchor in content:
        content = content.replace(anchor, new_hardcode, 1)
        print("✅ Патч 2: хардкод-проверки добавлены")
        return content, True
    print("⚠️ Якорь хардкода не найден.")
    return content, False


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем из backup...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    print("✅ Восстановлено")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Патч №2: дополнение базы знаний (таблица Минцифры)")
    print("=" * 60)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content, ok1 = patch_rules(content)
    content, ok2 = patch_hardcode(content)
    if not (ok1 or ok2):
        print("\n❌ Патч не применён.")
        if input("Восстановить? (y/n): ").strip().lower() == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
        sys.exit(1)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите контейнер:")
    print("   docker compose down && docker compose up -d --build")
