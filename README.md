# Rebajón 💧
App Android personal de alertas de rebajas, comparativa e histórico de precios.

## APK (GitHub)
1. Sube esta carpeta a un repo de GitHub.
2. Pestaña **Actions → Build APK** (se lanza sola al hacer push). Descarga `Rebajon-APK` y copia `app-debug.apk` al móvil.

## Servidor (PC/Raspberry siempre encendido)
```
cd server && pip install -r requirements.txt && python app.py
```
En la app: Ajustes → `http://IP_DEL_SERVIDOR:8000`. Fuera de casa usa Tailscale (no expongas el puerto a Internet).
