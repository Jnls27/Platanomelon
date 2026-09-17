# Dashboard Platano Melón (Meta Ads)

Dashboard estático que se actualiza solo cada día a las 7:00 (hora España)
vía GitHub Actions, sin ninguna acción manual una vez configurado — mismo
esquema que el dashboard de FFJ.

## Configuración inicial (una sola vez)

1. **Sube todo el contenido de esta carpeta tal cual** al repositorio
   `Jnls27/Platanomelon` (Add file → Upload files, o arrastrando la carpeta
   entera).

2. **Añade el secret `WINDSOR_API_KEY`**:
   - Ve a `Settings` → `Secrets and variables` → `Actions` → `New repository secret`.
   - Nombre: `WINDSOR_API_KEY`. Valor: tu API key de Windsor.ai (la
     encuentras en tu panel de Windsor.ai, sección API — es la misma key
     que usaste para el dashboard de FFJ si es la misma cuenta de Windsor).

3. **Activa GitHub Pages**:
   - Ve a `Settings` → `Pages`.
   - En "Source", elige **GitHub Actions** (no "Deploy from a branch").

4. **Lanza el workflow una vez a mano**:
   - Ve a la pestaña `Actions` → `Actualización diaria del dashboard` → `Run workflow`.
   - Cuando termine (1-2 minutos), tu dashboard estará publicado en la URL
     que indique `Settings` → `Pages` (algo como
     `https://jnls27.github.io/Platanomelon/`).

A partir de ahí, el workflow corre solo cada día a las 7:00 (hora España,
con el matiz de una hora en horario de invierno — ver comentario en
`.github/workflows/daily-update.yml`) y el dashboard se ve siempre
actualizado hasta el día anterior, en la misma URL.

## Estructura

- `index.html` — el dashboard (no se toca a mano; lee los datos con `fetch()`).
- `data.json` — datos de Meta Ads (España + México), sobrescrito a diario
  por el workflow.
- `insights.json` — el análisis de la pestaña "Insights" (últimos 7 días
  por mercado, razonamiento causal tipo paid media specialist). **No lo
  actualiza este workflow** — se regenera cada lunes mediante una tarea
  programada aparte (ver más abajo), porque requiere razonamiento, no solo
  aritmética.
- `scripts/update_data.py` — script que pide los datos a Windsor.ai y
  regenera `data.json`. Verifica automáticamente que los totales cuadren
  antes de sobrescribir nada.
- `.github/workflows/daily-update.yml` — la automatización diaria.

## Insights semanales (Los lunes a las 9:00, España)

`insights.json` se regenera cada lunes mediante una tarea programada del
asistente (no GitHub Actions, porque este paso requiere diagnóstico causal
sobre los datos de la semana, no solo recalcular fórmulas). Si en algún
momento esa entrega automática no puede hacer push directo al repo, el
asistente te entregará el archivo `insights.json` actualizado para que lo
subas tú con `Add file → Upload files` (sustituye el existente) — 10
segundos, un solo archivo pequeño.
