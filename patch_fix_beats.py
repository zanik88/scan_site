#!/usr/bin/env python3
"""Добавляет Filebeat, Fluent Bit, Jaeger + чинит .NET SDK с версией."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_beats"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Добавить недостающие правила после ".net sdk"
old1 = '''    ".net sdk": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET SDK."},'''
new1 = '''    ".net sdk": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET SDK."},
    "dotnet sdk": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET SDK."},
    "elastic beats": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Elastic Beats — Elastic License. Замена: Fluent Bit."},
    "filebeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Filebeat (Elastic) — Замена: Fluent Bit."},
    "metricbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Metricbeat (Elastic) — Замена: Prometheus."},
    "packetbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Packetbeat (Elastic)."},
    "heartbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Heartbeat (Elastic)."},
    "auditbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Auditbeat (Elastic)."},
    "fluent bit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluent Bit."},
    "fluentbit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluent Bit."},
    "fluent-bit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluent Bit."},
    "fluentd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluentd."},
    "jaeger": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jaeger — трассировка."},
    "zipkin": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Zipkin."},
    "tempo": {"license": "AGPL-3.0", "status": "⚠️ Требует внимания", "recommendation": "Grafana Tempo — AGPL."},'''

if old1 in content:
    content = content.replace(old1, new1, 1)
    print("✅ Добавлены правила: Filebeat, Fluent Bit, Jaeger, Beats")
else:
    print("⚠️ Якорь .net sdk не найден")

# 2. Хардкод-проверка в fetch_package_info_with_version — ищем .NET SDK без точного совпадения
anchor2 = '''    # Oracle MySQL — различаем Community (разрешено) и Commercial (запрещено)'''
new2 = '''    # .NET SDK (с версией в названии)
    if ".net sdk" in search_clean or "dotnet sdk" in search_clean or search_clean.startswith(".net "):
        return {"name": package_name, "version": table_version,
                "license": "MIT",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 .NET SDK — MIT</small>"}

    # Elastic Beats (Filebeat, Metricbeat и др.) — запрещены
    if "filebeat" in search_clean or "metricbeat" in search_clean or "packetbeat" in search_clean or "auditbeat" in search_clean or "elastic beats" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Elastic License 2.0",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Elastic License. Замена: Fluent Bit / OpenSearch</small>"}

    # Fluent Bit / Fluentd
    if "fluent bit" in search_clean or "fluentbit" in search_clean or "fluent-bit" in search_clean or "fluentd" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Apache-2.0",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Fluent Bit / Fluentd — Apache-2.0</small>"}

    # Jaeger
    if "jaeger" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Apache-2.0",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Jaeger — Apache-2.0</small>"}

    # Oracle MySQL — различаем Community (разрешено) и Commercial (запрещено)'''

if anchor2 in content and ".net sdk\" in search_clean" not in content:
    content = content.replace(anchor2, new2, 1)
    print("✅ Хардкод-проверки добавлены для .NET SDK, Beats, Fluent Bit, Jaeger")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.2.1")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
