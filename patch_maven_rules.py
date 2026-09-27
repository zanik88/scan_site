#!/usr/bin/env python3
"""Добавляет Maven namespace-правила в DEFAULT_RULES (якорь: pulumi)."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_maven_rules"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Правильный якорь — последняя запись перед }
anchor = '''    "pulumi": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Pulumi — Apache-2.0."},
}'''

new_block = '''    "pulumi": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Pulumi — Apache-2.0."},

    # ============ Maven namespace-правила (Java) ============
    # Spring
    "org.springframework": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Framework."},
    "org.springframework.boot": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Boot."},
    "org.springframework.security": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Security."},
    "org.springframework.cloud": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Cloud."},
    "org.springframework.ai": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring AI."},
    "org.springframework.kafka": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Kafka."},
    "org.springframework.retry": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Retry."},

    # Apache
    "org.apache.commons": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Commons."},
    "org.apache.tika": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Tika."},
    "org.apache.poi": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache POI."},
    "org.apache.pdfbox": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache PDFBox."},
    "org.apache.httpcomponents": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache HttpComponents."},
    "org.apache.kafka": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Kafka."},
    "org.apache.logging": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Logging."},
    "org.apache.opennlp": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache OpenNLP."},
    "org.apache.james": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache James."},
    "org.apache.xmlbeans": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache XMLBeans."},
    "org.apache.tomcat": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Tomcat."},
    "org.apache.antlr": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "ANTLR."},
    "org.apache.zookeeper": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ZooKeeper."},

    # Google
    "com.google.guava": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Google Guava."},
    "com.google.code.gson": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Gson."},
    "com.google.code.findbugs": {"license": "LGPL-3.0", "status": "✅ Разрешено", "recommendation": "FindBugs."},
    "com.google.protobuf": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Protobuf."},
    "com.google.errorprone": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Error Prone."},
    "com.google.api.grpc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "gRPC-Google."},
    "com.google.android": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Google Annotations."},
    "com.google.j2objc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "J2ObjC."},
    "com.googlecode.plist": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "dd-plist."},

    # Jackson
    "com.fasterxml.jackson": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jackson."},
    "com.fasterxml": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "FasterXML."},

    # Bouncy Castle / Netty / gRPC
    "org.bouncycastle": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Bouncy Castle."},
    "io.netty": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Netty."},
    "io.grpc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "gRPC."},

    # Observability
    "io.opentelemetry": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenTelemetry."},
    "io.opentelemetry.semconv": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OTel SemConv."},
    "io.micrometer": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Micrometer."},
    "io.prometheus": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Prometheus Client."},
    "io.perfmark": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "PerfMark."},
    "io.projectreactor": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Project Reactor."},
    "io.qdrant": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Qdrant client."},
    "io.swagger.core.v3": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Swagger Core."},

    # Jakarta
    "jakarta.activation": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta Activation."},
    "jakarta.annotation": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta Annotations."},
    "jakarta.validation": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta Validation."},
    "jakarta.xml.bind": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta XML Bind."},
    "javax.validation": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "javax.validation."},

    # Test
    "org.junit": {"license": "EPL-2.0", "status": "✅ Разрешено", "recommendation": "JUnit."},
    "org.junit.jupiter": {"license": "EPL-2.0", "status": "✅ Разрешено", "recommendation": "JUnit 5."},
    "org.junit.platform": {"license": "EPL-2.0", "status": "✅ Разрешено", "recommendation": "JUnit Platform."},
    "junit": {"license": "EPL-1.0", "status": "✅ Разрешено", "recommendation": "JUnit 4."},
    "org.mockito": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Mockito."},
    "org.assertj": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "AssertJ."},
    "org.hamcrest": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Hamcrest."},
    "org.awaitility": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Awaitility."},
    "org.apiguardian": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apiguardian."},
    "org.opentest4j": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenTest4J."},
    "org.xmlunit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "XMLUnit."},
    "org.skyscreamer": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JSONassert."},
    "org.testcontainers": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Testcontainers."},

    # Logging
    "ch.qos.logback": {"license": "EPL-1.0 / LGPL-2.1", "status": "✅ Разрешено", "recommendation": "Logback."},
    "org.slf4j": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "SLF4J."},
    "net.logstash.logback": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Logstash Encoder."},

    # Nimbus / Square
    "com.nimbusds": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Nimbus JOSE+JWT."},
    "com.squareup.okhttp3": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OkHttp."},
    "com.squareup.okio": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Okio."},

    # Котлин
    "org.jetbrains": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JetBrains Annotations."},
    "org.jetbrains.kotlin": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Kotlin stdlib."},

    # Прочее
    "com.github.ben-manes.caffeine": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Caffeine cache."},
    "com.github.victools": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "JSON Schema Generator."},
    "com.github.docker-java": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Docker Java client."},
    "com.github.junrar": {"license": "UnRAR License", "status": "⚠️ Требует внимания", "recommendation": "junrar — нестандартная лицензия."},
    "com.github.luben": {"license": "BSD-2-Clause", "status": "✅ Разрешено", "recommendation": "Zstd-JNI."},
    "com.github.stephenc.jcip": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JCIP Annotations."},
    "com.github.jai-imageio": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "JAI ImageIO."},
    "com.healthmarketscience.jackcess": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jackcess."},
    "com.ethlo.time": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ITU library."},
    "com.zaxxer": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SparseBitSet."},
    "com.rometools": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ROME."},
    "com.pff": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "java-libpst."},
    "com.jayway.jsonpath": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JsonPath."},
    "com.knuddels": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jtokkit."},
    "com.networknt": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JSON Schema Validator."},
    "com.drewnoakes": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "metadata-extractor."},
    "com.adobe.xmp": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "XMPCore."},
    "com.epam": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Parso."},
    "com.sun.istack": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "istack-commons."},
    "com.github.albfernandez": {"license": "LGPL-2.1 / MPL-1.1", "status": "✅ Разрешено", "recommendation": "juniversalchardet."},
    "com.vaadin.external.google": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Android JSON for tests."},
    "org.codelibs": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jhighlight."},
    "org.eclipse.angus": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Angus Activation."},
    "org.glassfish.jaxb": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Glassfish JAXB."},
    "org.jboss.logging": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JBoss Logging."},
    "org.hibernate.validator": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Hibernate Validator."},
    "org.gagravarr": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Vorbis-Java."},
    "org.json": {"license": "JSON License (MIT-like)", "status": "✅ Разрешено", "recommendation": "JSON-java."},
    "org.jsoup": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "jsoup."},
    "org.jspecify": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JSpecify."},
    "org.jdom": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JDOM2."},
    "org.latencyutils": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "LatencyUtils."},
    "org.objenesis": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Objenesis."},
    "org.ow2.asm": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "ASM."},
    "org.projectlombok": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Lombok."},
    "org.reactivestreams": {"license": "MIT-0", "status": "✅ Разрешено", "recommendation": "Reactive Streams."},
    "org.rnorth.duct-tape": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Duct Tape."},
    "org.hdrhistogram": {"license": "BSD-2-Clause", "status": "✅ Разрешено", "recommendation": "HdrHistogram."},
    "org.netpreserve": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jwarc."},
    "org.tallison": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jmatio."},
    "org.tukaani": {"license": "Public Domain", "status": "✅ Разрешено", "recommendation": "XZ for Java."},
    "org.brotli": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Brotli decoder."},
    "org.yaml": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SnakeYAML."},
    "org.webjars": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "WebJars."},
    "org.springdoc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SpringDoc OpenAPI."},
    "info.picocli": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "picocli."},
    "io.github.openfeign": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenFeign."},
    "net.bytebuddy": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Byte Buddy."},
    "net.java.dev.jna": {"license": "LGPL-2.1 / Apache-2.0", "status": "✅ Разрешено", "recommendation": "JNA."},
    "net.minidev": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "json-smart."},
    "software.amazon.awssdk": {"license": "Apache-2.0", "status": "⚠️ Требует внимания", "recommendation": "AWS SDK. Интеграция опциональна."},
    "dev.langchain4j": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "LangChain4j."},
    "commons-codec": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons Codec."},
    "commons-io": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons IO."},
    "commons-logging": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons Logging."},
    "commons-fileupload": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons FileUpload."},
    "aopalliance": {"license": "Public Domain", "status": "✅ Разрешено", "recommendation": "AOP Alliance."},
    "at.yawk.lz4": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "lz4-java."},
    "org.antlr": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "ANTLR runtime."},
}'''

if anchor in content:
    content = content.replace(anchor, new_block, 1)
    print("✅ Maven namespace-правила добавлены (110+ правил)")
else:
    print("❌ Якорь 'pulumi' не найден")
    sys.exit(1)

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Пересоберите локально:")
    print("   docker compose down && docker compose build --no-cache && docker compose up -d")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
