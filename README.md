# VECTOR 84 // Radar de IA, Extrusión FDM y Emprendimiento

Web personal (y compartible) con estética **Synthwave Editorial Oscuro** (retro años 80 + moderno/futurista), alojada en **GitHub Pages** y actualizada automáticamente cada día mediante **GitHub Actions**.

## Qué incluye

- **El Parte Diario:** resumen ejecutivo arriba de la portada con las claves del día en 30 segundos y acceso directo a cada pieza.
- **Noticias de actualidad en español:** recopila feeds en inglés/español sobre **IA**, **Impresión 3D / extrusión de filamento (FDM/FFF)** y **Emprendimiento**, extrae imágenes OpenGraph, traduce titulares, resume cada artículo y enlaza al original.
- **Papers científicos con descarga directa de PDF:** consulta **arXiv** y **OpenAlex** (filtrado a publicaciones *open-access* con PDF directo), resume *Problema*, *Método* y *Aplicación práctica* en español y ofrece el botón directo **Descargar PDF**.
- **Filtros modernos y funciones locales:** filtrado por temática (`FDM`, `IA`, `Emprendimiento`, `Cruces`), pestañas (`Portada`, `Noticias`, `Papers PDF`, `Guardados`), buscador instantáneo, favoritos y estado *leído* en `localStorage`, interruptor `Efectos 80s: ON/OFF` y feed `feed.xml` propio.

---

## Puesta en marcha en GitHub y GitHub Pages (5 minutos)

### 1. Sube este proyecto a un repositorio de GitHub
```bash
git add .
git commit -m "feat: lanzamiento inicial de VECTOR 84"
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

### 2. Consigue tu clave gratuita de Gemini API
1. Entra en [Google AI Studio](https://aistudio.google.com/apikey) y crea una API key gratuita.
2. En tu repositorio de GitHub ve a **Settings → Secrets and variables → Actions → New repository secret**.
3. Crea un secreto con:
   - **Name:** `GEMINI_API_KEY`
   - **Secret:** pega tu clave de Gemini.

### 3. Activa GitHub Pages y permisos del bot
1. Ve a **Settings → Pages**:
   - En **Build and deployment → Source**, elige **GitHub Actions**.
2. Ve a **Settings → Actions → General → Workflow permissions**:
   - Marca **Read and write permissions** y guarda (para que el bot pueda actualizar `data/feed.json` y `feed.xml` cada mañana).

### 4. Ejecuta tu primera actualización manual
1. Ve a la pestaña **Actions** de tu repositorio.
2. Selecciona **Actualizar Radar y Desplegar en GitHub Pages** y pulsa **Run workflow**.
3. A partir de ese momento se actualizará sola todos los días a las **06:30 UTC** (07:30/08:30 hora España).

---

## Personalizar fuentes y horarios

- **Añadir o quitar medios / búsquedas de papers:** edita [`scripts/sources.json`](scripts/sources.json).
- **Cambiar la frecuencia de actualización:** ajusta la línea `cron` en [`.github/workflows/update-and-deploy.yml`](.github/workflows/update-and-deploy.yml).
- **Probar en local:**
  ```bash
  # Probar la web en local
  python3 -m http.server 8000
  # Abrir http://localhost:8000

  # Probar actualización manual con tu clave Gemini en local
  GEMINI_API_KEY="tu_clave" python3 scripts/update_feed.py
  ```
