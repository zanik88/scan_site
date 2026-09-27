#!/usr/bin/env python3
"""Добавляет ETA (оценку времени) в прогресс-бар."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_eta"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Заменяем JS функцию check() в audit_progress_page
old_js = '''    <script>
    let cancelled = false;

    async function cancelAudit(){{
        if(cancelled) return;
        if(!confirm('Отменить проверку? Все результаты будут удалены.')) return;
        cancelled = true;
        document.getElementById('cancelBtn').disabled = true;
        document.getElementById('cancelBtn').innerText = '⏳ Отмена...';
        document.getElementById('ct').style.display = 'block';
        try {{
            await fetch('/audit/{report_id}/cancel', {{method:'POST'}});
        }} catch(e) {{ console.error(e); }}
        setTimeout(() => {{ window.location.href = '/'; }}, 1500);
    }}

    async function check(){{
        if(cancelled) return;
        try{{
            const r = await fetch('/audit/{report_id}/status');
            const d = await r.json();
            if(d.total>0){{
                const pct = Math.round((d.processed/d.total)*100);
                document.getElementById('pf').style.width = pct + '%';
                document.getElementById('pt').innerText = `Анализ: ${{d.processed}}/${{d.total}} (${{pct}}%)`;
            }}
            if(d.status==='completed') window.location.href='/audit/{report_id}/result';
            else if(d.status==='failed'){{alert('Ошибка анализа');window.location.href='/';}}
            else if(d.status==='cancelled' || d.status==='deleted'){{window.location.href='/';}}
            else setTimeout(check,1000);
        }}catch(e){{setTimeout(check,2000);}}
    }} check();
    </script>'''

new_js = '''    <script>
    let cancelled = false;
    let startTime = null;
    let lastProcessed = 0;
    let eta = null;

    function formatTime(sec){{
        if(sec < 60) return Math.round(sec) + ' сек';
        const m = Math.floor(sec / 60);
        const s = Math.round(sec % 60);
        return m + ' мин ' + s + ' сек';
    }}

    function computeEta(processed, total){{
        if(!startTime || processed < 3) return null;
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = processed / elapsed;  // компонентов/сек
        const remaining = total - processed;
        if(speed <= 0) return null;
        return remaining / speed;
    }}

    async function cancelAudit(){{
        if(cancelled) return;
        if(!confirm('Отменить проверку? Все результаты будут удалены.')) return;
        cancelled = true;
        document.getElementById('cancelBtn').disabled = true;
        document.getElementById('cancelBtn').innerText = '⏳ Отмена...';
        document.getElementById('ct').style.display = 'block';
        try {{
            await fetch('/audit/{report_id}/cancel', {{method:'POST'}});
        }} catch(e) {{ console.error(e); }}
        setTimeout(() => {{ window.location.href = '/'; }}, 1500);
    }}

    async function check(){{
        if(cancelled) return;
        try{{
            const r = await fetch('/audit/{report_id}/status');
            const d = await r.json();
            if(d.total>0){{
                if(startTime === null) startTime = Date.now();
                const pct = Math.round((d.processed/d.total)*100);
                document.getElementById('pf').style.width = pct + '%';

                // Пересчитываем ETA каждые 5 компонентов
                if(d.processed > lastProcessed){{
                    eta = computeEta(d.processed, d.total);
                    lastProcessed = d.processed;
                }}

                let text = `Анализ: ${{d.processed}}/${{d.total}} (${{pct}}%)`;
                if(eta !== null && d.processed < d.total){{
                    text += ` — осталось ~${{formatTime(eta)}}`;
                }}
                document.getElementById('pt').innerText = text;
            }}
            if(d.status==='completed') window.location.href='/audit/{report_id}/result';
            else if(d.status==='failed'){{alert('Ошибка анализа');window.location.href='/';}}
            else if(d.status==='cancelled' || d.status==='deleted'){{window.location.href='/';}}
            else setTimeout(check,1000);
        }}catch(e){{setTimeout(check,2000);}}
    }} check();
    </script>'''

if old_js in content:
    content = content.replace(old_js, new_js, 1)
    print("✅ ETA добавлен в прогресс-бар")
else:
    print("❌ Старый JS не найден. Возможно, структура отличается.")

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
