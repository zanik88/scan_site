#!/usr/bin/env python3
"""
Жёсткая проверка запрещённых/разрешённых компонентов из таблицы Минцифры.
Выполняется ДО цикла по DEFAULT_RULES — 100% надёжно.
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
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch(content: str) -> tuple:
    """Вставляет хардкод-проверки перед проверкой Elasticsearch."""
    anchor = '''    if any(re.search(r'\\b' + re.escape(e) + r'\\b', search_clean) for e in ["elasticsearch", "kibana", "logstash"]):'''

    hardcode = '''    # ============================================================
    # ХАРДКОД: компоненты из таблицы Минцифры (100% надёжно)
    # ============================================================

    # DevExpress (все модули)
    if "devexpress" in search_clean or "dev express" in search_clean or "devart" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Commercial / DevExpress EULA",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Экспортные ограничения. Замена: открытые UI-библиотеки</small>"}

    # Запрещённые СУБД
    banned_db = [
        ("ibm db2", "IBM DB2"),
        ("db2", "IBM DB2"),
        ("intersystems", "InterSystems Caché"),
        ("splunk", "Splunk"),
        ("sap ase", "SAP ASE"),
        ("sybase", "Sybase"),
        ("sap sql anywhere", "SAP SQL Anywhere"),
        ("sap hana", "SAP HANA"),
        ("oracle nosql", "Oracle NoSQL"),
        ("oracle mysql", "Oracle MySQL"),
        ("oracle database", "Oracle Database"),
    ]
    for key, label in banned_db:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}. Замена: Postgres Pro / MariaDB</small>"}

    # Запрещённые серверы приложений
    banned_app_servers = [
        ("websphere", "IBM WebSphere"),
        ("weblogic", "Oracle WebLogic"),
        ("jboss", "Red Hat JBoss EAP"),
        ("coldfusion", "Adobe ColdFusion"),
        ("netweaver", "SAP NetWeaver"),
        ("zend server", "RogueWave Zend Server"),
    ]
    for key, label in banned_app_servers:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}. Замена: WildFly / TomEE</small>"}

    # Запрещённые платформы
    banned_platforms = [
        ("filenet", "IBM FileNet"),
        ("lotus domino", "IBM Lotus Domino"),
        ("lotus notes", "IBM Lotus Notes"),
    ]
    for key, label in banned_platforms:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}.</small>"}

    # Запрещённые ОС
    banned_os = [
        ("redhat", "Red Hat Enterprise Linux"),
        ("red hat", "Red Hat Enterprise Linux"),
        ("suse linux", "SUSE Linux Enterprise"),
        ("sles", "SUSE Linux Enterprise Server"),
    ]
    for key, label in banned_os:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}. Замена: Astra Linux / ALT Linux</small>"}

    # Разрешённые серверы приложений (open-source из таблицы Минцифры)
    allowed_app_servers = [
        ("wildfly", "WildFly", "LGPL-2.1"),
        ("tomee", "Apache TomEE", "Apache-2.0"),
        ("geronimo", "Apache Geronimo", "Apache-2.0"),
        ("glassfish", "GlassFish", "CDDL / GPL"),
        ("resin", "Resin", "GPL / Commercial"),
    ]
    for key, label, lic in allowed_app_servers:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": lic,
                    "status": f"✅ Разрешено <br><small style='color:#2f855a;'>💡 {label} — открытая лицензия</small>"}

    # Разрешённые СУБД (open-source из таблицы Минцифры)
    if "firebird" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Interbase Public License",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Firebird — открытая лицензия</small>"}

    # ============================================================

    if any(re.search(r'\\b' + re.escape(e) + r'\\b', search_clean) for e in ["elasticsearch", "kibana", "logstash"]):'''

    if anchor in content:
        content = content.replace(anchor, hardcode, 1)
        print("✅ Хардкод-проверки добавлены")
        return content, True
    print("⚠️ Якорь Elasticsearch не найден")
    return content, False


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Синтаксическая ошибка! Восстанавливаем...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    print("✅ Восстановлено")
    return False


if __name__ == "__main__":
    print("=" * 55)
    print("🔧 Хардкод-проверки компонентов Минцифры")
    print("=" * 55)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content, ok = patch(content)
    if not ok:
        sys.exit(1)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите:")
    print("   docker compose down -v && docker compose up -d --build")
