#!/usr/bin/env python3
"""Puerto Rico Hoy — daily news + weather dashboard generator.

Fetches RSS feeds from Puerto Rico news outlets and the NWS San Juan
forecast, then renders a static Google News-style page to site/index.html.
Stdlib only — no pip dependencies.
"""

import html
import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

UA = "PRDailyDashboard/1.0 (github.com/djfayer/pr-daily-dashboard; djfayer@gmail.com)"
AST = timezone(timedelta(hours=-4), "AST")
NOW = datetime.now(AST)
MAX_AGE = timedelta(hours=48)

FEEDS = [
    ("El Nuevo Día", "https://www.elnuevodia.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("El Vocero", "https://www.elvocero.com/search/?f=rss&t=article&l=30"),
    ("El Vocero", "https://www.elvocero.com/search/?f=rss&t=article&l=15&c=gobierno*"),
    ("Primera Hora", "https://www.primerahora.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("El Vocero", "https://www.elvocero.com/search/?f=rss&t=article&l=15&c=ley-y-orden*"),
    ("Noticel", "https://noticel.com/feed/"),
    ("Telemundo PR", "https://www.telemundopr.com/?rss=y"),
    ("Metro PR", "https://www.metro.pr/arc/outboundfeeds/rss/?outputType=xml"),
    ("WAPA TV", "https://www.wapa.tv/search/?f=rss&t=article&l=20"),
    ("NotiUno", "https://www.notiuno.com/search/?f=rss&t=article&l=20"),
    ("Radio Isla", "https://radioisla.tv/feed/"),
    ("CPI", "https://periodismoinvestigativo.com/feed/"),
    ("Es Noticia", "https://esnoticiapr.com/feed/"),
]

# PRPD crime-incidence layers (NIBRS, ~30-day lag); /0 = current year, /1 = 2012-present
CRIME_API = ("https://utility.arcgis.com/usrsvcs/servers/"
             "8abf26c4f0074515ac63c8e9c9d0c5fc/rest/services/"
             "IncidenciaCriminalPublica/FeatureServer")

FORECAST_URL = "https://api.weather.gov/gridpoints/SJU/162,132/forecast"
ALERTS_URL = "https://api.weather.gov/alerts/active?area=PR"

SECTIONS = [
    ("crimen", "Crimen y Seguridad",
     r"ley-y-orden|policiac|crimen|asesinat|homicid|tiroteo|balacera|arrest|feminicid|secuestro|violencia-domestica|violencia-de-genero|narcotrafic|fugitivo|operativo-|imputad|convicto"),
    ("politica", "Política y Gobierno",
     r"politica|gobierno|legislatur|senado|camara-de-repres|eleccion|gobernador|fortaleza|alcalde|municipio|tribunal|justicia|congreso|estadidad|junta-de-control|junta-de-supervision|fiscal"),
    ("economia", "Economía y Negocios",
     r"negocio|economia|empresa|comercio|lum[a-]|energia|impuesto|ivu|hacienda|turismo|empleo"),
    ("deportes", "Deportes", r"deporte|baloncesto|beisbol|boxeo|voleibol|futbol|olimpic|mlb|nba"),
    ("entretenimiento", "Entretenimiento y Cultura",
     r"entretenimiento|farandula|musica|cine|cultura|arte|festival|concierto|bad-bunny|television"),
]

WEATHER_EMOJI = [
    ("thunder", "⛈️"), ("storm", "⛈️"), ("rain", "🌧️"), ("shower", "🌦️"),
    ("drizzle", "🌦️"), ("partly", "⛅"), ("mostly sunny", "🌤️"),
    ("mostly clear", "🌤️"), ("cloud", "☁️"), ("sunny", "☀️"), ("clear", "🌙"),
    ("fog", "🌫️"), ("haze", "🌫️"), ("wind", "💨"),
]


BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url, timeout=30, tries=3, ua=BROWSER_UA):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(4 * (attempt + 1))
    raise last


def strip_tags(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_feed(source, url):
    items = []
    try:
        root = ElementTree.fromstring(fetch(url))
    except Exception as e:
        print(f"  ! {source}: {e}")
        return items
    ns = {"media": "http://search.yahoo.com/mrss/"}
    for it in root.iter("item"):
        title = strip_tags(it.findtext("title", ""))
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = strip_tags(it.findtext("description", ""))
        pub = None
        raw = it.findtext("pubDate") or it.findtext(
            "{http://purl.org/dc/elements/1.1/}date")
        if raw:
            try:
                pub = parsedate_to_datetime(raw.strip()).astimezone(AST)
            except Exception:
                pass
        img = None
        for tag in ("media:content", "media:thumbnail"):
            el = it.find(tag, ns)
            if el is not None and el.get("url"):
                img = el.get("url")
                break
        if img is None:
            enc = it.find("enclosure")
            if enc is not None and (enc.get("type") or "").startswith("image"):
                img = enc.get("url")
        items.append({"source": source, "title": title, "link": link,
                      "desc": desc[:220], "pub": pub, "img": img})
    print(f"  ✓ {source}: {len(items)} items ({url[:60]}…)")
    return items


def classify(item):
    hay = (item["link"] + " " + item["title"]).lower()
    for key, _, pattern in SECTIONS:
        if re.search(pattern, hay):
            return key
    return "portada"


def collect_news():
    seen, fresh = set(), []
    for i, (source, url) in enumerate(FEEDS):
        if i:
            time.sleep(2)
        for item in parse_feed(source, url):
            key = item["link"].split("?")[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            if item["pub"] and NOW - item["pub"] > MAX_AGE:
                continue
            item["section"] = classify(item)
            fresh.append(item)
    fresh.sort(key=lambda i: i["pub"] or NOW - MAX_AGE, reverse=True)
    return fresh


def get_weather():
    forecast, alerts = [], []
    try:
        data = json.loads(fetch(FORECAST_URL))
        for p in data["properties"]["periods"][:6]:
            short = p["shortForecast"]
            emoji = "🌤️"
            for kw, e in WEATHER_EMOJI:
                if kw in short.lower():
                    emoji = e
                    break
            forecast.append({
                "name": p["name"], "temp": p["temperature"],
                "unit": p["temperatureUnit"], "short": short, "emoji": emoji,
                "rain": (p.get("probabilityOfPrecipitation") or {}).get("value"),
                "wind": f"{p.get('windSpeed', '')} {p.get('windDirection', '')}".strip(),
            })
    except Exception as e:
        print(f"  ! forecast: {e}")
    try:
        data = json.loads(fetch(ALERTS_URL))
        for f in data.get("features", [])[:8]:
            p = f["properties"]
            alerts.append({"event": p.get("event", "Aviso"),
                           "headline": p.get("headline", ""),
                           "severity": p.get("severity", ""),
                           "areas": p.get("areaDesc", "")[:140]})
    except Exception as e:
        print(f"  ! alerts: {e}")
    return forecast, alerts


def get_homicides():
    """Year-to-date murder tally from the PRPD crime-incidence service,
    with a same-period prior-year comparison. Data lags ~30 days."""
    import urllib.parse
    try:
        cur = json.loads(fetch(
            f"{CRIME_API}/0/query?where=FK_delito_cometido_Tipo_I%3D1"
            "&returnCountOnly=true&f=json"))["count"]
        stats = urllib.parse.quote(
            '[{"statisticType":"max","onStatisticField":"fecha_ocurrencia",'
            '"outStatisticFieldName":"maxd"}]')
        maxd_ms = json.loads(fetch(
            f"{CRIME_API}/0/query?where=FK_delito_cometido_Tipo_I%3D1"
            f"&outStatistics={stats}&f=json"))["features"][0]["attributes"]["maxd"]
        as_of = datetime.fromtimestamp(maxd_ms / 1000, tz=timezone.utc).astimezone(AST)
        prev_where = urllib.parse.quote(
            "FK_delito_cometido_Tipo_I=1 AND "
            f"fecha_ocurrencia >= DATE '{as_of.year - 1}-01-01' AND "
            f"fecha_ocurrencia <= DATE '{as_of.year - 1}-{as_of.month:02d}-{as_of.day:02d}'")
        prev = json.loads(fetch(
            f"{CRIME_API}/1/query?where={prev_where}"
            "&returnCountOnly=true&f=json"))["count"]
        return {"year": as_of.year, "count": cur, "prev": prev, "as_of": as_of}
    except Exception as e:
        print(f"  ! homicides: {e}")
        return None


MONTHS_ES = {"January": "enero", "February": "febrero", "March": "marzo",
             "April": "abril", "May": "mayo", "June": "junio", "July": "julio",
             "August": "agosto", "September": "septiembre", "October": "octubre",
             "November": "noviembre", "December": "diciembre"}


def fecha_es(dt, fmt="%-d de %B"):
    s = dt.strftime(fmt)
    for en, es_m in MONTHS_ES.items():
        s = s.replace(en, es_m)
    return s


# ---------------------------------------------------------------- rendering

def esc(s):
    return html.escape(s or "", quote=True)


def rel_time(pub):
    if not pub:
        return ""
    mins = int((NOW - pub).total_seconds() // 60)
    if mins < 60:
        return f"hace {max(mins, 1)} min"
    hours = mins // 60
    if hours < 24:
        return f"hace {hours} h"
    return f"hace {hours // 24} d"


def article_html(item, lead=False):
    img = ""
    if item["img"]:
        img = (f'<img class="thumb" src="{esc(item["img"])}" alt="" '
               f'loading="lazy" onerror="this.style.display=\'none\'">')
    desc = f'<p class="desc">{esc(item["desc"])}</p>' if lead and item["desc"] else ""
    return f'''<article class="story{" lead" if lead else ""}">
  <div class="story-text">
    <span class="src">{esc(item["source"])}</span>
    <h3><a href="{esc(item["link"])}" target="_blank" rel="noopener">{esc(item["title"])}</a></h3>
    {desc}<time>{rel_time(item["pub"])}</time>
  </div>{img}
</article>'''


def section_html(sec_id, label, items, lead_count=1, limit=8):
    if not items:
        return ""
    parts = [article_html(it, lead=(i < lead_count)) for i, it in enumerate(items[:limit])]
    return f'''<section class="panel" id="{sec_id}">
<h2>{esc(label)}</h2>
{"".join(parts)}
</section>'''


SEVERITY_ES = {"Extreme": "Extremo", "Severe": "Severo", "Moderate": "Moderado", "Minor": "Menor"}


def render(items, forecast, alerts, homicides=None):
    by_sec = {}
    for it in items:
        by_sec.setdefault(it["section"], []).append(it)

    alert_html = ""
    if alerts:
        rows = "".join(
            f'<div class="alert"><strong>⚠️ {esc(a["event"])}'
            f'{" · " + esc(SEVERITY_ES.get(a["severity"], a["severity"])) if a["severity"] else ""}</strong>'
            f'<span>{esc(a["headline"] or a["areas"])}</span></div>'
            for a in alerts)
        alert_html = f'<div class="alerts">{rows}</div>'

    fc_rows = "".join(
        f'''<div class="fc-row">
  <span class="fc-name">{esc(p["name"])}</span>
  <span class="fc-emoji">{p["emoji"]}</span>
  <span class="fc-short">{esc(p["short"])}{f' · lluvia {p["rain"]}%' if p["rain"] else ""}</span>
  <span class="fc-temp">{p["temp"]}°{esc(p["unit"])}</span>
</div>''' for p in forecast)

    today = forecast[0] if forecast else None
    hero = ""
    if today:
        hero = (f'<div class="wx-now"><span class="wx-big">{today["emoji"]} '
                f'{today["temp"]}°{esc(today["unit"])}</span>'
                f'<span class="wx-cond">San Juan · {esc(today["short"])}</span></div>')

    portada = by_sec.get("portada", [])
    nav_links = "".join(
        f'<a href="#{sid}">{label.split(" y ")[0]}</a>'
        for sid, label, _ in SECTIONS if by_sec.get(sid))

    columns = "".join(
        section_html(sid, label, by_sec.get(sid, []))
        for sid, label, _ in SECTIONS)

    stamp = fecha_es(NOW, "%-d de %B de %Y, %-I:%M %p AST")

    tally_html = ""
    if homicides:
        diff = homicides["count"] - homicides["prev"]
        pct = (diff / homicides["prev"] * 100) if homicides["prev"] else 0
        arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "•")
        cls = "up" if diff > 0 else ("down" if diff < 0 else "")
        tally_html = f'''<section class="panel tally" id="asesinatos">
      <h2>Asesinatos en {homicides["year"]}</h2>
      <div class="tally-num">{homicides["count"]}</div>
      <div class="tally-cmp {cls}">{arrow} {abs(diff)} ({pct:+.1f}%) vs. mismo periodo de {homicides["year"] - 1} ({homicides["prev"]})</div>
      <time>Datos: Policía de Puerto Rico (NIBRS), hasta el {esc(fecha_es(homicides["as_of"]))} — se publican con ~30 días de rezago y no son estadísticas oficiales certificadas.</time>
    </section>'''

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Puerto Rico Hoy — Noticias y Clima</title>
<meta name="description" content="Resumen diario de noticias, política y clima de Puerto Rico. Fuentes: El Nuevo Día, El Vocero, Primera Hora, Noticel, Telemundo PR y NWS San Juan.">
<meta name="robots" content="noindex, nofollow, noarchive">
<style>
:root {{
  --bg:#ffffff; --surface:#ffffff; --panel:#fff; --border:#dadce0;
  --text:#202124; --muted:#5f6368; --link:#1a0dab; --accent:#1a73e8;
  --alert-bg:#fef7e0; --alert-border:#f9ab00; --chip:#f1f3f4;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#202124; --surface:#292a2d; --panel:#292a2d; --border:#3c4043;
    --text:#e8eaed; --muted:#9aa0a6; --link:#8ab4f8; --accent:#8ab4f8;
    --alert-bg:#3a2f14; --alert-border:#f9ab00; --chip:#3c4043;
  }}
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text);
  font:15px/1.5 "Google Sans",Roboto,-apple-system,"Segoe UI",Arial,sans-serif; }}
