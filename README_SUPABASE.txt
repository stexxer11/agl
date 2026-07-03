AGL Closing V18 SUPABASE
=========================

Esta versión mantiene el diseño y las reglas del ZIP base, pero cambia la arquitectura:

Excel Masters -> Recargar Masters -> Supabase/PostgreSQL -> App Web

1) Crear proyecto en Supabase
- En Supabase crea un proyecto.
- Ve a Project Settings > Database > Connection string.
- Copia la conexión tipo URI de PostgreSQL.
- Reemplaza [YOUR-PASSWORD] por la contraseña real.

Ejemplo:
postgresql://postgres.xxxxx:TU_PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres

2) Configurar la app
- Ejecuta python main.py
- Abre http://127.0.0.1:8000
- En Config pega la DATABASE_URL de Supabase.
- Configura las rutas de AGL_MASTER, STATUS_MASTER y CLIENT_MASTER.
- Presiona Guardar rutas.
- Presiona Recargar Masters.

3) Verificar
Abre:
http://127.0.0.1:8000/api/db-status

Debe mostrar filas en:
- agl_rates
- status_refs
- clients
- brands
- directions

4) Uso normal
- Buscar AGL Ref lee desde Supabase.
- Services/tarifas leen desde Supabase.
- Guardados/cases se guardan en Supabase.
- Todos los usuarios conectados a la misma DATABASE_URL ven la misma data.

IMPORTANTE
No compartas excdb.sqlite por OneDrive. En esta versión ya no se usa como centro.
La DB central es Supabase/PostgreSQL.
