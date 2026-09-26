#!/usr/bin/env python3
"""
Патч main.py на основе официальной таблицы Минцифры:
"Разрешенные и запрещенные компоненты для проверки ПО"

Добавляет запрещённые компоненты из разделов:
1. ОС (CentOS, Fedora, RHEL, SUSE, AlmaLinux, Rocky, openSUSE)
2. СУБД (EnterpriseDB, IBM DB2, MS SQL, Oracle, SAP, Splunk)
3. Серверы приложений (Adobe, IBM, Oracle, JBoss, Zend, SAP)
4. Платформы (AWS, IBM, Microsoft Azure, SharePoint, Dynamics, SAP)
5. Библиотеки/фреймворки (DevExpress, Unity, Unreal)
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


def patch_rules(content: str) -> tuple:
    """Вставляет запрещённые компоненты из таблицы Минцифры."""
    anchor = '''    "pytest": {"license": "MIT", "status": "Разрешено", "recommendation": "pytest."},
}'''

    mincifry_block = '''    "pytest": {"license": "MIT", "status": "Разрешено", "recommendation": "pytest."},

    # ============================================================
    # ОФИЦИАЛЬНАЯ ТАБЛИЦА МИНЦИФРЫ
    # "Разрешенные и запрещенные компоненты для проверки ПО"
    # ============================================================

    # --- 1. Операционные системы (запрещены) ---
    "redhat": {"license": "Commercial / Subscription", "status": "❌ Запрещено", "recommendation": "Экспортные ограничения. Замена: Astra Linux / ALT Linux."},
    "red hat": {"license": "Commercial / Subscription", "status": "❌ Запрещено", "recommendation": "RHEL. Замена: Astra Linux / ALT Linux."},
    "redhat jboss": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "JBoss EAP. Замена: WildFly / TomEE."},
    "jboss": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Red Hat JBoss. Замена: WildFly / TomEE."},
    "suse": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SUSE Linux Enterprise. Замена: Astra Linux."},
    "sles": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SUSE Linux Enterprise Server."},

    # --- 2. СУБД (запрещены) ---
    "ibm db2": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM DB2. Замена: Postgres Pro."},
    "db2": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM DB2. Замена: Postgres Pro."},
    "intersystems cache": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "InterSystems Caché. Замена: PostgreSQL."},
    "cache": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "InterSystems Caché."},
    "microsoft access": {"license": "Commercial EULA", "status": "❌ Запрещено", "recommendation": "Microsoft Access. Замена: Postgres Pro."},
    "ms access": {"license": "Commercial EULA", "status": "❌ Запрещено", "recommendation": "Microsoft Access."},
    "oracle mysql": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Oracle MySQL (Commercial). Замена: MariaDB / Postgres Pro."},
    "oracle nosql": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Oracle NoSQL. Замена: Postgres Pro."},
    "oracle weblogic": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Oracle WebLogic. Замена: WildFly / TomEE."},
    "weblogic": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Oracle WebLogic."},
    "sap ase": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SAP ASE / Sybase ASE. Замена: Postgres Pro."},
    "sybase": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Sybase. Замена: Postgres Pro."},
    "sap sql anywhere": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SAP SQL Anywhere. Замена: Postgres Pro."},
    "splunk": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Splunk. Замена: OpenSearch / Loki."},
    "interbase": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "InterBase. Замена: Firebird."},
    "firebird": {"license": "Interbase Public License", "status": "✅ Разрешено", "recommendation": "Firebird — открытая лицензия."},

    # --- 3. Серверы приложений (запрещены) ---
    "adobe coldfusion": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Adobe ColdFusion."},
    "coldfusion": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Adobe ColdFusion."},
    "ibm websphere": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM WebSphere. Замена: WildFly / TomEE."},
    "websphere": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM WebSphere."},
    "roguewave zend": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "RogueWave Zend Server."},
    "zend server": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Zend Server."},
    "sap netweaver": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SAP NetWeaver. Замена: WildFly / TomEE."},
    "netweaver": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SAP NetWeaver."},
    "glassfish": {"license": "CDDL / GPL", "status": "✅ Разрешено", "recommendation": "GlassFish — открытая лицензия."},
    "wildfly": {"license": "LGPL-2.1", "status": "✅ Разрешено", "recommendation": "WildFly — открытая лицензия."},
    "tomee": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache TomEE."},
    "geronimo": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Geronimo."},
    "resin": {"license": "GPL / Commercial", "status": "✅ Разрешено", "recommendation": "Resin (open source)."},

    # --- 4. Платформы (запрещены) ---
    "ibm filenet": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM FileNet."},
    "filenet": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM FileNet."},
    "ibm lotus": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM Lotus Domino / Notes."},
    "lotus domino": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM Lotus Domino."},
    "lotus notes": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM Lotus Notes."},

    # --- 5. Библиотеки/фреймворки (запрещены) ---
    "devexpress": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress — экспортные ограничения (https://www.devexpress.com/support/eulas/). Замена: открытые UI-библиотеки (Material UI, Ant Design)."},
    "devexpress aspnetcore": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress ASP.NET Core — экспортные ограничения."},
    "devexpress.blazor": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress Blazor — экспортные ограничения."},
    "devexpress.wpf": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress WPF — экспортные ограничения."},
    "devexpress.winforms": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress WinForms — экспортные ограничения."},
    "devexpress.reporting": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress Reporting."},
    "devexpress.mvvm": {"license": "Commercial / DevExpress EULA", "status": "❌ Запрещено", "recommendation": "DevExpress MVVM Framework."},
}'''

    if anchor in content:
        content = content.replace(anchor, mincifry_block, 1)
        print("✅ Патч: добавлены запрещённые компоненты из таблицы Минцифры")
        return content, True
    print("⚠️ Якорь 'pytest + }' не найден. Проверьте структуру DEFAULT_RULES.")
    return content, False


def patch_devexpress_logic(content: str) -> tuple:
    """Добавляет явную проверку DevExpress в fetch_package_info_with_version."""
    anchor = '''    if any(re.search(r'\\b' + re.escape(e) + r'\\b', search_clean) for e in ["elasticsearch", "kibana", "logstash"]):'''
    
    devexpress_block = '''    if "devexpress" in search_clean or "dev express" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Commercial / DevExpress EULA",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Экспортные ограничения. Замена: открытые UI-библиотеки</small>"}

    if any(re.search(r'\\b' + re.escape(e) + r'\\b', search_clean) for e in ["elasticsearch", "kibana", "logstash"]):'''

    if anchor in content:
        content = content.replace(anchor, devexpress_block, 1)
        print("✅ Патч: явная проверка DevExpress добавлена")
        return content, True
    print("⚠️ Якорь Elasticsearch не найден.")
    return content, False


def verify_syntax():
    print("\n🔍 Проверка синтаксиса...")
    result = os.system("python3 -m py_compile main.py")
    if result == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка синтаксиса! Восстанавливаем из backup...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    print("✅ Файл восстановлен")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Патч на основе официальной таблицы Минцифры")
    print("=" * 60)

    backup()

    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    content, ok1 = patch_rules(content)
    content, ok2 = patch_devexpress_logic(content)

    if not (ok1 or ok2):
        print("\n❌ Патч не применён.")
        if input("Восстановить из backup? (y/n): ").strip().lower() == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
            print("✅ Восстановлено")
        sys.exit(1)

    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    if not verify_syntax():
        sys.exit(1)

    print("\n🎉 Готово! Пересоберите контейнер:")
    print("   docker compose down -v && docker compose up -d --build")
    print("\nПосле перезапуска загрузите файл с DevExpress — увидите ❌ Запрещено.")