a {{ color:inherit; text-decoration:none; }}
header {{ position:sticky; top:0; z-index:10; background:var(--bg);
  border-bottom:1px solid var(--border); }}
.bar {{ max-width:1160px; margin:0 auto; padding:12px 20px;
  display:flex; align-items:center; gap:16px; flex-wrap:wrap; }}
.logo {{ font-size:22px; font-weight:400; letter-spacing:-.3px; }}
.logo b {{ color:var(--accent); font-weight:600; }}
.logo .flag {{ margin-right:8px; }}
.datebox {{ color:var(--muted); font-size:13px; }}
nav {{ margin-left:auto; display:flex; gap:4px; flex-wrap:wrap; }}
nav a {{ padding:6px 14px; border-radius:16px; font-size:14px; color:var(--muted); }}
nav a:hover {{ background:var(--chip); color:var(--text); }}
main {{ max-width:1160px; margin:0 auto; padding:20px; }}
.layout {{ display:grid; grid-template-columns:minmax(0,2fr) minmax(280px,1fr); gap:20px; }}
@media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; }} }}
.panel {{ background:var(--panel); border:1px solid var(--border);
  border-radius:16px; padding:20px 24px; margin-bottom:20px; }}
.panel h2 {{ font-size:20px; font-weight:500; margin-bottom:8px; }}
.story {{ display:flex; gap:16px; justify-content:space-between;
  padding:14px 0; border-top:1px solid var(--border); }}
