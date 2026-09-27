#!/usr/bin/env python3
"""
Патч v6: Elasticsearch / OpenSearch / Kibana / Logstash — из мониторинга в СУБД.
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_category_v6"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Убрать elasticsearch/opensearch/kibana/logstash/graylog из monitor_keys
# ============================================================
old_monitor = '''    monitor_keys = ["zabbix", "prometheus", "grafana", "nagios", "datadog",
                    "new relic", "splunk", "elasticsearch", "kibana", "logstash",
                    "opensearch", "graylog", "loki", "jaeger", "zipkin", "tempo",
                    "opentelemetry", "otel", "sentry", "victoriametrics",
                    "influxdb", "telegraf", "fluentd", "fluentbit", "fluent-bit",
                    "filebeat", "metricbeat", "logstash", "vector"]'''

new_monitor = '''    # Elasticsearch/OpenSearch/Kibana/Logstash — это СУБД/поиск, не мониторинг
    monitor_keys = ["zabbix", "prometheus", "grafana", "nagios", "datadog",
                    "new relic", "splunk", "loki", "jaeger", "zipkin", "tempo",
                    "opentelemetry", "otel", "sentry", "victoriametrics",
                    "influxdb", "telegraf", "fluentd", "fluentbit", "fluent-bit",
                    "filebeat", "metricbeat", "vector"]'''

if old_monitor in content:
    content = content.replace(old_monitor, new_monitor, 1)
    patched.append("Убраны elasticsearch/opensearch/kibana/logstash/graylog из мониторинга")
else:
    print("⚠️ Якорь monitor_keys не найден")

# ============================================================
# 2. Добавить их в db_keys
# ============================================================
old_db = '''    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "zookeeper", "sap hana", "enterprisedb", "npgsql", "db2", "teradata",
               "firebird", "hive", "tibero", "tmax"]'''

new_db = '''    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "zookeeper", "sap hana", "enterprisedb", "npgsql", "db2", "teradata",
               "firebird", "hive", "tibero", "tmax",
               "elasticsearch", "opensearch", "kibana", "logstash", "graylog"]'''

if old_db in content:
    content = content.replace(old_db, new_db, 1)
    patched.append("Elasticsearch/OpenSearch/Kibana/Logstash добавлены в СУБД")
else:
    print("⚠️ Якорь db_keys не найден")

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
