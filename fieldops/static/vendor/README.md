# Locally served UI dependencies

No runtime CDN requests or frontend build step.

- `bootstrap-5.3.8.min.css`: https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css
  SHA-256: `d85327d99c7a3ee1f9b5d0500d1370acea3ad2db39c163c2f51f232baedbdede`
- `htmx-2.0.8.min.js`: https://cdn.jsdelivr.net/npm/htmx.org@2.0.8/dist/htmx.min.js
  SHA-256: `22283ef68cb7545914f0a88a1bdedc7256a703d1d580c1d255217d0a50d31313`

Bootstrap is MIT licensed; see bootstrap-LICENSE. HTMX is Zero-Clause BSD; see htmx-LICENSE.
Official documentation: https://getbootstrap.com/docs/5.3/getting-started/download/ and https://htmx.org/docs/.
Only Bootstrap CSS is needed: native HTML controls and details elements avoid a JavaScript widget dependency.
