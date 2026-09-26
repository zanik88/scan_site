#!/usr/bin/env python3
"""Добавляет категории 'Мониторинг' и 'Очереди сообщений' в _detect_category."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_new_cats"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Найдём начало проверки СУБД в _detect_category и вставим ПЕРЕД ней
anchor = '''    # СУБД и хранилища (первым делом — во избежание ложных срабатываний)
    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",'''

new_block = '''    # Очереди сообщений и брокеры (ДО СУБД, чтобы Kafka/RabbitMQ попали сюда)
    mq_keys = ["kafka", "rabbitmq", "activemq", "artemis", "nats", "zeromq", "pulsar",
               "rocketmq", "ibm mq", "rabbit", "qpid", "emqx", "mosquitto"]
    if any(_has_word(n, k) for k in mq_keys) or "activemq artemis" in n:
        return "Очереди сообщений"

    # Мониторинг и логирование
    monitor_keys = ["zabbix", "prometheus", "grafana", "nagios", "datadog",
                    "new relic", "splunk", "elasticsearch", "kibana", "logstash",
                    "opensearch", "graylog", "loki", "jaeger", "zipkin", "tempo",
                    "opentelemetry", "otel", "sentry", "victoriametrics",
                    "influxdb", "telegraf", "fluentd", "fluentbit", "fluent-bit",
                    "filebeat", "metricbeat", "logstash", "vector"]
    if any(_has_word(n, k) for k in monitor_keys):
        return "Мониторинг и логирование"

    # СУБД и хранилища (после очередей и мониторинга)
    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",'''

if anchor in content:
    content = content.replace(anchor, new_block, 1)
    print("✅ Категории 'Очереди сообщений' и 'Мониторинг и логирование' добавлены")
else:
    print("⚠️ Якорь СУБД не найден. Проверьте _detect_category.")

# Также обновим существующие категории в СУБД, убрав дубли monitor
old_db = '''    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "elasticsearch", "opensearch", "kafka", "rabbitmq", "zookeeper", "influxdb",
               "sap hana", "enterprisedb", "npgsql", "db2", "teradata", "firebird", "hive",
               "tibero", "tmax"]'''

new_db = '''    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "zookeeper", "sap hana", "enterprisedb", "npgsql", "db2", "teradata",
               "firebird", "hive", "tibero", "tmax"]'''

if old_db in content:
    content = content.replace(old_db, new_db, 1)
    print("✅ Убраны дубликаты из СУБД (kafka, rabbitmq, elasticsearch, opensearch, influxdb)")

# Обновить список категорий в выпадающем фильтре
old_filter = '''            <option value="Инструменты разработки">Инструменты разработки</option>
            <option value="IDE и редакторы">IDE и редакторы</option>'''
new_filter = '''            <option value="Мониторинг и логирование">Мониторинг и логирование</option>
            <option value="Очереди сообщений">Очереди сообщений</option>
            <option value="Инструменты разработки">Инструменты разработки</option>
            <option value="IDE и редакторы">IDE и редакторы</option>'''

if old_filter in content:
    content = content.replace(old_filter, new_filter, 1)
    print("✅ Опции в фильтре обновлены")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите локально:")
    print("   docker compose down && docker compose up -d --build")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
