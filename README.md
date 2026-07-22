# Puerto Rico Hoy 🇵🇷

Daily auto-updating dashboard of Puerto Rico news, politics, and weather, styled after Google News.

**Live site:** https://djfayer.github.io/pr-daily-dashboard/

## Sources

- [El Nuevo Día](https://www.elnuevodia.com) (endi.com)
- [El Vocero](https://www.elvocero.com) (front page + Gobierno/Política section)
- [Primera Hora](https://www.primerahora.com)
- [Noticel](https://noticel.com)
- [Telemundo PR](https://www.telemundopr.com)
- Weather + alerts: [NWS San Juan](https://www.weather.gov/sju/) (api.weather.gov)

## How it works

`build.py` (Python stdlib only) fetches the RSS feeds and the NWS forecast,
deduplicates and classifies stories into sections (Portada, Política, Economía,
Deportes, Entretenimiento), and renders a static page to `site/index.html`.

A GitHub Actions workflow rebuilds and deploys the site to GitHub Pages twice a
day: 6:00 AM and 5:00 PM Puerto Rico time (AST). It can also be run manually
from the Actions tab.

## Run locally

```bash
python3 build.py
open site/index.html
```
