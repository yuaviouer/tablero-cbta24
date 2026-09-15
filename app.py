"""
Portal de Calificaciones Khan Academy - TSM II
CBTA 24 - Temas Selectos de Matemáticas II
"""

import os
import io
import json
import glob
import re
from datetime import date, datetime
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIGURACIÓN GENERAL Y ESTILOS
# ==============================================================================
st.set_page_config(
    page_title="Portal de Calificaciones - TSM II",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Credenciales de administrador por defecto
ADMIN_USERNAME = os.environ.get("ADMIN_USER", "javier_admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin_password")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
CONFIG_PARCIALES_PATH = os.path.join(DATA_DIR, "config_parciales.json")

# Mapeo de meses en español
MONTHS_ES = {
    'ene': 1, 'enero': 1,
    'feb': 2, 'febrero': 2,
    'mar': 3, 'marzo': 3,
    'abr': 4, 'abril': 4,
    'may': 5, 'mayo': 5,
    'jun': 6, 'junio': 6,
    'jul': 7, 'julio': 7,
    'ago': 8, 'agosto': 8,
    'sep': 9, 'sept': 9, 'set': 9, 'septiembre': 9, 'setiembre': 9,
    'oct': 10, 'octubre': 10,
    'nov': 11, 'noviembre': 11,
    'dic': 12, 'diciembre': 12
}

# Inyección de estilos CSS
st.markdown("""
<style>
    /* General UI */
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        color: white;
        padding: 24px 30px;
        border-radius: 12px;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .main-header h1 {
        color: white !important;
        font-size: 1.9rem;
        margin: 0;
        font-weight: 700;
    }
    .main-header p {
        color: #e0e7ff !important;
        font-size: 1.0rem;
        margin: 5px 0 0 0;
    }
    .stat-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 18px 20px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .stat-title {
        font-size: 0.85rem;
        text-transform: uppercase;
        color: #64748b;
        font-weight: 600;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }
    .stat-val {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0f172a;
    }
    .block-card {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-left: 5px solid #2563eb;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 18px;
    }
    .badge-parcial {
        display: inline-block;
        background-color: #dbeafe;
        color: #1e40af;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-left: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# GESTIÓN Y CONFIGURACIÓN DE PARCIALES (PERIODOS DE EVALUACIÓN)
# ==============================================================================
def get_default_parciales_config():
    """Configuración predeterminada de fechas para los 3 Parciales del ciclo."""
    return {
        'Parcial 1': {'start': '2025-08-15', 'end': '2025-10-03'},
        'Parcial 2': {'start': '2025-10-04', 'end': '2025-11-21'},
        'Parcial 3': {'start': '2025-11-22', 'end': '2026-01-23'}
    }


def load_parciales_config():
    """Carga la configuración de fechas de Parciales desde archivo JSON o default."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PARCIALES_PATH):
        try:
            with open(CONFIG_PARCIALES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                parsed = {}
                for p_name in ['Parcial 1', 'Parcial 2', 'Parcial 3']:
                    if p_name in data:
                        parsed[p_name] = {
                            'start': date.fromisoformat(data[p_name]['start']),
                            'end': date.fromisoformat(data[p_name]['end'])
                        }
                if len(parsed) == 3:
                    return parsed
        except Exception:
            pass

    defaults = get_default_parciales_config()
    return {
        k: {'start': date.fromisoformat(v['start']), 'end': date.fromisoformat(v['end'])}
        for k, v in defaults.items()
    }


def save_parciales_config(config_dict):
    """Guarda la configuración de fechas de Parciales en formato JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    serializable = {}
    for k, v in config_dict.items():
        serializable[k] = {
            'start': v['start'].isoformat() if isinstance(v['start'], date) else str(v['start']),
            'end': v['end'].isoformat() if isinstance(v['end'], date) else str(v['end'])
        }
    with open(CONFIG_PARCIALES_PATH, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=4, ensure_ascii=False)


def assign_parcial(dt, parcial_config):
    """
    Asigna una etiqueta 'Parcial 1', 'Parcial 2', 'Parcial 3' o 'Sin asignar'
    a una fecha de entrega según los rangos configurados.
    """
    if pd.isna(dt):
        return 'Sin asignar'
    task_date = dt.date() if hasattr(dt, 'date') else dt
    for p_name in ['Parcial 1', 'Parcial 2', 'Parcial 3']:
        cfg = parcial_config.get(p_name, {})
        start_d = cfg.get('start')
        end_d = cfg.get('end')
        if start_d and end_d:
            if start_d <= task_date <= end_d:
                return p_name
    return 'Sin asignar'


# ==============================================================================
# IDENTIFICACIÓN DE GRUPO
# ==============================================================================
def extract_group(filename):
    """
    Extrae el identificador de grupo a partir del nombre de archivo.
    Busca patrones como '5°H', '5° H', '5H', '5-H', '5° F', '5F', '5° G', etc.
    Si no encuentra coincidencia, retorna el nombre base sin extensión.
    """
    base_name = os.path.basename(filename)
    match = re.search(r'([1-6])[\s°º\-_]*([A-Za-z])(?=[^a-zA-Z]|$)', base_name)
    if match:
        digit, letter = match.groups()
        return f"{digit}°{letter.upper()}"
    return os.path.splitext(base_name)[0]


# ==============================================================================
# PARSER DE FECHAS PERSONALIZADO PARA KHAN ACADEMY
# ==============================================================================
def parse_khan_date(val, default_year=2025):
    """
    Convierte una cadena de fecha de Khan Academy en español con símbolo de grado/ordinal
    (ej. 'sep. 12º, 11:59PM' o 'dic. 14º, 11:00PM') en un objeto pd.Timestamp.
    Por defecto asigna el año 2025.
    """
    if pd.isna(val) or not str(val).strip():
        return pd.NaT

    s = str(val).strip().lower()

    pattern = r'([a-záéíóú]+)\.?\s+(\d{1,2})[º°ª]?(?:[,\s]+(\d{4}))?[,\s]+(\d{1,2}):(\d{2})\s*(am|pm)?'
    match = re.search(pattern, s)

    if match:
        mon_str, day_str, yr_str, hr_str, min_str, ampm_str = match.groups()
        mon = MONTHS_ES.get(mon_str[:3], 1)
        day = int(day_str)
        yr = int(yr_str) if yr_str else default_year
        hr = int(hr_str)
        mn = int(min_str)

        if ampm_str:
            if ampm_str == 'pm' and hr < 12:
                hr += 12
            elif ampm_str == 'am' and hr == 12:
                hr = 0

        try:
            return pd.Timestamp(year=yr, month=mon, day=day, hour=hr, minute=mn)
        except Exception:
            return pd.NaT

    try:
        return pd.to_datetime(s)
    except Exception:
        return pd.NaT


# ==============================================================================
# MOTOR DE CALIFICACIÓN PONDERADA
# ==============================================================================
def calculate_weighted_task(row):
    """
    Calcula los puntos máximos y puntos ganados según el sistema ponderado:
    - Video: Max points = 1. Earned = 1.0 (a tiempo), 0.1 (tardío), 0.0 (no completado).
    - Artículo: Max points = 2. Earned = 2.0 (a tiempo), 0.2 (tardío), 0.0 (no completado).
    - Ejercicios / Quizzes (donde 'Número total de preguntas' > 0):
        Max points = N (Número total de preguntas).
        Earned = n (aciertos) tras aplicar penalizaciones:
          * Penalización por intentos (>3): -1 acierto por cada intento extra.
          * Si tardía: máx es 10% de N (0.1 * N).
          * Si tardía Y >3 intentos: 0 puntos.
          * Si no completado: 0 puntos.
    """
    task_type = str(row.get('Tipo de tarea', '')).strip().lower()
    due_dt = row.get('dt_entrega')
    comp_dt = row.get('dt_terminacion')

    is_completed = pd.notna(comp_dt)
    is_late = is_completed and pd.notna(due_dt) and (comp_dt > due_dt)

    raw_attempts = row.get('Número de intentos', '')
    try:
        if pd.isna(raw_attempts) or str(raw_attempts).strip() in ['', 'En progreso']:
            attempts = 1 if is_completed else 0
        else:
            attempts = int(float(raw_attempts))
    except (ValueError, TypeError):
        attempts = 1 if is_completed else 0

    # 1. VIDEO
    if task_type == 'video':
        max_pts = 1.0
        if not is_completed:
            earned_pts = 0.0
            status = 'No completado'
            obs = 'No completado'
        elif is_late:
            earned_pts = 0.1
            status = 'Tardía'
            obs = 'Completado tardío (0.1 / 1.0 pt)'
        else:
            earned_pts = 1.0
            status = 'A tiempo'
            obs = 'Completado a tiempo (1.0 / 1.0 pt)'

        return {
            'earned_points': earned_pts,
            'max_points': max_pts,
            'status': status,
            'observations': obs,
            'attempts_count': attempts,
            'correct_count': 0,
            'total_count': 0,
            'is_completed': is_completed,
            'is_late': is_late
        }

    # 2. ARTÍCULO
    elif task_type in ['artículo', 'articulo']:
        max_pts = 2.0
        if not is_completed:
            earned_pts = 0.0
            status = 'No completado'
            obs = 'No completado'
        elif is_late:
            earned_pts = 0.2
            status = 'Tardía'
            obs = 'Completado tardío (0.2 / 2.0 pts)'
        else:
            earned_pts = 2.0
            status = 'A tiempo'
            obs = 'Completado a tiempo (2.0 / 2.0 pts)'

        return {
            'earned_points': earned_pts,
            'max_points': max_pts,
            'status': status,
            'observations': obs,
            'attempts_count': attempts,
            'correct_count': 0,
            'total_count': 0,
            'is_completed': is_completed,
            'is_late': is_late
        }

    # 3. EJERCICIOS / PREGUNTAS
    else:
        try:
            val_total = row.get('Número total de preguntas', 0)
            total_q = float(val_total) if (pd.notna(val_total) and str(val_total).strip() != '') else 0.0
        except (ValueError, TypeError):
            total_q = 0.0

        try:
            val_correct = row.get('Mayor número de preguntas correctas hasta ahora', 0)
            if pd.isna(val_correct) or str(val_correct).strip() == '':
                val_correct = row.get('Número de preguntas correctas en la fecha de entrega', 0)
            correct_q = float(val_correct) if (pd.notna(val_correct) and str(val_correct).strip() != '') else 0.0
        except (ValueError, TypeError):
            correct_q = 0.0

        max_pts = total_q
        penalties = []

        if not is_completed or total_q == 0:
            earned_pts = 0.0
            status = 'No completado'
            obs = 'Sin entrega'
        else:
            penalty_attempts = max(0, attempts - 3)
            effective_correct = max(0.0, correct_q - penalty_attempts)

            if penalty_attempts > 0:
                penalties.append(f"-{penalty_attempts} acierto(s) por {attempts} intentos")

            if is_late and attempts > 3:
                earned_pts = 0.0
                penalties.append("Tardía + >3 intentos (0 pts)")
                status = "Tardía (>3 intentos)"
            elif is_late:
                earned_pts = min(effective_correct, 0.1 * total_q)
                penalties.append(f"Entrega tardía (Máx. {0.1 * total_q:.1f} pts)")
                status = "Tardía"
            else:
                earned_pts = min(effective_correct, total_q)
                status = "A tiempo" if penalty_attempts == 0 else "A tiempo (con penalización)"

            obs = "; ".join(penalties) if penalties else "A tiempo (sin penalización)"

        return {
            'earned_points': round(earned_pts, 2),
            'max_points': max_pts,
            'status': status,
            'observations': obs,
            'attempts_count': attempts,
            'correct_count': int(correct_q) if pd.notna(correct_q) else 0,
            'total_count': int(total_q) if pd.notna(total_q) else 0,
            'is_completed': is_completed,
            'is_late': is_late
        }


# ==============================================================================
# CARGA Y CACHÉ DE DATOS
# ==============================================================================
@st.cache_data
def load_credentials():
    """Carga credenciales desde datos/credenciales.xlsx o fallback CSVs."""
    os.makedirs(DATA_DIR, exist_ok=True)
    excel_path = os.path.join(DATA_DIR, "credenciales.xlsx")

    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
            cols = {c: c.strip() for c in df.columns}
            df = df.rename(columns=cols)
            rename_map = {}
            for col in df.columns:
                col_clean = col.lower()
                if 'usuario' in col_clean:
                    rename_map[col] = 'Usuario'
                elif 'contrase' in col_clean:
                    rename_map[col] = 'Contraseña'
                elif 'estudiante' in col_clean or 'nombre' in col_clean:
                    rename_map[col] = 'Nombre del estudiante'
            df = df.rename(columns=rename_map)
            if {'Usuario', 'Contraseña', 'Nombre del estudiante'}.issubset(df.columns):
                df['Usuario'] = df['Usuario'].astype(str).str.strip()
                df['Contraseña'] = df['Contraseña'].astype(str).str.strip()
                df['Nombre del estudiante'] = df['Nombre del estudiante'].astype(str).str.strip()
                return df[['Usuario', 'Contraseña', 'Nombre del estudiante']]
        except Exception as e:
            st.warning(f"Aviso al leer {excel_path}: {e}")

    csv_files = glob.glob(os.path.join(DATA_DIR, "*redencial*.csv"))
    if csv_files:
        dfs = []
        for cf in csv_files:
            try:
                temp_df = pd.read_csv(cf, encoding='utf-8-sig')
                rename_map = {}
                for col in temp_df.columns:
                    col_clean = col.lower()
                    if 'usuario' in col_clean:
                        rename_map[col] = 'Usuario'
                    elif 'contrase' in col_clean:
                        rename_map[col] = 'Contraseña'
                    elif 'estudiante' in col_clean:
                        rename_map[col] = 'Nombre del estudiante'
                temp_df = temp_df.rename(columns=rename_map)
                if {'Usuario', 'Contraseña', 'Nombre del estudiante'}.issubset(temp_df.columns):
                    dfs.append(temp_df[['Usuario', 'Contraseña', 'Nombre del estudiante']])
            except Exception:
                continue

        if dfs:
            combined = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=['Usuario'])
            combined['Usuario'] = combined['Usuario'].astype(str).str.strip()
            combined['Contraseña'] = combined['Contraseña'].astype(str).str.strip()
            combined['Nombre del estudiante'] = combined['Nombre del estudiante'].astype(str).str.strip()
            try:
                combined.to_excel(excel_path, index=False)
            except Exception:
                pass
            return combined

    return pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])


@st.cache_data
def load_assignments():
    """
    Lee todos los archivos CSV en la carpeta datos/ (exceptuando credenciales)
    y procesa las tareas aplicando extracción de grupo, parseo de fechas y cálculo ponderado.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    assignment_files = [f for f in csv_files if "credencial" not in os.path.basename(f).lower()]

    if not assignment_files:
        return pd.DataFrame()

    dfs = []
    for filepath in assignment_files:
        try:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
            df['Archivo_Origen'] = os.path.basename(filepath)
            df['Grupo'] = extract_group(filepath)
            dfs.append(df)
        except Exception:
            try:
                df = pd.read_csv(filepath, encoding='latin-1')
                df['Archivo_Origen'] = os.path.basename(filepath)
                df['Grupo'] = extract_group(filepath)
                dfs.append(df)
            except Exception as e:
                st.error(f"Error al leer archivo {os.path.basename(filepath)}: {e}")

    if not dfs:
        return pd.DataFrame()

    all_data = pd.concat(dfs, ignore_index=True)
    all_data.columns = [c.strip() for c in all_data.columns]

    if 'Nombre del estudiante' in all_data.columns:
        all_data['Nombre del estudiante'] = all_data['Nombre del estudiante'].astype(str).str.strip()

    # Parsear fechas usando regla de Khan Academy
    if 'Fecha de entrega' in all_data.columns:
        all_data['dt_entrega'] = all_data['Fecha de entrega'].apply(parse_khan_date)
    else:
        all_data['dt_entrega'] = pd.NaT

    if 'Última fecha de terminación' in all_data.columns:
        all_data['dt_terminacion'] = all_data['Última fecha de terminación'].apply(parse_khan_date)
    else:
        all_data['dt_terminacion'] = pd.NaT

    # Calcular puntos ponderados
    grades_info = all_data.apply(calculate_weighted_task, axis=1)
    grades_df = pd.DataFrame(list(grades_info))

    for col in grades_df.columns:
        all_data[col] = grades_df[col]

    # Asignar Parcial según configuración
    parcial_config = load_parciales_config()
    all_data['Parcial'] = all_data['dt_entrega'].apply(lambda d: assign_parcial(d, parcial_config))

    return all_data


def compute_student_block_grades(assignments_df):
    """
    Calcula la calificación por bloque (Fecha de entrega) para cada estudiante y grupo:
    Block Grade = (Sum(Puntos Ganados) / Sum(Puntos Posibles)) * 10
    Redondeado a 1 decimal.
    """
    if assignments_df.empty:
        return pd.DataFrame()

    block_summary = assignments_df.groupby(
        ['Grupo', 'Nombre del estudiante', 'Fecha de entrega'],
        as_index=False
    ).agg(
        earned_sum=('earned_points', 'sum'),
        max_sum=('max_points', 'sum'),
        dt_entrega=('dt_entrega', 'first'),
        parcial=('Parcial', 'first')
    )

    block_summary['block_grade'] = block_summary.apply(
        lambda r: round((r['earned_sum'] / r['max_sum'] * 10.0), 1) if r['max_sum'] > 0 else 0.0,
        axis=1
    )

    return block_summary


# ==============================================================================
# COMPONENTE REUTILIZABLE: DASHBOARD DETALLADO DEL ESTUDIANTE
# ==============================================================================
def render_student_dashboard(student_name, student_data, is_admin_drilldown=False):
    """
    Renderiza la interfaz detallada del estudiante (tarjetas KPIs, filtros por Parcial
    y tipo de tarea, y bloques expandibles con tareas, intentos, fechas y puntos).
    Se utiliza tanto en la vista del Estudiante como en el Drill-Down del Administrador.
    """
    if student_data.empty:
        st.info(f"No se encontraron actividades registradas para **{student_name}**.")
        return

    # --------------------------------------------------------------------------
    # Filtros superiores (Parcial y Tipo de Actividad)
    # --------------------------------------------------------------------------
    filter_col1, filter_col2 = st.columns([3, 2])

    with filter_col1:
        parciales_disponibles = ["Todas", "Parcial 1", "Parcial 2", "Parcial 3", "Sin asignar"]
        # Detectar qué parciales tienen realmente datos
        present_parciales = set(student_data['Parcial'].unique())
        selected_parcial = st.radio(
            "Filtrar por Periodo (Parcial):",
            parciales_disponibles,
            horizontal=True,
            key=f"parcial_filter_{'admin' if is_admin_drilldown else 'student'}_{student_name}"
        )

    with filter_col2:
        tipo_filtro = st.selectbox(
            "Filtrar por tipo de actividad:",
            ["Todas las actividades", "Solo Ejercicios", "Solo Videos", "Solo Artículos"],
            key=f"tipo_filter_{'admin' if is_admin_drilldown else 'student'}_{student_name}"
        )

    # Filtrar por Parcial si aplica
    active_data = student_data.copy()
    if selected_parcial != "Todas":
        active_data = active_data[active_data['Parcial'] == selected_parcial]

    if active_data.empty:
        st.warning(f"No hay actividades para el periodo **{selected_parcial}**.")
        return

    # --------------------------------------------------------------------------
    # Tarjetas de Resumen General (KPIs)
    # --------------------------------------------------------------------------
    total_tasks = len(active_data)
    completed_tasks = active_data['is_completed'].sum()
    late_tasks = active_data['is_late'].sum()
    ontime_tasks = completed_tasks - late_tasks

    # Promedio del estudiante para el filtro activo
    active_blocks = compute_student_block_grades(active_data)
    overall_avg = active_blocks['block_grade'].mean() if not active_blocks.empty else 0.0

    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    with kpi_col1:
        title_avg = "Promedio General" if selected_parcial == "Todas" else f"Promedio {selected_parcial}"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">{title_avg}</div>
            <div class="stat-val" style="color: {'#16a34a' if overall_avg >= 7.0 else '#dc2626'};">{overall_avg:.1f} <span style="font-size: 1rem; color: #64748b;">/ 10</span></div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">Actividades</div>
            <div class="stat-val">{total_tasks}</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">Completadas</div>
            <div class="stat-val" style="color: #2563eb;">{completed_tasks}</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col4:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">A Tiempo</div>
            <div class="stat-val" style="color: #16a34a;">{ontime_tasks}</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col5:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">Tardías</div>
            <div class="stat-val" style="color: {'#ea580c' if late_tasks > 0 else '#64748b'};">{late_tasks}</div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")
    st.divider()

    # --------------------------------------------------------------------------
    # Agrupación por Bloques de Entrega
    # --------------------------------------------------------------------------
    st.markdown("### 📋 Calificaciones por Bloque de Entrega")
    st.caption("Cada fecha representa un bloque/semana evaluado mediante la suma ponderada de puntos.")

    unique_due_dates = (
        active_data.dropna(subset=['dt_entrega'])
        .sort_values('dt_entrega')['Fecha de entrega']
        .unique()
        .tolist()
    )
    for d in active_data['Fecha de entrega'].unique():
        if d not in unique_due_dates:
            unique_due_dates.append(d)

    for due_date_str in unique_due_dates:
        block_df = active_data[active_data['Fecha de entrega'] == due_date_str].copy()
        parcial_tag = block_df['Parcial'].iloc[0] if 'Parcial' in block_df.columns and not block_df.empty else 'Sin asignar'

        # Puntos del bloque completos
        block_earned_total = block_df['earned_points'].sum()
        block_max_total = block_df['max_points'].sum()
        block_grade = round((block_earned_total / block_max_total * 10.0), 1) if block_max_total > 0 else 0.0

        # Filtrar solo para visualización en tabla si seleccionó tipo
        if tipo_filtro == "Solo Ejercicios":
            display_df = block_df[block_df['Tipo de tarea'].str.lower() == 'ejercicio']
        elif tipo_filtro == "Solo Videos":
            display_df = block_df[block_df['Tipo de tarea'].str.lower() == 'video']
        elif tipo_filtro == "Solo Artículos":
            display_df = block_df[block_df['Tipo de tarea'].str.lower().isin(['artículo', 'articulo'])]
        else:
            display_df = block_df

        if display_df.empty:
            continue

        block_completed = block_df['is_completed'].sum()
        block_tasks_count = len(block_df)

        # Header del bloque
        st.markdown(f"""
        <div class="block-card">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <h3 style="margin: 0; color: #1e293b; font-size: 1.25rem;">
                        📅 Fecha de Entrega: <strong>{due_date_str}</strong>
                        <span class="badge-parcial">{parcial_tag}</span>
                    </h3>
                    <span style="color: #64748b; font-size: 0.9rem;">
                        Actividades: {block_tasks_count} | Completadas: {block_completed} | 
                        Puntos Obtenidos: <strong>{block_earned_total:.1f} / {block_max_total:.1f}</strong>
                    </span>
                </div>
                <div style="text-align: right; margin-top: 5px;">
                    <span style="font-size: 0.85rem; color: #64748b; font-weight: 600; text-transform: uppercase;">Calificación del Bloque:</span>
                    <span style="font-size: 1.7rem; font-weight: 800; color: {'#16a34a' if block_grade >= 7.0 else '#dc2626'}; margin-left: 8px;">{block_grade:.1f}</span>
                    <span style="font-size: 0.95rem; color: #64748b;"> / 10</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.progress(min(1.0, max(0.0, block_grade / 10.0)))

        # Tabla detallada del bloque
        table_rows = []
        for _, row in display_df.iterrows():
            if row['Tipo de tarea'].lower() == 'ejercicio' or row['total_count'] > 0:
                aciertos_str = f"{row['correct_count']} / {row['total_count']}"
                intentos_str = str(row['attempts_count'])
            else:
                aciertos_str = "N/A"
                intentos_str = "1" if row['is_completed'] else "0"

            terminacion_str = row['Última fecha de terminación'] if pd.notna(row['Última fecha de terminación']) else "Sin entrega"

            table_rows.append({
                "Actividad": row['Nombre de la tarea'],
                "Tipo": row['Tipo de tarea'],
                "Intentos": intentos_str,
                "Aciertos": aciertos_str,
                "Puntos Ganados": f"{row['earned_points']:.1f} / {row['max_points']:.1f}",
                "Fecha Terminación": terminacion_str,
                "Estado": row['status'],
                "Detalle / Penalización": row['observations']
            })

        table_df = pd.DataFrame(table_rows)

        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Actividad": st.column_config.TextColumn("Actividad", width="large"),
                "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                "Intentos": st.column_config.TextColumn("Intentos", width="small"),
                "Aciertos": st.column_config.TextColumn("Aciertos", width="small"),
                "Puntos Ganados": st.column_config.TextColumn("Puntos Ganados", width="medium"),
                "Fecha Terminación": st.column_config.TextColumn("Fecha Terminación", width="medium"),
                "Estado": st.column_config.TextColumn("Estado", width="medium"),
                "Detalle / Penalización": st.column_config.TextColumn("Detalle / Penalización", width="large"),
            }
        )
        st.write("")

    # Acordeón de reglas
    with st.expander("ℹ️ ¿Cómo se calculan los puntos ponderados y penalizaciones?"):
        st.markdown("""
        ### Sistema de Puntuación Ponderada
        - **Videos (1 pto base):** 1.0 pto a tiempo, 0.1 pto tardío, 0 no completado.
        - **Artículos (2 ptos base):** 2.0 ptos a tiempo, 0.2 ptos tardío, 0 no completado.
        - **Ejercicios ($N$ preguntas = $N$ ptos posibles):**
          - Aciertos obtenidos con 3 intentos libres.
          - A partir del 4º intento, se resta 1 acierto por cada intento extra.
          - Entrega tardía: máximo el 10% de $N$ ($0.1 \\times N$).
          - Tardía con más de 3 intentos: **0 puntos**.
        - **Calificación del Bloque:** $\\left( \\frac{\\sum \\text{Puntos Ganados}}{\\sum \\text{Puntos Posibles}} \\right) \\times 10$, redondeado a 1 decimal.
        """)


# ==============================================================================
# VISTA: INICIO DE SESIÓN
# ==============================================================================
def render_login():
    st.markdown("""
    <div class="main-header" style="text-align: center;">
        <h1>📐 Portal de Calificaciones - TSM II</h1>
        <p>Centro de Bachillerato Tecnológico Agropecuario No. 24 | Temas Selectos de Matemáticas II</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Iniciar Sesión")
        st.caption("Ingresa con tu usuario y contraseña institucional de Khan Academy, o como Administrador.")

        with st.form("login_form", clear_on_submit=False):
            username_input = st.text_input("Usuario", placeholder="ej. alboresclementepaulo o javier_admin").strip()
            password_input = st.text_input("Contraseña", type="password", placeholder="••••••••").strip()
            submit_btn = st.form_submit_button("Ingresar al Portal", use_container_width=True, type="primary")

            if submit_btn:
                if not username_input or not password_input:
                    st.error("Por favor completa ambos campos.")
                    return

                # 1. Administrador
                if username_input == ADMIN_USERNAME and password_input == ADMIN_PASSWORD:
                    st.session_state['logged_in'] = True
                    st.session_state['role'] = 'admin'
                    st.session_state['username'] = ADMIN_USERNAME
                    st.session_state['student_name'] = "Profesor / Administrador"
                    st.success("Acceso concedido como Administrador.")
                    st.rerun()

                # 2. Estudiante
                creds_df = load_credentials()
                if not creds_df.empty:
                    matched = creds_df[
                        (creds_df['Usuario'].str.lower() == username_input.lower()) &
                        (creds_df['Contraseña'] == password_input)
                    ]
                    if not matched.empty:
                        student_name = matched.iloc[0]['Nombre del estudiante']
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = 'student'
                        st.session_state['username'] = username_input
                        st.session_state['student_name'] = student_name
                        st.success(f"Bienvenido(a), {student_name}")
                        st.rerun()
                    else:
                        st.error("Usuario o contraseña incorrectos. Verifica tus datos.")
                else:
                    st.error("No se encontró el archivo de credenciales. Contacta al docente.")

        st.info("💡 **Estudiantes:** Utilicen el usuario y contraseña asignados para Khan Academy.\n\n"
                "🛡️ **Docente:** Inicia sesión con tus credenciales de Administrador.")


# ==============================================================================
# VISTA: PANEL DE ADMINISTRADOR
# ==============================================================================
def render_admin():
    header_col1, header_col2 = st.columns([5, 1])
    with header_col1:
        st.markdown("""
        <div class="main-header" style="background: linear-gradient(135deg, #0f172a 0%, #334155 100%);">
            <h1>🛡️ Panel de Administración - Control Escolar TSM II</h1>
            <p>Monitoreo por grupos, concentrado master, configuración de parciales y drill-down individual</p>
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # Cargar datos
    all_assignments = load_assignments()
    all_credentials = load_credentials()
    parcial_config = load_parciales_config()

    # --------------------------------------------------------------------------
    # SECCIÓN 1: CONFIGURACIÓN DE PARCIALES Y CARGA DE ARCHIVOS (EXPANDIBLES)
    # --------------------------------------------------------------------------
    col_cfg1, col_cfg2 = st.columns(2)

    with col_cfg1:
        with st.expander("⚙️ Configuración de Parciales (Periodos)", expanded=False):
            st.write("Define las fechas límite de inicio y fin para cada uno de los 3 Parciales del semestre:")
            with st.form("form_parciales"):
                cp1_col1, cp1_col2 = st.columns(2)
                with cp1_col1:
                    p1_s = st.date_input("Inicio Parcial 1", value=parcial_config['Parcial 1']['start'])
                    p2_s = st.date_input("Inicio Parcial 2", value=parcial_config['Parcial 2']['start'])
                    p3_s = st.date_input("Inicio Parcial 3", value=parcial_config['Parcial 3']['start'])
                with cp1_col2:
                    p1_e = st.date_input("Fin Parcial 1", value=parcial_config['Parcial 1']['end'])
                    p2_e = st.date_input("Fin Parcial 2", value=parcial_config['Parcial 2']['end'])
                    p3_e = st.date_input("Fin Parcial 3", value=parcial_config['Parcial 3']['end'])

                save_p_btn = st.form_submit_button("💾 Guardar Fechas de Parciales", type="primary")
                if save_p_btn:
                    new_cfg = {
                        'Parcial 1': {'start': p1_s, 'end': p1_e},
                        'Parcial 2': {'start': p2_s, 'end': p2_e},
                        'Parcial 3': {'start': p3_s, 'end': p3_e}
                    }
                    save_parciales_config(new_cfg)
                    st.cache_data.clear()
                    st.success("✅ Fechas de Parciales actualizadas con éxito.")
                    st.rerun()

    with col_cfg2:
        with st.expander("📂 Carga de Archivos (CSV y Credenciales)", expanded=False):
            st.write("Sube nuevos archivos de Khan Academy o credenciales a la carpeta `datos/`:")
            tab_up1, tab_up2 = st.tabs(["📊 Subir CSVs Tareas", "🔑 Subir Credenciales"])

            with tab_up1:
                uploaded_csvs = st.file_uploader(
                    "Selecciona archivos CSV de tareas:",
                    type=["csv"],
                    accept_multiple_files=True,
                    key="admin_csv_uploader"
                )
                if uploaded_csvs:
                    if st.button("💾 Guardar CSVs", key="save_csv_btn"):
                        for f in uploaded_csvs:
                            with open(os.path.join(DATA_DIR, f.name), "wb") as out_file:
                                out_file.write(f.getbuffer())
                        st.cache_data.clear()
                        st.success(f"✅ Se guardaron {len(uploaded_csvs)} archivo(s) CSV.")
                        st.rerun()

            with tab_up2:
                uploaded_cred = st.file_uploader(
                    "Selecciona archivo credenciales (.xlsx o .csv):",
                    type=["xlsx", "csv"],
                    accept_multiple_files=False,
                    key="admin_cred_uploader"
                )
                if uploaded_cred:
                    if st.button("💾 Guardar Credenciales", key="save_cred_btn"):
                        dest_path = os.path.join(DATA_DIR, "credenciales.xlsx")
                        if uploaded_cred.name.endswith(".xlsx"):
                            with open(dest_path, "wb") as out_file:
                                out_file.write(uploaded_cred.getbuffer())
                        else:
                            temp_df = pd.read_csv(uploaded_cred, encoding='utf-8-sig')
                            temp_df.to_excel(dest_path, index=False)
                        st.cache_data.clear()
                        st.success("✅ Credenciales actualizadas.")
                        st.rerun()

    st.divider()

    # --------------------------------------------------------------------------
    # SECCIÓN 2: MASTER DASHBOARD CON FILTRO DE GRUPO Y COLUMNA 'GRUPO'
    # --------------------------------------------------------------------------
    st.markdown("### 📊 Master Dashboard de Calificaciones")
    st.caption("Concentrado de calificaciones por bloques. Incluye columna de Grupo y filtros interactivos.")

    if all_assignments.empty:
        st.warning("No hay tareas registradas en la carpeta `datos/`.")
        return

    # Obtener grupos disponibles
    available_groups = sorted([g for g in all_assignments['Grupo'].dropna().unique() if g])

    # Controles del Master Dashboard
    f_col1, f_col2, f_col3, f_col4 = st.columns([3, 2, 2, 2])

    with f_col1:
        selected_groups = st.multiselect(
            "Filtrar por Grupo(s):",
            options=available_groups,
            default=available_groups,
            help="Selecciona uno o varios grupos para visualizarlos en el concentrado."
        )

    with f_col2:
        filtro_parcial_master = st.selectbox(
            "Filtrar por Parcial:",
            ["Todos los Parciales", "Parcial 1", "Parcial 2", "Parcial 3", "Sin asignar"]
        )

    with f_col3:
        search_student = st.text_input("🔍 Buscar estudiante:", placeholder="Nombre...").strip()

    with f_col4:
        fill_option = st.selectbox("Valores sin entrega:", ["0.0", "N/A"])

    # Filtrar asignaciones por grupo(s)
    if selected_groups:
        active_master = all_assignments[all_assignments['Grupo'].isin(selected_groups)].copy()
    else:
        active_master = all_assignments.copy()

    # Filtrar por parcial si se seleccionó uno en específico
    if filtro_parcial_master != "Todos los Parciales":
        active_master = active_master[active_master['Parcial'] == filtro_parcial_master]

    if active_master.empty:
        st.warning("No se encontraron registros para los filtros seleccionados.")
        return

    # Calcular bloques para los datos filtrados
    block_summary = compute_student_block_grades(active_master)

    # Orden cronológico de las columnas de fecha
    date_order = (
        active_master.dropna(subset=['dt_entrega'])
        .sort_values('dt_entrega')['Fecha de entrega']
        .unique()
        .tolist()
    )
    for d in active_master['Fecha de entrega'].unique():
        if d not in date_order:
            date_order.append(d)

    # Construir tabla pivote con 'Grupo' y 'Nombre del estudiante' en las filas
    pivot_df = block_summary.pivot(
        index=['Grupo', 'Nombre del estudiante'],
        columns='Fecha de entrega',
        values='block_grade'
    ).reset_index()

    # Asegurar que las columnas de fecha sigan el orden cronológico
    existing_date_cols = [c for c in date_order if c in pivot_df.columns]
    column_arrangement = ['Grupo', 'Nombre del estudiante'] + existing_date_cols
    pivot_df = pivot_df[column_arrangement]

    # Búsqueda por nombre
    if search_student:
        pivot_df = pivot_df[pivot_df['Nombre del estudiante'].str.contains(search_student, case=False, na=False)]

    # Calcular promedio general
    numeric_only = pivot_df[existing_date_cols].fillna(0.0)
    pivot_df['Promedio General'] = numeric_only.mean(axis=1).round(1)

    # Métricas grupales
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total de Alumnos", len(pivot_df))
    with m2:
        st.metric("Bloques Evaluados", len(existing_date_cols))
    with m3:
        avg_g = pivot_df['Promedio General'].mean() if not pivot_df.empty else 0.0
        st.metric("Promedio General Grupal", f"{avg_g:.1f} / 10")
    with m4:
        aprob = (pivot_df['Promedio General'] >= 6.0).sum() if not pivot_df.empty else 0
        pct_aprob = (aprob / len(pivot_df) * 100) if len(pivot_df) > 0 else 0
        st.metric("Tasa de Aprobación", f"{pct_aprob:.0f}% ({aprob}/{len(pivot_df)})")

    st.write("")

    # Formateo de visualización
    display_pivot = pivot_df.copy()
    if fill_option == "N/A":
        for col in existing_date_cols:
            display_pivot[col] = display_pivot[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        display_pivot['Promedio General'] = display_pivot['Promedio General'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "0.0")
    else:
        for col in existing_date_cols:
            display_pivot[col] = display_pivot[col].fillna(0.0).map("{:.1f}".format)
        display_pivot['Promedio General'] = display_pivot['Promedio General'].fillna(0.0).map("{:.1f}".format)

    # Renderizar la tabla pivote con la columna Grupo visible
    st.dataframe(
        display_pivot,
        use_container_width=True,
        hide_index=True,
        height=min(550, 100 + len(display_pivot) * 35),
        column_config={
            "Grupo": st.column_config.TextColumn("Grupo", width="small"),
            "Nombre del estudiante": st.column_config.TextColumn("Nombre del estudiante", width="large"),
            "Promedio General": st.column_config.TextColumn("Promedio General", width="small")
        }
    )

    # Botones de exportación
    exp_c1, exp_c2, _ = st.columns([1.5, 1.5, 3])
    with exp_c1:
        csv_bytes = display_pivot.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 Descargar Concentrado (CSV)",
            data=csv_bytes,
            file_name=f"Concentrado_Calificaciones_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    with exp_c2:
        excel_buff = io.BytesIO()
        with pd.ExcelWriter(excel_buff, engine='openpyxl') as writer:
            display_pivot.to_excel(writer, index=False, sheet_name="Concentrado")
        st.download_button(
            label="📥 Descargar Concentrado (Excel)",
            data=excel_buff.getvalue(),
            file_name=f"Concentrado_Calificaciones_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.divider()

    # --------------------------------------------------------------------------
    # SECCIÓN 3: ADMIN DRILL-DOWN (INSPECCIÓN INDIVIDUAL DE ESTUDIANTE)
    # --------------------------------------------------------------------------
    st.markdown("### 🔍 Detalle Individual de Estudiante (Drill-Down)")
    st.caption("Selecciona a un estudiante para inspeccionar su dashboard individual exacto, con tareas, intentos, fechas y puntos.")

    # Estudiantes disponibles según el filtro de grupos
    candidate_students_df = all_assignments[all_assignments['Grupo'].isin(selected_groups)] if selected_groups else all_assignments
    available_students = sorted(candidate_students_df['Nombre del estudiante'].dropna().unique())

    if not available_students:
        st.info("No hay estudiantes para los grupos seleccionados.")
        return

    drill_col1, drill_col2 = st.columns([3, 1])
    with drill_col1:
        selected_student = st.selectbox(
            "Selecciona un estudiante para inspeccionar en detalle:",
            options=available_students,
            key="admin_drilldown_student_select"
        )

    # Obtener grupo del estudiante seleccionado
    student_record = all_assignments[all_assignments['Nombre del estudiante'] == selected_student]
    student_group = student_record['Grupo'].iloc[0] if not student_record.empty else "N/A"

    with drill_col2:
        st.write("")
        st.write("")
        st.info(f"**Grupo:** {student_group}")

    # Renderizar la vista idéntica que ve el estudiante
    student_tasks_data = all_assignments[all_assignments['Nombre del estudiante'] == selected_student].copy()
    render_student_dashboard(selected_student, student_tasks_data, is_admin_drilldown=True)


# ==============================================================================
# VISTA: ESTUDIANTE (DASHBOARD PERSONALIZADO)
# ==============================================================================
def render_student():
    student_name = st.session_state.get('student_name', '')
    username = st.session_state.get('username', '')

    # Encabezado principal
    header_col1, header_col2 = st.columns([5, 1])
    with header_col1:
        all_assignments = load_assignments()
        student_tasks = all_assignments[all_assignments['Nombre del estudiante'].str.strip() == student_name.strip()]
        student_group = student_tasks['Grupo'].iloc[0] if not student_tasks.empty else ""

        st.markdown(f"""
        <div class="main-header">
            <h1>🎓 Calificaciones: {student_name}</h1>
            <p>Grupo: <strong>{student_group}</strong> | Usuario: <code>{username}</code> | Materia: Temas Selectos de Matemáticas II</p>
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if all_assignments.empty:
        st.warning("No hay tareas registradas en el sistema. Contacta al docente.")
        return

    # Renderizar dashboard reutilizable
    render_student_dashboard(student_name, student_tasks, is_admin_drilldown=False)


# ==============================================================================
# CONTROLADOR PRINCIPAL
# ==============================================================================
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['username'] = None
        st.session_state['student_name'] = None

    if not st.session_state['logged_in']:
        render_login()
    else:
        if st.session_state.get('role') == 'admin':
            render_admin()
        else:
            render_student()


if __name__ == "__main__":
    main()