.story:first-of-type {{ border-top:none; }}
.story-text {{ min-width:0; flex:1; }}
.story h3 {{ font-size:16px; font-weight:500; line-height:1.35; }}
.story.lead h3 {{ font-size:20px; }}
.story h3 a:hover {{ text-decoration:underline; }}
.story h3 a:visited {{ color:var(--muted); }}
.src {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }}
.desc {{ color:var(--muted); font-size:14px; margin-top:6px;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
time {{ display:block; font-size:12px; color:var(--muted); margin-top:6px; }}
.thumb {{ width:112px; height:112px; object-fit:cover; border-radius:12px; flex-shrink:0; }}
.story.lead .thumb {{ width:168px; height:120px; }}
@media (max-width:520px) {{ .thumb, .story.lead .thumb {{ width:84px; height:84px; }} }}
.alerts {{ margin-bottom:20px; }}
.alert {{ background:var(--alert-bg); border:1px solid var(--alert-border);
  border-radius:12px; padding:12px 16px; margin-bottom:8px; font-size:14px; }}
.alert strong {{ display:block; margin-bottom:2px; }}
.alert span {{ color:var(--muted); }}
.wx-now {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:12px; }}
.wx-big {{ font-size:32px; font-weight:500; }}
.wx-cond {{ color:var(--muted); font-size:14px; }}
.fc-row {{ display:grid; grid-template-columns:1fr auto; gap:2px 10px;
  padding:10px 0; border-top:1px solid var(--border); font-size:14px; }}
.fc-name {{ font-weight:500; }}
.fc-emoji {{ grid-row:span 2; align-self:center; font-size:22px; }}
.fc-short {{ color:var(--muted); font-size:13px; grid-column:1; }}
.fc-temp {{ grid-column:2; grid-row:1; font-weight:500; }}
footer {{ max-width:1160px; margin:0 auto; padding:24px 20px 40px;
  color:var(--muted); font-size:13px; border-top:1px solid var(--border); }}
footer a {{ color:var(--accent); }}
.sticky-col {{ position:sticky; top:76px; align-self:start; }}
.tally h2 {{ font-size:16px; color:var(--muted); font-weight:500; }}
.tally-num {{ font-size:44px; font-weight:600; line-height:1.1; color:#d93025; }}
@media (prefers-color-scheme: dark) {{ .tally-num {{ color:#f28b82; }} }}
.tally-cmp {{ font-size:13px; margin-top:4px; }}
.tally-cmp.up {{ color:#d93025; }} .tally-cmp.down {{ color:#188038; }}
@media (prefers-color-scheme: dark) {{
  .tally-cmp.up {{ color:#f28b82; }} .tally-cmp.down {{ color:#81c995; }} }}
.tally time {{ margin-top:8px; }}
@media (max-width:900px) {{ .sticky-col {{ position:static; }} }}
</style>
</head>
<body>
<header>
  <div class="bar">
    <span class="logo"><span class="flag">🇵🇷</span>Puerto Rico <b>Hoy</b></span>
    <span class="datebox">Actualizado: {esc(stamp)}</span>
    <nav>
      <a href="#portada">Portada</a>{nav_links}<a href="#clima">Clima</a>
    </nav>
  </div>
</header>
<main>
{alert_html}
<div class="layout">
  <div>
    {section_html("portada", "Titulares", portada, lead_count=2, limit=12)}
    {columns}
  </div>
  <div class="sticky-col">
    {tally_html}
    <section class="panel" id="clima">
      <h2>Clima</h2>
      {hero}
      {fc_rows}
      <time>Fuente: Servicio Nacional de Meteorología (NWS San Juan)</time>
    </section>
  </div>
</div>
</main>
<footer>
  <p>Resumen generado automáticamente cada día. Fuentes:
  <a href="https://www.elnuevodia.com" target="_blank" rel="noopener">El Nuevo Día</a> ·
  <a href="https://www.elvocero.com" target="_blank" rel="noopener">El Vocero</a> ·
  <a href="https://www.primerahora.com" target="_blank" rel="noopener">Primera Hora</a> ·
  <a href="https://www.noticel.com" target="_blank" rel="noopener">Noticel</a> ·
  <a href="https://www.telemundopr.com" target="_blank" rel="noopener">Telemundo PR</a> ·
  <a href="https://www.metro.pr" target="_blank" rel="noopener">Metro PR</a> ·
  <a href="https://www.wapa.tv" target="_blank" rel="noopener">WAPA TV</a> ·
  <a href="https://www.notiuno.com" target="_blank" rel="noopener">NotiUno</a> ·
  <a href="https://radioisla.tv" target="_blank" rel="noopener">Radio Isla</a> ·
  <a href="https://periodismoinvestigativo.com" target="_blank" rel="noopener">Centro de Periodismo Investigativo</a> ·
  <a href="https://esnoticiapr.com" target="_blank" rel="noopener">Es Noticia</a> ·
  <a href="https://www.weather.gov/sju/" target="_blank" rel="noopener">NWS San Juan</a> ·
  <a href="https://incidenciacriminal.policia.pr.gov/publica/" target="_blank" rel="noopener">Policía de PR — Incidencia Criminal</a>.
  Los titulares enlazan a los artículos originales de cada medio.</p>
</footer>
</body>
</html>'''


def main():
    print("Fetching news…")
    items = collect_news()
    print(f"Total fresh items: {len(items)}")
    print("Fetching weather…")
    forecast, alerts = get_weather()
    print("Fetching homicide tally…")
    homicides = get_homicides()
    if homicides:
        print(f"  ✓ {homicides['count']} in {homicides['year']} "
              f"(prev year same period: {homicides['prev']})")
    out = Path(__file__).parent / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(items, forecast, alerts, homicides), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
