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
  Columnas opcionales para **tutoría académica**: `rol` (`docente`, `tutor` o `directivo`) y
  `grupos_tutoria` (p. ej. `5°H, 5°J`; vacío o `todos` = todos los grupos). Un tutor o directivo
  sin `carpeta_nombre` entra directo a la vista de tutoría (todas las materias de sus grupos);
  un docente que además es tutor ve la sección **🧭 Tutoría** en su panel.
- Una subcarpeta por docente/asignatura con:
  - Los reportes CSV de Khan Academy (el grupo se toma del nombre, p. ej. `5°H`).
    Si un grupo se descarga más de una vez, se usa la versión más reciente de cada tarea.
  - `credenciales.xlsx` (`Usuario`, `Contraseña`, `Nombre del estudiante`).
  - `criterios.json`, que la app crea al guardar la configuración del docente.
  - `lista_alumnos.xlsx` (opcional, pestaña **Alumnos y cuentas**): lista oficial con
    `ID`, `Matrícula`, `Código provisional`, `Nombre`, `Grupo` y `PIN`. Permite que los
    alumnos entren con matrícula (o código provisional) y PIN, y une cuentas duplicadas de Khan.
  - `vinculos_khan.xlsx` (opcional): qué cuenta de Khan corresponde a cada alumno de la lista.
    Las coincidencias exactas de nombre se vinculan solas.

  - `evidencias.xlsx`, `calificaciones_parcial.xlsx` y `asistencia.xlsx` (opcionales, pestaña
    **Evaluación del parcial**): sellos de evidencia por bloque, examen y producto del parcial,
    y pase de lista. Los pesos de cada componente y la asistencia mínima se configuran en
    **Configuración → Componentes y asistencia** y se guardan en `criterios.json`.
  - **Criterios por grupo** (opcional, **Ajustes → Criterios → 👥 Por grupo**): el peso de Khan, los
    componentes del parcial y la clasificación pueden acordarse con cada grupo, para todo el semestre o
    solo a partir de un parcial. Se guardan en `criterios.json` (`criterios_por_grupo` y `grupos`). La
    escala, las fechas, la asistencia mínima y la rúbrica son las mismas para todos los grupos.
  - `metas.xlsx` (opcional): metas que cada alumno se pone por parcial desde su portal (🎯 Mi meta).
  - `temas.xlsx` (opcional, **Ajustes → 📚 Temas**): tema de cada actividad de Khan. Con él,
    los alumnos ven su dominio por tema (📚 Mis temas) y el docente ve **Calificaciones → Por tema**.

  Las plantillas de todos estos archivos se descargan en **Ajustes → 🚀 Primeros pasos**.
  El reporte de avance para la familia (PDF) se genera en **🔍 Alumno** y en **🧭 Tutoría**.

  Estos archivos se pueden abrir y corregir con Google Sheets, pero deben conservar el
  formato `.xlsx` y su nombre (no "Guardar como Hojas de cálculo de Google").
