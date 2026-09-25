# Portal de Calificaciones Khan Academy — CBTA 24

Aplicación en Streamlit que lee los reportes CSV de Khan Academy desde Google Drive,
calcula calificaciones por bloque de entrega y parcial, y ofrece un panel para docentes
y una vista individual para estudiantes.

## Ejecutar

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Configuración (`.streamlit/secrets.toml`)

```toml
# Credenciales del Service Account de Google Drive (JSON completo)
gcp_service_account = '''{ ... }'''

# Opcional: acceso de administrador maestro (modo local).
# Si no se definen, este acceso queda deshabilitado.
ADMIN_USER = "usuario"
ADMIN_PASS = "una-contraseña-segura"
```

`ADMIN_USER` / `ADMIN_PASS` también pueden definirse como variables de entorno.

Sin `gcp_service_account` la app funciona en **modo local**, leyendo los CSV y
`credenciales.xlsx` desde la carpeta `datos/` (ignorada por git: nunca subas
credenciales de alumnos al repositorio).

## Estructura en Google Drive

- Carpeta raíz (`ROOT_FOLDER_ID` en `app.py`) con `docentes.xlsx`
  (`usuario_docente`, `password`, `asignatura`, `carpeta_nombre`, `Nombre del Docente`, `e_mail`).
- Una subcarpeta por docente/asignatura con:
  - Los reportes CSV de Khan Academy (el grupo se toma del nombre, p. ej. `5°H`).
    Si un grupo se descarga más de una vez, se usa la versión más reciente de cada tarea.
  - `credenciales.xlsx` (`Usuario`, `Contraseña`, `Nombre del estudiante`).
  - `criterios.json`, que la app crea al guardar la configuración del docente.
