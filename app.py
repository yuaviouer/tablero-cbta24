"""
Portal de Calificaciones Khan Academy - CBTA 24
Sincronización con Google Drive API & Gestión Multimateria
"""

import os
import io
import json
import glob
import html
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
import time
import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

# ==============================================================================
# CONFIGURACIÓN GENERAL Y ESTILOS
# ==============================================================================
st.set_page_config(
    page_title="Portal de Calificaciones - CBTA 24",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Constante del directorio raíz en Google Drive
ROOT_FOLDER_ID = '1vXexz6nj_fa5lUtWOaFMqvCv3uRJyORJ'

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")

# Zona horaria del plantel: el servidor (p. ej. Streamlit Cloud) corre en UTC,
# lo que desfasaba 6 horas la detección de tareas "Programadas".
LOCAL_TZ = ZoneInfo("America/Mexico_City")


def now_local():
    """Fecha y hora actual en la zona horaria del plantel (sin tzinfo, igual que las fechas de Khan)."""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def get_secret(key, default=None):
    """Lee un valor de st.secrets sin fallar si no existe secrets.toml."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default


# Credenciales del administrador maestro: se leen de st.secrets o variables de entorno.
# Si no están configuradas, el acceso de administrador maestro queda deshabilitado
# (antes existía una contraseña por defecto pública en el código).
ADMIN_USERNAME = get_secret("ADMIN_USER") or os.environ.get("ADMIN_USER", "")
ADMIN_PASSWORD = get_secret("ADMIN_PASS") or os.environ.get("ADMIN_PASS", "")

# Diccionario de traducción de meses en español a inglés
SPANISH_TO_ENGLISH_MONTHS = {
    'ene': 'Jan', 'enero': 'Jan',
    'feb': 'Feb', 'febrero': 'Feb',
    'mar': 'Mar', 'marzo': 'Mar',
    'abr': 'Apr', 'abril': 'Apr',
    'may': 'May', 'mayo': 'May',
    'jun': 'Jun', 'junio': 'Jun',
    'jul': 'Jul', 'julio': 'Jul',
    'ago': 'Aug', 'agosto': 'Aug',
    'sep': 'Sep', 'sept': 'Sep', 'set': 'Sep', 'septiembre': 'Sep', 'setiembre': 'Sep',
    'oct': 'Oct', 'octubre': 'Oct',
    'nov': 'Nov', 'noviembre': 'Nov',
    'dic': 'Dec', 'diciembre': 'Dec'
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
    /* Vista del alumno */
    .hero-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 6px solid #2563eb;
        border-radius: 12px;
        padding: 20px 22px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        color: #0f172a;
    }
    .hero-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
    .hero-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600; }
    .hero-grade { font-size: 3rem; font-weight: 800; line-height: 1.1; color: #0f172a; }
    .hero-grade span { font-size: 1.1rem; font-weight: 600; color: #64748b; }
    .hero-status { padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 0.95rem; white-space: nowrap; }
    .hero-msg { margin-top: 12px; font-size: 1rem; line-height: 1.5; color: #334155; }
    .task-card {
        display: flex; justify-content: space-between; align-items: center; gap: 12px;
        background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #2563eb;
        border-radius: 8px; padding: 10px 14px; margin: 0 0 8px 0; color: #0f172a;
    }
    .task-title { font-weight: 600; font-size: 0.95rem; }
    .task-meta { font-size: 0.82rem; color: #64748b; margin-top: 2px; }
    .task-right { text-align: right; font-size: 0.8rem; color: #64748b; white-space: nowrap; }
    .task-right strong { font-size: 0.95rem; color: #0f172a; }
    .mini-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 14px; }
    .mini-stat { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; color: #0f172a; }
    .mini-label { font-size: 0.75rem; color: #64748b; font-weight: 600; }
    .mini-val { font-size: 1.5rem; font-weight: 700; line-height: 1.2; }
    .mini-val small { font-size: 0.75rem; font-weight: 500; color: #64748b; }
    .mini-val small.delta-up { color: #15803d; font-weight: 700; }
    .mini-val small.delta-down { color: #b91c1c; font-weight: 700; }
    .mini-sub { font-size: 0.75rem; color: #475569; margin-top: 2px; line-height: 1.3; }
    .teacher-stats { grid-template-columns: repeat(4, 1fr); }
    .student-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 10px; margin-bottom: 10px; }
    .student-card {
        background: #ffffff; border: 1px solid #e2e8f0; border-left: 5px solid #2563eb;
        border-radius: 10px; padding: 12px 14px; color: #0f172a;
    }
    .student-card ul { margin: 4px 0 0 0; padding-left: 18px; font-size: 0.85rem; color: #334155; }
    .student-card li { margin: 1px 0; }
    .sc-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
    .sc-name { font-weight: 700; font-size: 0.95rem; display: block; }
    .sc-meta { font-size: 0.8rem; color: #64748b; }
    .sc-badge { padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; white-space: nowrap; }
    .pair-row { display: grid; grid-template-columns: 1fr auto 1fr; gap: 8px; align-items: center; margin-top: 4px; }
    .pair-row .sc-label, .pair-row .sc-name, .pair-row .sc-meta { display: block; }
    .pair-arrow { font-size: 1.3rem; color: #64748b; }
    .sc-body { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px; }
    .sc-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b; font-weight: 700; }
    .badge-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
    .badge-card {
        background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
        padding: 12px; text-align: center; color: #0f172a;
    }
    .badge-card.earned { border-color: #86efac; background: #f0fdf4; }
    .badge-card.locked { opacity: 0.6; }
    .badge-card.locked .badge-icon { filter: grayscale(1); }
    .badge-icon { font-size: 1.8rem; }
    .badge-title { font-weight: 700; font-size: 0.9rem; margin-top: 4px; }
    .badge-state { font-size: 0.72rem; color: #64748b; margin: 2px 0 4px 0; }
    .badge-desc { font-size: 0.78rem; color: #475569; line-height: 1.35; }
    @media (max-width: 640px) {
        .main-header { padding: 16px 18px; }
        .main-header h1 { font-size: 1.3rem; }
        .main-header p { font-size: 0.85rem; }
        .hero-grade { font-size: 2.4rem; }
        .stat-val { font-size: 1.4rem; }
        .badge-grid { grid-template-columns: repeat(2, 1fr); }
        .mini-val { font-size: 1.2rem; }
        .mini-stat { padding: 8px; }
        .teacher-stats { grid-template-columns: repeat(2, 1fr); }
        .student-cards { grid-template-columns: 1fr; }
        .sc-body { grid-template-columns: 1fr; }
    }
.topic-list { display: flex; flex-direction: column; gap: 10px; margin: 6px 0 14px; }
.topic-row { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; }
.topic-head { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.topic-name { font-weight: 600; color: #0f172a; }
.topic-pct { font-weight: 600; font-size: 0.9rem; }
.topic-meta { color: #64748b; font-size: 0.85rem; }
.topic-track { height: 10px; background: #f1f5f9; border-radius: 6px; overflow: hidden; }
.topic-fill { height: 100%; border-radius: 6px; }
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
    """Configuración predeterminada de fechas dinámicas para los 3 Parciales del ciclo."""
    now = now_local()
    # En enero seguimos dentro del semestre agosto-enero que inició el año anterior
    now_year = now.year - 1 if now.month == 1 else now.year
    next_year = now_year + 1
    return {
        'Parcial 1': {'start': f'{now_year}-08-15', 'end': f'{now_year}-10-03'},
        'Parcial 2': {'start': f'{now_year}-10-04', 'end': f'{now_year}-11-21'},
        'Parcial 3': {'start': f'{now_year}-11-22', 'end': f'{next_year}-01-23'}
    }


def parse_parciales_dates(parciales_cfg):
    """
    Convierte cadenas 'YYYY-MM-DD' o date objects de los parciales en datetime.date válidos.
    Aplica fallback a las fechas por defecto del ciclo escolar actual si falta o es inválido.
    """
    defaults = get_default_parciales_config()
    result = {}
    for p in ['Parcial 1', 'Parcial 2', 'Parcial 3']:
        cfg = parciales_cfg.get(p, {}) if isinstance(parciales_cfg, dict) else {}
        st_raw = cfg.get('start', defaults[p]['start'])
        en_raw = cfg.get('end', defaults[p]['end'])

        try:
            st_d = date.fromisoformat(str(st_raw).strip()) if not isinstance(st_raw, (date, datetime)) else (st_raw.date() if isinstance(st_raw, datetime) else st_raw)
        except Exception:
            st_d = date.fromisoformat(defaults[p]['start'])

        try:
            en_d = date.fromisoformat(str(en_raw).strip()) if not isinstance(en_raw, (date, datetime)) else (en_raw.date() if isinstance(en_raw, datetime) else en_raw)
        except Exception:
            en_d = date.fromisoformat(defaults[p]['end'])

        result[p] = {'start': st_d, 'end': en_d}
    return result


def assign_parciales_vectorized(df, parcial_config):
    """
    CRÍTICO: Asigna la etiqueta 'Parcial' a cada actividad extrayendo .dt.date
    de la columna 'dt_entrega' (Timestamp de Pandas) y comparándola directamente
    contra los objetos datetime.date obtenidos de criterios.json con operadores >= y <=.
    Soporta recibir el diccionario completo de criterios.json o directamente la sección 'parciales'.
    Si las fechas no están presentes o son inválidas, usa las fechas por defecto del semestre actual.
    """
    if df.empty:
        return df

    if 'dt_entrega' not in df.columns or not pd.api.types.is_datetime64_any_dtype(df['dt_entrega']):
        if 'Fecha de entrega' in df.columns:
            df['dt_entrega'] = pd.to_datetime(df['Fecha de entrega'], errors='coerce')
        elif 'dt_entrega' not in df.columns:
            df['Parcial'] = 'Sin asignar'
            return df

    if isinstance(parcial_config, dict) and 'parciales' in parcial_config:
        parciales_dict = parcial_config['parciales']
    elif isinstance(parcial_config, dict):
        parciales_dict = parcial_config
    else:
        parciales_dict = {}

    parsed_dates = parse_parciales_dates(parciales_dict)

    # Extracción explícita de datetime.date desde la columna Timestamp de Pandas
    task_dates = df['dt_entrega'].dt.date
    parcial_series = pd.Series('Sin asignar', index=df.index, dtype='object')

    for p_name in ['Parcial 1', 'Parcial 2', 'Parcial 3']:
        cfg = parsed_dates.get(p_name, {})
        start_d = cfg.get('start')
        end_d = cfg.get('end')

        if start_d is not None and end_d is not None:
            # Comparación directa de fechas (datetime.date vs datetime.date)
            mask = (task_dates >= start_d) & (task_dates <= end_d)
            parcial_series[mask] = p_name

    df['Parcial'] = parcial_series
    return df


# ==============================================================================
# IDENTIFICACIÓN DE GRUPO
# ==============================================================================
def extract_group(filename):
    """
    Extrae el identificador de grupo a partir del nombre de archivo.
    Busca patrones como '5°H', '5° H', '5H', '5-H', '5° F', '5F', '5° G', etc.
    """
    base_name = os.path.basename(filename)
    match = re.search(r'([1-6])[\s°º\-_]*([A-Za-z])(?=[^a-zA-Z]|$)', base_name)
    if match:
        digit, letter = match.groups()
        return f"{digit}°{letter.upper()}"
    return os.path.splitext(base_name)[0]


# ==============================================================================
# PARSER DE FECHAS AGRESIVO PERSONALIZADO PARA KHAN ACADEMY
# ==============================================================================
def parse_khan_date(val, default_year=None):
    """
    Limpia agresivamente la cadena de fecha de Khan Academy:
    - Remueve 'º', '°', 'ª'
    - Traduce abreviaturas y nombres de meses en español a inglés
    - Determina dinámicamente el año actual (zona horaria del plantel)
    - Aplica lógica inteligente de cambio de año (crossover):
      Si el mes parseado es entre enero y julio (1-7) y el mes actual es entre agosto y diciembre (8-12),
      suma 1 al año para manejar correctamente los semestres interanuales (agosto-enero).
    - Convierte a pd.Timestamp con formato mixto y manejo robusto de errores
    """
    if pd.isna(val) or not str(val).strip():
        return pd.NaT

    s = str(val).strip()

    # 1. Quitar símbolos de grado u ordinales
    s = re.sub(r'[º°ª]', '', s)

    # 2. Reemplazar nombres y abreviaturas de meses en español por inglés
    def replace_month(match):
        m = match.group(1).lower()
        return SPANISH_TO_ENGLISH_MONTHS.get(m, match.group(1))

    s = re.sub(r'\b([a-záéíóú]{3,10})\.?', replace_month, s, flags=re.IGNORECASE)

    # 3. Normalizar espacios
    s = re.sub(r'\s+', ' ', s).strip()

    # 4. Determinar año dinámicamente con lógica inteligente de crossover
    now = now_local()
    now_year = now.year if default_year is None else default_year
    now_month = now.month

    # Identificar el número de mes a partir de la cadena traducida
    month_match = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', s, re.IGNORECASE)
    parsed_month_num = None
    if month_match:
        m_name = month_match.group(1).capitalize()
        month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                     'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        parsed_month_num = month_map.get(m_name)

    # Si la cadena no contiene ya un año de 4 dígitos:
    if not re.search(r'\b(20\d\d)\b', s):
        target_year = now_year
        # Crossover: si el mes es de enero a julio (1 a 7) y estamos en agosto a diciembre (8 a 12)
        # la fecha pertenece al año siguiente; si estamos en enero y el mes es de agosto a diciembre,
        # la fecha pertenece al año anterior (mismo semestre agosto-enero).
        if parsed_month_num is not None:
            if 1 <= parsed_month_num <= 7 and 8 <= now_month <= 12:
                target_year = now_year + 1
            elif 8 <= parsed_month_num <= 12 and now_month == 1:
                target_year = now_year - 1

        # Insertar año después del día y antes de la hora
        s = re.sub(r'([A-Za-z]+\s+\d{1,2})([,\s]+)', rf'\1 {target_year}\2', s)
        if not re.search(r'\b(20\d\d)\b', s):
            s = f"{s} {target_year}"

    try:
        return pd.to_datetime(s, format='mixed', errors='coerce')
    except Exception:
        return pd.NaT


# ==============================================================================
# GESTIÓN Y CONFIGURACIÓN DINÁMICA DE CRITERIOS DE EVALUACIÓN
# ==============================================================================
def get_default_criteria_config(unique_task_types=None):
    """
    Genera criterios de evaluación predeterminados para los tipos de tareas detectados:
    - Ejercicios / Pruebas / Cuestionarios: multiplicados por aciertos, evalúan intentos (máx 3 libres).
    - Artículos: 2.0 pts a tiempo, 0.2 tardío, puntaje plano, sin evaluación de intentos.
    - Videos: 1.0 pto a tiempo, 0.1 tardío, puntaje plano, sin evaluación de intentos.
    - Otros: 1.0 pto a tiempo, 0.1 tardío, puntaje plano, sin evaluación de intentos.
    """
    if not unique_task_types:
        unique_task_types = ['Video', 'Ejercicio', 'Artículo']
    defaults = {}
    for t in unique_task_types:
        t_clean = t.lower()
        if any(w in t_clean for w in ['ejercicio', 'cuestionario', 'prueba', 'quiz', 'examen']):
            defaults[t] = {
                'valor_a_tiempo': 1.0,
                'valor_tardio': 0.1,
                'multiplicar_por_aciertos': True,
                'evaluar_intentos': True,
                'max_intentos': 3
            }
        elif 'art' in t_clean:
            defaults[t] = {
                'valor_a_tiempo': 2.0,
                'valor_tardio': 0.2,
                'multiplicar_por_aciertos': False,
                'evaluar_intentos': False,
                'max_intentos': 1
            }
        elif 'video' in t_clean:
            defaults[t] = {
                'valor_a_tiempo': 1.0,
                'valor_tardio': 0.1,
                'multiplicar_por_aciertos': False,
                'evaluar_intentos': False,
                'max_intentos': 1
            }
        else:
            defaults[t] = {
                'valor_a_tiempo': 1.0,
                'valor_tardio': 0.1,
                'multiplicar_por_aciertos': False,
                'evaluar_intentos': False,
                'max_intentos': 1
            }
    return defaults


def get_default_teacher_criterios(unique_task_types=None, scale=10):
    """Retorna la configuración por defecto (Escala 10, Peso 100%, Umbrales estándar, Fechas de Parciales del ciclo)."""
    scale = 100 if scale == 100 else 10
    if scale == 100:
        thresh = {
            'excelente': 95.0,
            'bien': 80.0,
            'regular': 60.0,
            'en_riesgo': 60.0
        }
    else:
        thresh = {
            'excelente': 9.5,
            'bien': 8.0,
            'regular': 6.0,
            'en_riesgo': 6.0
        }
    return {
        'escala_maxima': scale,
        'peso_khan': 100,
        'thresholds': thresh,
        'parciales': get_default_parciales_config(),
        'task_criteria': get_default_criteria_config(unique_task_types),
        'componentes': dict(DEFAULT_COMPONENTES),
        'asistencia_minima': 80,
        'rubrica_evidencias': default_rubrica(),
        'criterios_por_grupo': False,
        'grupos': {}
    }


# Componentes adicionales de la calificación (además de Khan Academy, cuyo peso es 'peso_khan')
COMPONENTES = [
    ('evidencias', '📓 Evidencias (sellos)'),
    ('examen', '📝 Examen'),
    ('producto', '📦 Producto del parcial'),
    ('asistencia', '🙋 Asistencia'),
]
DEFAULT_COMPONENTES = {k: 0 for k, _ in COMPONENTES}


def khan_weight(cfg):
    """Peso de Khan en la calificación del parcial (se conserva aunque las vistas usen escala completa)."""
    cfg = cfg or {}
    return float(cfg.get('peso_khan_final', cfg.get('peso_khan', 100)))


def uses_components(cfg):
    return any(float(v) > 0 for v in ((cfg or {}).get('componentes') or {}).values())


def khan_view_config(cfg):
    """
    Con componentes activos, las vistas de Khan (inicio, concentrado, alumno) muestran el promedio de Khan
    en escala completa: su peso solo se aplica en la calificación del parcial. Sin componentes, se conserva
    el comportamiento original (la ponderación de Khan escala sus calificaciones).
    """
    if not uses_components(cfg):
        return cfg
    return {**cfg, 'peso_khan': 100, 'peso_khan_final': khan_weight(cfg)}


def group_overrides(cfg, grupo, parcial=None):
    """Criterios propios guardados para el grupo (y el parcial), o None si usa los generales."""
    cfg = cfg if isinstance(cfg, dict) else {}
    if not cfg.get('criterios_por_grupo') or not grupo:
        return None
    over = (cfg.get('grupos') or {}).get(str(grupo))
    if not over:
        return None
    p_over = (over.get('parciales') or {}).get(parcial) if parcial else None
    return {
        'peso_khan': float((p_over or over).get('peso_khan', over.get('peso_khan', 100))),
        'componentes': {**DEFAULT_COMPONENTES, **((p_over or over).get('componentes') or over.get('componentes') or {})},
        'thresholds': over.get('thresholds'),
        'del_parcial': bool(p_over),
    }


def group_config(cfg, grupo=None, parcial=None):
    """
    Criterios que aplican a un grupo (y parcial) cuando el docente los define por grupo: peso de Khan,
    componentes y umbrales de clasificación. La escala, las fechas, la asistencia mínima y la rúbrica
    son las mismas para todos. Regresa la configuración en formato de vista (ver khan_view_config).
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    over = group_overrides(cfg, grupo, parcial)
    if not over:
        return cfg
    base = {k: v for k, v in cfg.items() if k != 'peso_khan_final'}
    base['peso_khan'] = over['peso_khan']
    base['componentes'] = over['componentes']
    if over['thresholds']:
        base['thresholds'] = {**(cfg.get('thresholds') or {}), **over['thresholds']}
    return khan_view_config(base)


def classify_for(score, cfg, grupo=None):
    """Clasificación con los umbrales del grupo (si tiene criterios propios)."""
    g_cfg = group_config(cfg, grupo)
    return classify_student(score, g_cfg.get('thresholds', {}), g_cfg.get('escala_maxima', 10))


@st.cache_data(ttl=3600)
def load_teacher_criterios(folder_id, unique_task_types=None):
    """
    Carga la configuración persistente e independiente del docente ('criterios.json')
    desde su subcarpeta en Google Drive.
    Si no existe o es incompleto, retorna los valores predeterminados (Escala 10, Peso 100%, Parciales por defecto, etc.).
    """
    defaults = get_default_teacher_criterios(unique_task_types, scale=10)
    service = get_drive_service()

    # 1. Intentar cargar desde Google Drive si hay carpeta y servicio
    if service and folder_id and not str(folder_id).startswith('PEGA_AQUÍ'):
        try:
            item = find_drive_item(service, "criterios.json", folder_id, is_folder=False)
            if item:
                content = download_drive_bytes(service, item['id'])
                if content:
                    saved = json.loads(content.decode('utf-8'))
                    scale = int(saved.get('escala_maxima', 10))
                    peso = float(saved.get('peso_khan', 100))
                    thresholds = saved.get('thresholds', defaults['thresholds'])
                    parciales = saved.get('parciales', defaults['parciales'])
                    task_crit = saved.get('task_criteria', saved.get('criterios', {}))

                    merged_tasks = get_default_criteria_config(unique_task_types)
                    if isinstance(task_crit, dict):
                        for t, vals in task_crit.items():
                            if t in merged_tasks and isinstance(vals, dict):
                                merged_tasks[t].update(vals)
                            else:
                                merged_tasks[t] = vals

                    return {
                        'escala_maxima': scale,
                        'peso_khan': peso,
                        'thresholds': thresholds,
                        'parciales': parciales,
                        'task_criteria': merged_tasks,
                        'componentes': {**DEFAULT_COMPONENTES, **(saved.get('componentes') or {})},
                        'asistencia_minima': float(saved.get('asistencia_minima', 80)),
                        'rubrica_evidencias': saved.get('rubrica_evidencias') or default_rubrica(),
                        'criterios_por_grupo': bool(saved.get('criterios_por_grupo', False)),
                        'grupos': saved.get('grupos') if isinstance(saved.get('grupos'), dict) else {}
                    }
        except Exception as e:
            st.warning(f"No se pudo leer criterios.json desde Google Drive (se usarán valores por defecto): {e}")

    # 2. Fallback local en DATA_DIR
    local_path = os.path.join(DATA_DIR, "criterios.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            scale = int(saved.get('escala_maxima', 10))
            peso = float(saved.get('peso_khan', 100))
            thresholds = saved.get('thresholds', defaults['thresholds'])
            parciales = saved.get('parciales', defaults['parciales'])
            task_crit = saved.get('task_criteria', saved.get('criterios', {}))
            merged_tasks = get_default_criteria_config(unique_task_types)
            if isinstance(task_crit, dict):
                for t, vals in task_crit.items():
                    if t in merged_tasks and isinstance(vals, dict):
                        merged_tasks[t].update(vals)
                    else:
                        merged_tasks[t] = vals
            return {
                'escala_maxima': scale,
                'peso_khan': peso,
                'thresholds': thresholds,
                'parciales': parciales,
                'task_criteria': merged_tasks,
                'componentes': {**DEFAULT_COMPONENTES, **(saved.get('componentes') or {})},
                'asistencia_minima': float(saved.get('asistencia_minima', 80)),
                'rubrica_evidencias': saved.get('rubrica_evidencias') or default_rubrica(),
                'criterios_por_grupo': bool(saved.get('criterios_por_grupo', False)),
                'grupos': saved.get('grupos') if isinstance(saved.get('grupos'), dict) else {}
            }
        except Exception:
            pass

    return defaults


def save_teacher_criterios(folder_id, criterios_dict):
    """
    Serializa la configuración del docente a JSON (criterios.json) y la guarda/sobrescribe
    DIRECTAMENTE en su carpeta específica de Google Drive usando MediaIoBaseUpload.
    También mantiene una copia local de respaldo y limpia el caché.
    Retorna una tupla (nivel, mensaje) para mostrarse después de recargar la página.
    """
    serializable = dict(criterios_dict)
    if 'parciales' in serializable and isinstance(serializable['parciales'], dict):
        p_clean = {}
        for p_name, p_dates in serializable['parciales'].items():
            if isinstance(p_dates, dict):
                p_clean[p_name] = {
                    'start': p_dates['start'].isoformat() if hasattr(p_dates.get('start'), 'isoformat') else str(p_dates.get('start', '')),
                    'end': p_dates['end'].isoformat() if hasattr(p_dates.get('end'), 'isoformat') else str(p_dates.get('end', ''))
                }
            else:
                p_clean[p_name] = p_dates
        serializable['parciales'] = p_clean

    json_str = json.dumps(serializable, indent=4, ensure_ascii=False, default=str)
    json_bytes = json_str.encode('utf-8')

    # Guardar en local como respaldo
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "criterios.json"), "w", encoding="utf-8") as f:
            f.write(json_str)
    except Exception:
        pass

    result = ('success', "✅ Configuración guardada localmente (criterios.json).")

    # Guardar / Sobrescribir en Google Drive
    service = get_drive_service()
    if service and folder_id and not str(folder_id).startswith('PEGA_AQUÍ'):
        try:
            existing = find_drive_item(service, "criterios.json", folder_id, is_folder=False)
            media = MediaIoBaseUpload(io.BytesIO(json_bytes), mimetype='application/json', resumable=True)
            if existing:
                service.files().update(
                    fileId=existing['id'],
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
            else:
                meta = {
                    'name': 'criterios.json',
                    'parents': [folder_id]
                }
                service.files().create(
                    body=meta,
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
            result = ('success', "✅ Configuración y fechas de Parciales guardadas exitosamente en Google Drive (criterios.json).")
        except HttpError as e:
            if 'storage quota' in str(e).lower() or (getattr(e, 'resp', None) and e.resp.status == 403):
                result = ('warning', "⚠️ Nota: Tu cuenta de Google Drive no cuenta con cuota de escritura para Service Accounts institucionales. La configuración se ha guardado localmente en el servidor.")
            elif getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
                result = ('error', "⚠️ El servidor de Google Drive está experimentando alto tráfico. Por favor, intenta de nuevo en unos momentos.")
            else:
                result = ('error', f"Error al guardar criterios.json en Google Drive: {e}")
        except Exception as e:
            result = ('error', f"Error inesperado al guardar criterios.json en Google Drive: {e}")

    # Solo se recarga la configuración (no los reportes ni las listas, que no cambiaron)
    load_teacher_criterios.clear()
    return result


def set_flash(level, message):
    """Guarda un mensaje para mostrarlo después de st.rerun() (si no, se pierde al recargar)."""
    st.session_state['_flash'] = (level, message)


def show_flash():
    """Muestra (una sola vez) el mensaje pendiente guardado con set_flash."""
    # El contenedor se crea siempre (aunque no haya mensaje) para que los elementos de abajo no cambien de
    # posición entre recargas: si se movieran, Streamlit regresaría las pestañas abiertas a la primera.
    box = st.container()
    flash = st.session_state.pop('_flash', None)
    if flash:
        level, message = flash
        getattr(box, level, box.info)(message)


# Prefijos de las claves de widgets del panel de configuración. Se borran al guardar o
# restablecer para que los controles muestren los valores recién guardados.
CONFIG_WIDGET_PREFIXES = ('cfg_', 'th_', 'crit_')


def reset_config_widgets():
    for k in list(st.session_state.keys()):
        if str(k).startswith(CONFIG_WIDGET_PREFIXES):
            del st.session_state[k]


def render_criteria_explanation(criteria_config):
    """Genera texto dinámico en formato Markdown explicando los criterios activos."""
    if isinstance(criteria_config, dict) and 'task_criteria' in criteria_config:
        task_crit = criteria_config['task_criteria']
        scale = criteria_config.get('escala_maxima', 10)
        weight = criteria_config.get('peso_khan', 100)
    else:
        task_crit = criteria_config if isinstance(criteria_config, dict) else {}
        scale = 10
        weight = 100

    md = ["### Sistema de Criterios de Evaluación Vigente\n"]
    for t_name, cfg in task_crit.items():
        v_ot = cfg.get('valor_a_tiempo', 1.0)
        v_lt = cfg.get('valor_tardio', 0.1)
        mult = cfg.get('multiplicar_por_aciertos', False)
        eval_int = cfg.get('evaluar_intentos', False)
        max_int = cfg.get('max_intentos', 3)

        if mult:
            rule_pts = f"**{v_ot:g} pto(s)** por acierto a tiempo | **{v_lt:g} pto(s)** por acierto tardío"
        else:
            rule_pts = f"**{v_ot:g} pto(s)** a tiempo | **{v_lt:g} pto(s)** tardío | 0 pts sin entrega"

        if eval_int:
            rule_int = f"Permite hasta **{max_int} intento(s) libre(s)**. A partir del {max_int + 1}º intento se resta 1 acierto por cada intento extra. Entrega tardía con más de {max_int} intentos = **0 puntos**."
        else:
            rule_int = "No se contabilizan ni penalizan intentos adicionales."

        md.append(f"- **{t_name}:** {rule_pts}. {rule_int}")

    md.append(f"\n- **Escala Máxima:** **{scale}** | **Ponderación de Khan Academy:** **{weight:g}%**")
    md.append(f"- **Fórmula del Bloque:** $\\left( \\frac{{\\sum \\text{{Puntos Ganados}}}}{{\\sum \\text{{Puntos Posibles}}}} \\right) \\times {scale} \\times \\left( \\frac{{{weight:g}}}{{100}} \\right)$, redondeado a 1 decimal.")
    return "\n".join(md)


# ==============================================================================
# MOTOR DE CALIFICACIÓN DINÁMICO
# ==============================================================================
NOT_EVALUATED_STATUSES = ('Programada', 'En curso')


def apply_dynamic_grading(df, criteria_config):
    """
    Aplica las reglas de calificación y penalización dinámicamente según criteria_config,
    sin recurrir a cadenas fijas ('Video', 'Artículo', etc.).
    """
    if df.empty:
        return df

    if isinstance(criteria_config, dict) and 'task_criteria' in criteria_config:
        cfg_dict = criteria_config['task_criteria']
    else:
        cfg_dict = criteria_config if isinstance(criteria_config, dict) else {}

    graded_rows = []
    cfg_lookup = {str(k).strip().lower(): v for k, v in cfg_dict.items()}
    now = now_local()

    for _, row in df.iterrows():
        raw_type = str(row.get('Tipo de tarea', '')).strip()
        cfg = cfg_lookup.get(raw_type.lower())
        if not cfg:
            cfg = {
                'valor_a_tiempo': 1.0,
                'valor_tardio': 0.1,
                'multiplicar_por_aciertos': False,
                'evaluar_intentos': False,
                'max_intentos': 1
            }

        start_dt = row.get('dt_inicio')
        due_dt = row.get('dt_entrega')
        comp_dt = row.get('dt_terminacion')

        is_future = pd.notna(start_dt) and (start_dt > now)

        raw_attempts = row.get('Número de intentos', '')
        try:
            if pd.isna(raw_attempts) or str(raw_attempts).strip() in ['', 'En progreso']:
                attempts = 0 if is_future else (1 if (pd.notna(comp_dt) and str(comp_dt).strip() != '') else 0)
            else:
                attempts = int(float(str(raw_attempts).strip()))
        except (ValueError, TypeError):
            attempts = 0

        evaluar_intentos = cfg.get('evaluar_intentos', False)
        max_intentos = int(cfg.get('max_intentos', 3))

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

        valor_a_tiempo = float(cfg.get('valor_a_tiempo', 1.0))
        valor_tardio = float(cfg.get('valor_tardio', 0.1))
        multiplicar = bool(cfg.get('multiplicar_por_aciertos', False))

        # Valor de la actividad si se entrega completa (usado para proyecciones del alumno).
        # Si el alumno no ha abierto el ejercicio, Khan no reporta sus preguntas: se usa el
        # número de preguntas del mismo ejercicio en las filas de sus compañeros.
        known_total = total_q
        if known_total <= 0:
            try:
                fallback_total = float(row.get('_preguntas_tarea', 0))
                known_total = fallback_total if fallback_total > 0 else 0.0
            except (ValueError, TypeError):
                known_total = 0.0
        if multiplicar and known_total > 0:
            potential_max = valor_a_tiempo * known_total
            potential_on_time = valor_a_tiempo * known_total
            potential_late = valor_tardio * known_total
        elif multiplicar:
            # Sin ningún dato del número de preguntas: se proyecta con el valor base.
            potential_max = valor_a_tiempo
            potential_on_time = valor_a_tiempo
            potential_late = valor_tardio
        else:
            potential_max = valor_a_tiempo
            potential_on_time = valor_a_tiempo
            potential_late = valor_tardio

        is_completed = (not is_future) and pd.notna(comp_dt) and str(comp_dt).strip() != ''
        # Actividad iniciada, sin entregar y cuya fecha de entrega aún no llega:
        # todavía no se evalúa (antes contaba como 0 aunque el alumno tuviera tiempo).
        is_in_progress = (not is_future) and (not is_completed) and pd.notna(due_dt) and (due_dt > now)

        if is_future:
            # Tarea futura (no iniciada): se fijan Max Points y Earned Points a 0
            # para no tener ningún peso matemático sobre el promedio del bloque
            earned_pts = 0.0
            max_pts = 0.0
            status = 'Programada'
            obs = 'Programada (no iniciada)'
            is_late = False
        elif is_in_progress:
            earned_pts = 0.0
            max_pts = 0.0
            status = 'En curso'
            obs = 'En curso (aún no vence)'
            is_late = False
        else:
            is_late = is_completed and pd.notna(due_dt) and (comp_dt > due_dt)

            if evaluar_intentos:
                penalty_attempts = max(0, attempts - max_intentos)
            else:
                penalty_attempts = 0

            effective_correct = max(0.0, correct_q - penalty_attempts)

            if not is_completed:
                earned_pts = 0.0
                status = 'No completado'
                obs = 'Sin entrega'
                # Con el número de preguntas conocido (propio o de sus compañeros), el ejercicio
                # sin entregar pesa lo mismo que para el resto del grupo.
                max_pts = (valor_a_tiempo * known_total) if (multiplicar and known_total > 0) else valor_a_tiempo

            elif is_late and evaluar_intentos and attempts > max_intentos:
                earned_pts = 0.0
                status = f'Tardía (>{max_intentos} intentos)'
                obs = f'Tardía + >{max_intentos} intentos (0 pts)'
                max_pts = (valor_a_tiempo * known_total) if (multiplicar and known_total > 0) else valor_a_tiempo

            elif is_late:
                chosen_val = valor_tardio
                status = 'Tardía'
                if multiplicar:
                    max_pts = (valor_a_tiempo * total_q) if total_q > 0 else valor_a_tiempo
                    earned_pts = min(chosen_val * effective_correct, chosen_val * total_q) if total_q > 0 else 0.0
                    obs = f'Entrega tardía ({chosen_val:.2f} pts/acierto)'
                else:
                    max_pts = valor_a_tiempo
                    earned_pts = chosen_val
                    obs = f'Completado tardío ({chosen_val:.1f} / {valor_a_tiempo:.1f} pts)'

            else:
                chosen_val = valor_a_tiempo
                if penalty_attempts > 0:
                    status = 'A tiempo (con penalización)'
                    obs = f'-{penalty_attempts} acierto(s) por {attempts} intentos (máx. {max_intentos})'
                else:
                    status = 'A tiempo'
                    obs = 'A tiempo (sin penalización)' if multiplicar else f'Completado a tiempo ({chosen_val:.1f} / {valor_a_tiempo:.1f} pts)'

                if multiplicar:
                    max_pts = (valor_a_tiempo * total_q) if total_q > 0 else valor_a_tiempo
                    earned_pts = min(chosen_val * effective_correct, chosen_val * total_q) if total_q > 0 else 0.0
                else:
                    max_pts = valor_a_tiempo
                    earned_pts = chosen_val

        graded_rows.append({
            'earned_points': round(earned_pts, 2),
            'max_points': round(max_pts, 2),
            'status': status,
            'observations': obs,
            'attempts_count': attempts,
            'correct_count': int(correct_q) if pd.notna(correct_q) else 0,
            'total_count': int(total_q) if pd.notna(total_q) else 0,
            'is_completed': is_completed,
            'is_late': is_late,
            'is_future': is_future,
            'is_in_progress': is_in_progress,
            'evaluar_intentos': evaluar_intentos,
            'max_intentos': max_intentos,
            'potential_max': round(potential_max, 2),
            'potential_on_time': round(potential_on_time, 2),
            'potential_late': round(potential_late, 2),
            'per_correct_on_time': valor_a_tiempo if (multiplicar and known_total > 0) else None,
            'per_correct_late': valor_tardio if (multiplicar and known_total > 0) else None,
            'questions_known': int(known_total) if known_total > 0 else 0
        })

    graded_df = pd.DataFrame(graded_rows, index=df.index)
    result_df = df.copy()
    for col in graded_df.columns:
        result_df[col] = graded_df[col]
    return result_df



# ==============================================================================
# CLASIFICACIÓN DE RENDIMIENTO DEL ESTUDIANTE (ESTATUS)
# ==============================================================================
def classify_student(score, thresholds=None, scale=10):
    """
    Clasifica el rendimiento del estudiante según su promedio general
    usando los umbrales configurados por el docente:
    - 'Excelente': >= min_excelente
    - 'Bien': >= min_bien
    - 'Regular': >= min_regular
    - 'En riesgo': < min_regular
    """
    if pd.isna(score):
        return 'En riesgo'
    try:
        val = float(score)
    except (ValueError, TypeError):
        return 'En riesgo'

    scale = int(scale) if scale else 10
    if thresholds and isinstance(thresholds, dict):
        th_exc = float(thresholds.get('excelente', 9.5 if scale == 10 else 95.0))
        th_bien = float(thresholds.get('bien', 8.0 if scale == 10 else 80.0))
        th_reg = float(thresholds.get('regular', 6.0 if scale == 10 else 60.0))
    else:
        th_exc = 9.5 if scale == 10 else 95.0
        th_bien = 8.0 if scale == 10 else 80.0
        th_reg = 6.0 if scale == 10 else 60.0

    if val >= th_exc:
        return 'Excelente'
    elif val >= th_bien:
        return 'Bien'
    elif val >= th_reg:
        return 'Regular'
    else:
        return 'En riesgo'


# ==============================================================================
# INTEGRACIÓN CON GOOGLE DRIVE API (SERVICE ACCOUNT & MEMORY PROCESSING)
# ==============================================================================
@st.cache_resource
def get_drive_service():
    """
    Inicializa y cachea el cliente de Google Drive API v3 usando
    las credenciales del Service Account en st.secrets['gcp_service_account'].
    """
    raw_creds = get_secret('gcp_service_account')
    if raw_creds is None:
        return None
    try:
        if isinstance(raw_creds, str):
            creds_dict = json.loads(raw_creds)
        elif isinstance(raw_creds, dict):
            creds_dict = raw_creds
        else:
            creds_dict = dict(raw_creds)

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"Error al inicializar las credenciales de Google Drive: {e}")
        return None


def generate_credentials_template_bytes():
    """
    Genera un archivo Excel (.xlsx) en memoria con la estructura exacta
    requerida para las credenciales de los alumnos:
    - Usuario: Nombre de usuario de Khan Academy
    - Contraseña: Password asignada
    - Nombre del estudiante: Nombre completo del estudiante (para vincular con los CSVs)
    """
    sample_data = [
        {
            "Usuario": "alboresclementepaulo",
            "Contraseña": "Alumno2026*",
            "Nombre del estudiante": "ALBORES CLEMENTE PAULO CESAR"
        },
        {
            "Usuario": "gonzalezmartinezmaria",
            "Contraseña": "Alumno2026*",
            "Nombre del estudiante": "GONZÁLEZ MARTÍNEZ MARÍA FERNANDA"
        },
        {
            "Usuario": "hernandezlopezjuan",
            "Contraseña": "Alumno2026*",
            "Nombre del estudiante": "HERNÁNDEZ LÓPEZ JUAN PABLO"
        }
    ]
    df_template = pd.DataFrame(sample_data)
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine='openpyxl') as writer:
        df_template.to_excel(writer, index=False, sheet_name="Credenciales")
    return buff.getvalue()


def find_drive_item(service, name, parent_id, is_folder=None):
    """
    Busca un archivo o carpeta por nombre exacto dentro de una carpeta padre en Drive.
    """
    if not service or not parent_id or str(parent_id).startswith('PEGA_AQUÍ'):
        return None

    # Escapar comillas y diagonales para que nombres como "Matemáticas d'Arte" no rompan la consulta
    safe_name = str(name).replace('\\', '\\\\').replace("'", "\\'")
    query_parts = [
        f"'{parent_id}' in parents",
        f"name = '{safe_name}'",
        "trashed = false"
    ]
    if is_folder is True:
        query_parts.append("mimeType = 'application/vnd.google-apps.folder'")
    elif is_folder is False:
        query_parts.append("mimeType != 'application/vnd.google-apps.folder'")

    query = " and ".join(query_parts)
    try:
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType)',
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute(num_retries=3)
        files = results.get('files', [])
        if files:
            return files[0]
        return None
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error de Google Drive API al buscar '{name}': {e}")
        return None
    except Exception as e:
        st.error(f"Error al buscar '{name}' en Google Drive: {e}")
        return None


@st.cache_data(ttl=3600)
def get_cached_folder_id(folder_name):
    """
    Busca y cachea el ID de la subcarpeta del docente en Google Drive por 1 hora.
    Previene llamadas repetidas a Drive API durante la selección de docentes o el inicio de sesión.
    """
    if not folder_name or str(ROOT_FOLDER_ID).startswith('PEGA_AQUÍ'):
        return None
    try:
        service = get_drive_service()
        if not service:
            return None
        folder_item = find_drive_item(service, folder_name, ROOT_FOLDER_ID, is_folder=True)
        if folder_item:
            return folder_item['id']
        return None
    except Exception:
        return None


def download_drive_bytes(service, file_id):
    """
    Descarga el contenido de un archivo de Drive en memoria usando io.BytesIO.
    NO escribe nada en disco local (Zero Local Disk Storage).
    """
    if not service or not file_id:
        return None
    try:
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk(num_retries=3)
        return fh.getvalue()
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error de Google Drive API al descargar archivo: {e}")
        return None
    except Exception as e:
        st.error(f"Error al descargar archivo de Google Drive: {e}")
        return None



def read_drive_excel(service, file_id, dtype=None):
    """Lee un archivo Excel desde Google Drive directamente en un DataFrame en memoria."""
    try:
        content = download_drive_bytes(service, file_id)
        if content:
            return pd.read_excel(io.BytesIO(content), dtype=dtype)
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error al leer Excel de Drive: {e}")
    except Exception as e:
        st.error(f"Error al procesar archivo Excel desde Drive: {e}")
    return pd.DataFrame()


def read_drive_csv(service, file_id, dtype=None):
    """Lee un archivo CSV desde Google Drive directamente en un DataFrame en memoria."""
    try:
        content = download_drive_bytes(service, file_id)
        if not content:
            return pd.DataFrame()
        try:
            return pd.read_csv(io.BytesIO(content), encoding='utf-8-sig', dtype=dtype)
        except Exception:
            return pd.read_csv(io.BytesIO(content), encoding='latin-1', dtype=dtype)
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error al leer CSV de Drive: {e}")
    except Exception as e:
        st.error(f"Error al procesar archivo CSV desde Drive: {e}")
    return pd.DataFrame()


def list_drive_csvs(service, folder_id):
    """
    Lista los archivos CSV de tareas dentro de una carpeta de Drive,
    excluyendo credenciales y carpetas.
    """
    if not service or not folder_id or str(folder_id).startswith('PEGA_AQUÍ'):
        return []
    query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    try:
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, mimeType, modifiedTime)',
            orderBy='modifiedTime',
            pageSize=200,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute(num_retries=3)
        files = results.get('files', [])
        csv_files = [
            f for f in files
            if f.get('name', '').lower().endswith('.csv') and 'credencial' not in f.get('name', '').lower()
        ]
        return csv_files
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error de Google Drive API al listar archivos (Código {e.resp.status}): {e}")
        return []
    except Exception as e:
        st.error(f"Error al listar archivos CSV en Google Drive: {e}")
        return []


DOCENTES_COLS = ['usuario_docente', 'password', 'asignatura', 'carpeta_nombre', 'Nombre del Docente', 'e_mail', 'rol', 'grupos_tutoria']


@st.cache_data(ttl=3600)
def load_docentes_master():
    """
    Carga el archivo maestro docentes.xlsx ubicado en la carpeta raíz de Drive.
    Columnas requeridas: 'usuario_docente', 'password', 'asignatura', 'carpeta_nombre', 'Nombre del Docente', 'e_mail'.
    Opcionales: 'rol' (docente, tutor o directivo) y 'grupos_tutoria' (ej. "5°H, 5°J"; vacío o "todos" = todos los grupos).
    """
    default_empty = pd.DataFrame(columns=DOCENTES_COLS)
    try:
        service = get_drive_service()
        if not service or str(ROOT_FOLDER_ID).startswith('PEGA_AQUÍ'):
            return default_empty

        doc_file = find_drive_item(service, "docentes.xlsx", ROOT_FOLDER_ID, is_folder=False)
        if not doc_file:
            return default_empty

        df = read_drive_excel(service, doc_file['id'], dtype=str)
        if df.empty:
            return default_empty

        df.columns = [str(c).strip() for c in df.columns]
        rename_map = {}
        for col in df.columns:
            cl = col.lower().strip()
            if 'usuario' in cl:
                rename_map[col] = 'usuario_docente'
            elif cl.startswith('rol') or cl in ('perfil', 'cargo'):
                rename_map[col] = 'rol'
            elif 'grupo' in cl or 'tutor' in cl:
                rename_map[col] = 'grupos_tutoria'
            elif 'pass' in cl or 'contrase' in cl:
                rename_map[col] = 'password'
            elif 'asig' in cl or 'materia' in cl:
                rename_map[col] = 'asignatura'
            elif 'carpeta' in cl:
                rename_map[col] = 'carpeta_nombre'
            elif 'nombre' in cl and ('docente' in cl or 'profesor' in cl or 'maestro' in cl):
                rename_map[col] = 'Nombre del Docente'
            elif 'docente' in cl or 'profesor' in cl or 'maestro' in cl:
                rename_map[col] = 'Nombre del Docente'
            elif 'mail' in cl or 'correo' in cl:
                rename_map[col] = 'e_mail'
        df = df.rename(columns=rename_map)

        if 'Nombre del Docente' not in df.columns:
            df['Nombre del Docente'] = df.get('usuario_docente', 'Docente')
        if 'e_mail' not in df.columns:
            df['e_mail'] = ''

        for req in DOCENTES_COLS:
            if req not in df.columns:
                df[req] = ''
            else:
                df[req] = df[req].fillna('').astype(str).str.strip()

        # Descartar filas sin usuario o contraseña (evita accesos con contraseña vacía)
        df = df[(df['usuario_docente'] != '') & (df['password'] != '')].copy()
        if df.empty:
            return default_empty

        df['Nombre del Docente'] = df.apply(
            lambda r: r['Nombre del Docente'] if r['Nombre del Docente'].strip() else r['usuario_docente'],
            axis=1
        )

        df['rol'] = df['rol'].str.lower()
        return df[DOCENTES_COLS]
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error al cargar docentes desde Google Drive: {e}")
        return default_empty
    except Exception as e:
        st.error(f"Error al procesar docentes.xlsx: {e}")
        return default_empty


def normalize_credentials_df(df):
    """Normaliza las columnas de un dataframe de credenciales a ['Usuario', 'Contraseña', 'Nombre del estudiante']."""
    if df.empty:
        return pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
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
        for col in ['Usuario', 'Contraseña', 'Nombre del estudiante']:
            df[col] = df[col].fillna('').astype(str).str.strip()
        # Contraseñas numéricas leídas como float ("1234.0") se normalizan a "1234"
        df['Contraseña'] = df['Contraseña'].str.replace(r'^(\d+)\.0$', r'\1', regex=True)
        # Descartar filas sin usuario o sin contraseña (antes una celda vacía se convertía en la contraseña "nan")
        df = df[(df['Usuario'] != '') & (df['Contraseña'] != '')]
        return df[['Usuario', 'Contraseña', 'Nombre del estudiante']].drop_duplicates(subset=['Usuario'])
    return pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])


def parse_drive_time(value):
    """Convierte el modifiedTime de Drive (ISO en UTC) a hora local del plantel."""
    ts = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(ts):
        return pd.NaT
    return ts.tz_convert(LOCAL_TZ).tz_localize(None)


ASSIGNMENT_KEY_COLS = ['Grupo', 'Nombre del estudiante', 'Nombre de la tarea', 'Fecha de entrega']


def prepare_raw_assignments(dfs):
    """
    Une los CSVs de Khan Academy (ordenados del más antiguo al más reciente), limpia columnas,
    elimina tareas duplicadas conservando el reporte más reciente y parsea las fechas.
    """
    all_data = pd.concat(dfs, ignore_index=True)
    all_data.columns = [str(c).strip() for c in all_data.columns]

    for col in ['Nombre del estudiante', 'Tipo de tarea', 'Nombre de la tarea']:
        if col in all_data.columns:
            all_data[col] = all_data[col].astype(str).str.strip()

    # Si el mismo grupo se descargó más de una vez (o se subió el mismo archivo dos veces),
    # cada tarea aparecería repetida y alteraría los promedios: se conserva la versión más reciente.
    if set(ASSIGNMENT_KEY_COLS).issubset(all_data.columns):
        all_data = all_data.drop_duplicates(subset=ASSIGNMENT_KEY_COLS, keep='last').reset_index(drop=True)

    # Khan deja vacío el número de preguntas cuando el alumno no ha abierto el ejercicio.
    # Se toma de las filas de sus compañeros para proyectar correctamente cuánto vale.
    if {'Nombre de la tarea', 'Número total de preguntas'}.issubset(all_data.columns):
        totals = pd.to_numeric(all_data['Número total de preguntas'], errors='coerce')
        all_data['_preguntas_tarea'] = totals.where(totals > 0).groupby(all_data['Nombre de la tarea']).transform('max')

    date_sources = {
        'dt_entrega': 'Fecha de entrega',
        'dt_terminacion': 'Última fecha de terminación',
        'dt_inicio': 'Fecha de inicio',
    }
    for dt_col, src_col in date_sources.items():
        if src_col in all_data.columns:
            all_data[dt_col] = pd.to_datetime(all_data[src_col].apply(parse_khan_date), errors='coerce')
        else:
            all_data[dt_col] = pd.NaT
    return all_data


def load_credentials_local_fallback():
    """Fallback local para lectura de credenciales si Drive no está configurado."""
    os.makedirs(DATA_DIR, exist_ok=True)
    excel_path = os.path.join(DATA_DIR, "credenciales.xlsx")
    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path, dtype=str)
            return normalize_credentials_df(df)
        except Exception:
            pass
    csv_files = glob.glob(os.path.join(DATA_DIR, "*redencial*.csv"))
    if csv_files:
        dfs = []
        for cf in csv_files:
            try:
                tdf = pd.read_csv(cf, encoding='utf-8-sig', dtype=str)
                ndf = normalize_credentials_df(tdf)
                if not ndf.empty:
                    dfs.append(ndf)
            except Exception:
                continue
        if dfs:
            return pd.concat(dfs, ignore_index=True).drop_duplicates(subset=['Usuario'])
    return pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])


def load_raw_assignments_local_fallback():
    """Fallback local para lectura de tareas si Drive no está configurado."""
    os.makedirs(DATA_DIR, exist_ok=True)
    csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    assignment_files = sorted(
        (f for f in csv_files if "credencial" not in os.path.basename(f).lower()),
        key=os.path.getmtime
    )
    dfs = []
    for filepath in assignment_files:
        for encoding in ('utf-8-sig', 'latin-1'):
            try:
                df = pd.read_csv(filepath, encoding=encoding)
                break
            except Exception:
                df = None
        if df is None or df.empty:
            continue
        df['Archivo_Origen'] = os.path.basename(filepath)
        df['Grupo'] = extract_group(filepath)
        df['Archivo_Modificado'] = datetime.fromtimestamp(os.path.getmtime(filepath), LOCAL_TZ).replace(tzinfo=None)
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return prepare_raw_assignments(dfs)


@st.cache_data(ttl=3600)
def load_teacher_credentials(folder_id):
    """
    Carga las credenciales de los estudiantes desde la subcarpeta del docente en Google Drive.
    Busca 'credenciales.xlsx' o archivos que contengan 'credencial' (.xlsx o .csv) en memoria.
    """
    empty_creds = pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])
    try:
        service = get_drive_service()
        if not service or not folder_id or str(folder_id).startswith('PEGA_AQUÍ'):
            return load_credentials_local_fallback()

        # 1. Intentar credenciales.xlsx
        cred_file = find_drive_item(service, "credenciales.xlsx", folder_id, is_folder=False)
        if cred_file:
            df = read_drive_excel(service, cred_file['id'], dtype=str)
            norm_df = normalize_credentials_df(df)
            if not norm_df.empty:
                return norm_df

        # 2. Buscar otros archivos con 'credencial'
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            fields='files(id, name, mimeType)',
            pageSize=100,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute(num_retries=3)
        files = results.get('files', [])
        for f in files:
            fname = f.get('name', '').lower()
            if 'credencial' in fname:
                if fname.endswith('.xlsx'):
                    df = read_drive_excel(service, f['id'], dtype=str)
                elif fname.endswith('.csv'):
                    df = read_drive_csv(service, f['id'], dtype=str)
                else:
                    continue
                norm_df = normalize_credentials_df(df)
                if not norm_df.empty:
                    return norm_df

        return empty_creds
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error de Google Drive API al obtener credenciales: {e}")
        return empty_creds
    except Exception as e:
        st.error(f"Error al cargar las credenciales de los alumnos: {e}")
        return empty_creds


@st.cache_data(ttl=3600)
def load_teacher_raw_assignments(folder_id):
    """
    Descarga en memoria todos los CSVs de Khan Academy en la subcarpeta del docente en Google Drive,
    extrae el Grupo de cada archivo, y limpia y parsea fechas de Khan Academy.
    NO guarda nada en disco local.
    """
    try:
        service = get_drive_service()
        if not service or not folder_id or str(folder_id).startswith('PEGA_AQUÍ'):
            return load_raw_assignments_local_fallback()

        csv_items = list_drive_csvs(service, folder_id)
        if not csv_items:
            return pd.DataFrame()

        dfs = []
        for item in csv_items:
            file_id = item['id']
            file_name = item.get('name', 'asignacion.csv')
            df = read_drive_csv(service, file_id)
            if not df.empty:
                df['Archivo_Origen'] = file_name
                df['Grupo'] = extract_group(file_name)
                df['Archivo_Modificado'] = parse_drive_time(item.get('modifiedTime'))
                dfs.append(df)

        if not dfs:
            return pd.DataFrame()

        return prepare_raw_assignments(dfs)
    except HttpError as e:
        if getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
        else:
            st.error(f"Error de Google Drive API al obtener tareas: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error al procesar los reportes CSV de Khan Academy: {e}")
        return pd.DataFrame()


def compute_student_block_grades(assignments_df, criterios_config=None):
    """
    Calcula la calificación por bloque (Fecha de entrega) para cada estudiante y grupo:
    Block Grade = (Sum(Puntos Ganados) / Sum(Puntos Posibles)) * scale * (weight / 100.0)
    Redondeado a 1 decimal.
    Si ninguna tarea del bloque se ha evaluado todavía (todas 'Programada' o 'En curso'),
    la calificación del bloque se marca como NaN para no afectar el promedio del estudiante.
    """
    if assignments_df.empty:
        return pd.DataFrame()

    scale = 10.0
    weight = 100.0
    if criterios_config and isinstance(criterios_config, dict):
        scale = float(criterios_config.get('escala_maxima', 10))
        weight = float(criterios_config.get('peso_khan', 100))

    block_summary = assignments_df.groupby(
        ['Grupo', 'Nombre del estudiante', 'Fecha de entrega'],
        as_index=False
    ).agg(
        earned_sum=('earned_points', 'sum'),
        max_sum=('max_points', 'sum'),
        dt_entrega=('dt_entrega', 'first'),
        parcial=('Parcial', 'first') if 'Parcial' in assignments_df.columns else ('dt_entrega', 'first'),
        all_future=('status', lambda s: (s == 'Programada').all() if len(s) > 0 else False),
        not_evaluated=('status', lambda s: s.isin(NOT_EVALUATED_STATUSES).all() if len(s) > 0 else False)
    )

    # Con criterios por grupo, el peso de Khan (cuando escala la calificación) puede variar por grupo y parcial
    per_group = isinstance(criterios_config, dict) and criterios_config.get('criterios_por_grupo') and criterios_config.get('grupos')
    has_parcial = 'Parcial' in assignments_df.columns

    def row_weight(r):
        if not per_group:
            return weight
        return float(group_config(criterios_config, r['Grupo'], r['parcial'] if has_parcial else None).get('peso_khan', weight))

    def calc_grade(r):
        if r['max_sum'] > 0:
            raw_grade = (r['earned_sum'] / r['max_sum']) * scale * (row_weight(r) / 100.0)
            return round(raw_grade, 1)
        elif r.get('not_evaluated', False):
            return float('nan')
        else:
            return 0.0

    block_summary['block_grade'] = block_summary.apply(calc_grade, axis=1)

    return block_summary



# ==============================================================================
# COMPONENTE REUTILIZABLE: DASHBOARD DETALLADO DEL ESTUDIANTE
# ==============================================================================
def render_student_dashboard(student_name, student_data, criteria_config=None, is_admin_drilldown=False):
    """
    Renderiza la interfaz detallada del estudiante (tarjetas KPIs, filtros por Parcial
    y tipo de tarea dinámico, y bloques expandibles con tareas, intentos, fechas y puntos).
    """
    if student_data.empty:
        st.info(f"No se encontraron actividades registradas para **{student_name}**.")
        return

    # Obtener tipos de tarea presentes y configuración de criterios
    available_types = sorted([
        t for t in student_data['Tipo de tarea'].dropna().astype(str).str.strip().unique() if t
    ]) if 'Tipo de tarea' in student_data.columns else []

    if criteria_config is None:
        criteria_config = load_teacher_criterios(None, available_types)

    scale = int(criteria_config.get('escala_maxima', 10)) if isinstance(criteria_config, dict) else 10
    weight = float(criteria_config.get('peso_khan', 100)) if isinstance(criteria_config, dict) else 100.0
    thresholds = criteria_config.get('thresholds', {}) if isinstance(criteria_config, dict) else {}
    min_pass = float(thresholds.get('regular', 6.0 if scale == 10 else 60.0))

    # --------------------------------------------------------------------------
    # Filtros superiores (Parcial y Tipo de Actividad dinámico)
    # --------------------------------------------------------------------------
    filter_col1, filter_col2 = st.columns([3, 2])

    with filter_col1:
        parciales_disponibles = ["Todas", "Parcial 1", "Parcial 2", "Parcial 3", "Sin asignar"]
        selected_parcial = st.radio(
            "Filtrar por Periodo (Parcial):",
            parciales_disponibles,
            horizontal=True,
            key=f"parcial_filter_{'admin' if is_admin_drilldown else 'student'}_{student_name}"
        )

    with filter_col2:
        tipo_options = ["Todas las actividades"] + [f"Solo {t}" for t in available_types]
        tipo_filtro = st.selectbox(
            "Filtrar por tipo de actividad:",
            tipo_options,
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
    future_tasks = (active_data['status'] == 'Programada').sum()
    in_progress_tasks = (active_data['status'] == 'En curso').sum()
    active_tasks = total_tasks - future_tasks
    completed_tasks = active_data['is_completed'].sum()
    late_tasks = active_data['is_late'].sum()
    ontime_tasks = completed_tasks - late_tasks

    # Promedio del estudiante para el filtro activo (excluyendo bloques futuros)
    active_blocks = compute_student_block_grades(active_data, criteria_config)
    valid_blocks = active_blocks['block_grade'].dropna()
    overall_avg = valid_blocks.mean() if not valid_blocks.empty else 0.0

    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)
    with kpi_col1:
        title_avg = "Promedio General" if selected_parcial == "Todas" else f"Promedio {selected_parcial}"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">{title_avg}</div>
            <div class="stat-val" style="color: {'#16a34a' if overall_avg >= min_pass else '#dc2626'};">{overall_avg:.1f} <span style="font-size: 1rem; color: #64748b;">/ {scale}</span></div>
        </div>
        """, unsafe_allow_html=True)
    with kpi_col2:
        pending_bits = []
        if in_progress_tasks > 0:
            pending_bits.append(f"{in_progress_tasks} en curso")
        if future_tasks > 0:
            pending_bits.append(f"{future_tasks} programadas")
        caption_future = f"<div style='font-size:0.75rem; color:#64748b; margin-top:2px;'>({', '.join(pending_bits)})</div>" if pending_bits else ""
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-title">Actividades</div>
            <div class="stat-val">{active_tasks}{caption_future}</div>
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
        is_block_all_future = block_df['status'].isin(NOT_EVALUATED_STATUSES).all() if not block_df.empty else False
        block_label = "Programada" if (block_df['status'] == 'Programada').all() else "En curso"

        if block_max_total > 0:
            block_grade = round((block_earned_total / block_max_total) * scale * (weight / 100.0), 1)
            grade_str = f"{block_grade:.1f}"
            grade_color = '#16a34a' if block_grade >= min_pass else '#dc2626'
            progress_val = min(1.0, max(0.0, block_grade / float(scale)))
            pts_display = f"<strong>{block_earned_total:.1f} / {block_max_total:.1f}</strong>"
            grade_suffix = f"<span style='font-size: 0.95rem; color: #64748b;'> / {scale}</span>"
        elif is_block_all_future:
            block_grade = None
            grade_str = block_label
            grade_color = '#64748b'
            progress_val = 0.0
            pts_display = "<span style='color: #64748b; font-style: italic;'>" + ("Pendiente de inicio" if block_label == "Programada" else "Aún no vence") + "</span>"
            grade_suffix = ""
        else:
            block_grade = 0.0
            grade_str = "0.0"
            grade_color = '#dc2626'
            progress_val = 0.0
            pts_display = f"<strong>{block_earned_total:.1f} / {block_max_total:.1f}</strong>"
            grade_suffix = f"<span style='font-size: 0.95rem; color: #64748b;'> / {scale}</span>"

        # Filtrar solo para visualización en tabla si seleccionó tipo
        if tipo_filtro != "Todas las actividades":
            sel_t = tipo_filtro.replace("Solo ", "").strip()
            display_df = block_df[block_df['Tipo de tarea'].str.lower() == sel_t.lower()]
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
                        📅 Fecha de Entrega: <strong>{html.escape(str(due_date_str))}</strong>
                        <span class="badge-parcial">{html.escape(str(parcial_tag))}</span>
                    </h3>
                    <span style="color: #64748b; font-size: 0.9rem;">
                        Actividades: {block_tasks_count} | Completadas: {block_completed} | 
                        Puntos Obtenidos: {pts_display}
                    </span>
                </div>
                <div style="text-align: right; margin-top: 5px;">
                    <span style="font-size: 0.85rem; color: #64748b; font-weight: 600; text-transform: uppercase;">Calificación del Bloque:</span>
                    <span style="font-size: 1.7rem; font-weight: 800; color: {grade_color}; margin-left: 8px;">{grade_str}</span>
                    {grade_suffix}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.progress(progress_val)

        # Tabla detallada del bloque
        table_rows = []
        for _, row in display_df.iterrows():
            if row['status'] == 'En curso':
                aciertos_str = "—"
                intentos_str = str(row['attempts_count']) if row['attempts_count'] else "—"
                puntos_str = f"Vale hasta {row['potential_max']:.1f}"
                terminacion_str = "Pendiente"
                estado_str = "En curso"
                detalle_str = f"Entrégala antes de: {row['Fecha de entrega']}"
            elif row['status'] == 'Programada':
                aciertos_str = "—"
                intentos_str = "—"
                puntos_str = "Programada"
                terminacion_str = "—"
                estado_str = "Programada"
                inicio_val = row.get('Fecha de inicio')
                detalle_str = f"Programada (Inicia: {inicio_val})" if pd.notna(inicio_val) and str(inicio_val).strip() else "Programada (no iniciada)"
            else:
                if row.get('evaluar_intentos', False) or row.get('total_count', 0) > 0:
                    aciertos_str = f"{row['correct_count']} / {row['total_count']}"
                    intentos_str = str(row['attempts_count'])
                else:
                    aciertos_str = "N/A"
                    intentos_str = str(row['attempts_count']) if row['is_completed'] else "0"

                puntos_str = f"{row['earned_points']:.1f} / {row['max_points']:.1f}"
                terminacion_str = row['Última fecha de terminación'] if pd.notna(row['Última fecha de terminación']) else "Sin entrega"
                estado_str = row['status']
                detalle_str = row['observations']

            table_rows.append({
                "Actividad": row['Nombre de la tarea'],
                "Tipo": row['Tipo de tarea'],
                "Intentos": intentos_str,
                "Aciertos": aciertos_str,
                "Puntos Ganados": puntos_str,
                "Fecha Terminación": terminacion_str,
                "Estado": estado_str,
                "Detalle / Penalización": detalle_str
            })

        table_df = pd.DataFrame(table_rows)

        st.dataframe(
            table_df,
            width='stretch',
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

    # Acordeón de reglas con criterios activos dinámicos
    with st.expander("ℹ️ ¿Cómo se calculan los puntos ponderados y penalizaciones?"):
        st.markdown(render_criteria_explanation(criteria_config))


# ==============================================================================
# EXPERIENCIA DEL ESTUDIANTE: INICIO, PENDIENTES, RECUPERACIÓN Y LOGROS
# ==============================================================================
def compact_html(markup):
    """
    Une el HTML en una sola línea antes de pasarlo a st.markdown. Si queda una línea en
    blanco seguida de líneas con sangría, Markdown lo interpreta como bloque de código
    y el docente ve el HTML en crudo (p. ej. en las tarjetas sin aviso opcional).
    """
    return "".join(line.strip() for line in str(markup).splitlines())


MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

STATUS_STYLES = {
    'Excelente': {'icon': '🌟', 'bg': '#dcfce7', 'fg': '#166534', 'accent': '#16a34a'},
    'Bien': {'icon': '👍', 'bg': '#dbeafe', 'fg': '#1e40af', 'accent': '#2563eb'},
    'Regular': {'icon': '💪', 'bg': '#fef3c7', 'fg': '#92400e', 'accent': '#d97706'},
    'En riesgo': {'icon': '🤝', 'bg': '#fee2e2', 'fg': '#991b1b', 'accent': '#dc2626'},
    None: {'icon': '👋', 'bg': '#f1f5f9', 'fg': '#334155', 'accent': '#64748b'},
}


def format_short_date(dt, with_time=True):
    """'8 sep · 23:59' a partir de un Timestamp."""
    if dt is None or pd.isna(dt):
        return "sin fecha"
    text = f"{dt.day} {MESES_CORTOS[dt.month - 1]}"
    return f"{text} · {dt:%H:%M}" if with_time else text


def relative_days_label(dt, today=None):
    """'hoy', 'mañana', 'en 3 días', 'hace 2 días'."""
    if dt is None or pd.isna(dt):
        return ""
    today = today or now_local().date()
    diff = (dt.date() - today).days
    if diff == 0:
        return "hoy"
    if diff == 1:
        return "mañana"
    if diff > 1:
        return f"en {diff} días"
    if diff == -1:
        return "ayer"
    return f"hace {-diff} días"


def _average_block_grade(tasks, criteria_config):
    blocks = compute_student_block_grades(tasks, criteria_config)
    if blocks.empty:
        return None
    grades = blocks['block_grade'].dropna()
    return float(grades.mean()) if not grades.empty else None


def build_student_insights(tasks, criteria_config):
    """
    Calcula todo lo que necesita la vista del alumno a partir de sus actividades calificadas:
    promedio actual, pendientes, proyecciones de recuperación, racha, tendencia y logros.
    """
    cfg = criteria_config if isinstance(criteria_config, dict) else {}
    scale = int(cfg.get('escala_maxima', 10))
    weight = float(cfg.get('peso_khan', 100))
    thresholds = cfg.get('thresholds', {}) or {}
    max_grade = scale * weight / 100.0
    step = 1.0 if scale == 10 else 10.0  # "un punto" en la escala del docente
    min_pass = float(thresholds.get('regular', 6.0 if scale == 10 else 60.0))
    min_excelente = float(thresholds.get('excelente', 9.5 if scale == 10 else 95.0))
    today = now_local().date()

    ins = {
        'components': uses_components(cfg),
        'scale': scale, 'max_grade': max_grade, 'min_pass': min_pass,
        'min_excelente': min_excelente, 'step': step,
    }

    avg_now = _average_block_grade(tasks, cfg)
    ins['avg'] = avg_now
    ins['status'] = classify_student(avg_now, thresholds, scale) if avg_now is not None else None

    # Promedio del parcial en curso
    ins['parcial_actual'] = None
    ins['parcial_avg'] = None
    if 'Parcial' in tasks.columns:
        for p_name, rng in parse_parciales_dates(cfg.get('parciales', {})).items():
            if rng['start'] <= today <= rng['end']:
                ins['parcial_actual'] = p_name
                ins['parcial_avg'] = _average_block_grade(tasks[tasks['Parcial'] == p_name], cfg)
                break

    # Pendientes
    ins['upcoming'] = tasks[tasks['status'] == 'En curso'].sort_values('dt_entrega')
    ins['overdue'] = tasks[tasks['status'] == 'No completado'].sort_values('dt_entrega')
    ins['scheduled'] = tasks[tasks['status'] == 'Programada'].sort_values('dt_inicio')

    # Proyecciones ("¿qué pasa si entrego?")
    def simulate(recover_overdue=False, upcoming_mode=None):
        sim = tasks.copy()
        if recover_overdue and not ins['overdue'].empty:
            m = sim['status'] == 'No completado'
            sim.loc[m, 'max_points'] = sim.loc[m, ['max_points', 'potential_max']].max(axis=1)
            sim.loc[m, 'earned_points'] = sim.loc[m, 'potential_late']
            sim.loc[m, 'status'] = 'Tardía'
        if upcoming_mode and not ins['upcoming'].empty:
            m = sim['status'] == 'En curso'
            sim.loc[m, 'max_points'] = sim.loc[m, 'potential_max']
            sim.loc[m, 'earned_points'] = sim.loc[m, 'potential_on_time'] if upcoming_mode == 'on_time' else 0.0
            sim.loc[m, 'status'] = 'A tiempo' if upcoming_mode == 'on_time' else 'No completado'
        return _average_block_grade(sim, cfg)

    ins['avg_recover_overdue'] = simulate(recover_overdue=True) if not ins['overdue'].empty else None
    ins['avg_upcoming_on_time'] = simulate(upcoming_mode='on_time') if not ins['upcoming'].empty else None
    ins['avg_upcoming_missed'] = simulate(upcoming_mode='missed') if not ins['upcoming'].empty else None
    ins['avg_best'] = simulate(recover_overdue=True, upcoming_mode='on_time') if (not ins['overdue'].empty or not ins['upcoming'].empty) else None

    # Bloques ya cerrados (todas sus actividades vencidas o entregadas), en orden cronológico
    blocks = compute_student_block_grades(tasks, cfg)
    finished = []
    if not blocks.empty:
        for _, b in blocks.sort_values('dt_entrega').iterrows():
            b_tasks = tasks[tasks['Fecha de entrega'] == b['Fecha de entrega']]
            if b_tasks['status'].isin(NOT_EVALUATED_STATUSES).any() or pd.isna(b['block_grade']):
                continue
            finished.append({
                'fecha': b['Fecha de entrega'],
                'dt': b['dt_entrega'],
                'grade': float(b['block_grade']),
                'all_on_time': bool(b_tasks['status'].astype(str).str.startswith('A tiempo').all()),
            })
    ins['finished_blocks'] = finished

    streak = 0
    for b in reversed(finished):
        if not b['all_on_time']:
            break
        streak += 1
    ins['streak'] = streak

    ins['trend'] = None
    if len(finished) >= 2:
        prev = [b['grade'] for b in finished[:-1]]
        ins['trend'] = finished[-1]['grade'] - (sum(prev) / len(prev))

    evaluated = tasks[~tasks['status'].isin(NOT_EVALUATED_STATUSES)]
    on_time = evaluated['status'].astype(str).str.startswith('A tiempo')
    ins['n_evaluated'] = len(evaluated)
    ins['on_time_pct'] = (on_time.mean() * 100) if len(evaluated) else None

    perfect_ex = evaluated[on_time & (evaluated['total_count'] > 0) & (evaluated['correct_count'] >= evaluated['total_count'])]

    # Logros: se calculan solo con los datos del propio alumno (sin comparar con compañeros)
    ins['badges'] = [
        {
            'icon': '🔥', 'title': 'Racha puntual',
            'earned': streak >= 3,
            'desc': f"{streak} bloque(s) seguidos entregando todo a tiempo." if streak else "Entrega completo y a tiempo varios bloques seguidos.",
            'how': "Entrega todas las actividades a tiempo 3 bloques seguidos.",
        },
        {
            'icon': '🎯', 'title': 'Puntería perfecta',
            'earned': len(perfect_ex) > 0,
            'desc': f"{len(perfect_ex)} ejercicio(s) con todas las respuestas correctas.",
            'how': "Resuelve un ejercicio a tiempo con el 100% de aciertos.",
        },
        {
            'icon': '⏰', 'title': 'Siempre a tiempo',
            'earned': ins['on_time_pct'] is not None and len(evaluated) >= 5 and ins['on_time_pct'] >= 90,
            'desc': f"{ins['on_time_pct']:.0f}% de tus actividades entregadas a tiempo." if ins['on_time_pct'] is not None else "Aún no hay actividades evaluadas.",
            'how': "Entrega a tiempo al menos el 90% de tus actividades.",
        },
        {
            'icon': '🏆', 'title': 'Bloque perfecto',
            'earned': any(b['grade'] >= max_grade - 0.05 for b in finished),
            'desc': f"Obtuviste {max_grade:g} en al menos un bloque.",
            'how': f"Consigue {max_grade:g} en un bloque de entrega.",
        },
        {
            'icon': '📈', 'title': 'En ascenso',
            'earned': ins['trend'] is not None and (ins['trend'] >= step or finished[-1]['grade'] >= max_grade - 0.05),
            'desc': "Tu último bloque superó tu promedio anterior." if (ins['trend'] or 0) >= step else "Mantuviste la calificación máxima en tu último bloque.",
            'how': "Supera tu promedio por al menos 1 punto en tu siguiente bloque.",
        },
        {
            'icon': '✅', 'title': 'Al día',
            'earned': len(finished) > 0 and ins['overdue'].empty,
            'desc': "No tienes actividades atrasadas.",
            'how': "Entrega todas tus actividades atrasadas.",
        },
    ]
    return ins


def build_motivation_message(ins):
    """Mensaje personalizado según el desempeño: reconoce lo bueno y propone un siguiente paso concreto."""
    status = ins['status']
    avg = ins['avg']
    n_over = len(ins['overdue'])
    n_up = len(ins['upcoming'])
    best = ins['avg_best']

    if status is None:
        if n_up:
            return ("¡Bienvenido(a)!", f"Aún no tienes actividades evaluadas. Tienes {n_up} actividad(es) en curso: entrégalas a tiempo y empieza con el pie derecho.")
        return ("¡Bienvenido(a)!", "Aún no tienes actividades evaluadas. Aquí verás tu avance en cuanto tu docente publique las primeras tareas.")

    streak_txt = f" Llevas {ins['streak']} bloque(s) seguidos entregando todo a tiempo." if ins['streak'] >= 2 else ""
    trend = ins['trend']
    trend_txt = ""
    if trend is not None and trend >= ins['step'] * 0.5:
        trend_txt = " Tu último bloque fue mejor que tu promedio: ¡vas mejorando!"

    if status == 'Excelente':
        return ("¡Vas excelente!", f"Tu esfuerzo se nota.{streak_txt}{trend_txt} Mantén este ritmo todo el parcial.")
    if status == 'Bien':
        gap = max(0.0, ins['min_excelente'] - avg)
        extra = ""
        if _meaningful_gain(avg, best):
            extra = f" Si entregas tus pendientes, tu promedio puede llegar a {best:.1f}."
        return ("¡Vas muy bien!", f"Estás a {gap:.1f} de llegar a Excelente.{streak_txt}{trend_txt}{extra}")
    if status == 'Regular':
        extra = f" Si entregas tus pendientes, tu promedio puede subir a {best:.1f}." if _meaningful_gain(avg, best) else " Entrega tus próximas actividades a tiempo para subir tu promedio."
        return ("Vas aprobando, ¡puedes más!", f"Estás por encima del mínimo, pero todavía hay espacio para mejorar.{trend_txt}{extra}")
    # En riesgo: tono de apoyo, nunca de regaño
    if _meaningful_gain(avg, best):
        parts = []
        if n_over:
            parts.append(f"{n_over} actividad(es) atrasada(s)")
        if n_up:
            parts.append(f"{n_up} en curso")
        return ("Todavía estás a tiempo de recuperarte", f"Si entregas tus {' y '.join(parts)}, tu promedio puede subir de {avg:.1f} a {best:.1f}. Empieza por la que vence primero; cada entrega cuenta.{trend_txt}")
    return ("Todavía estás a tiempo de recuperarte", f"Cada bloque nuevo es una oportunidad. Entrega a tiempo tus próximas actividades y pide ayuda a tu docente si algún tema se te complica.{trend_txt}")


def _exercise_detail(r, late):
    """'0.5 pts por acierto · 4 preguntas · máx. 3 intentos' para ejercicios que se califican por aciertos."""
    per = r.get('per_correct_late' if late else 'per_correct_on_time')
    if per is None or pd.isna(per) or not r.get('questions_known'):
        return ""
    txt = f" · {per:g} pts por acierto · {int(r['questions_known'])} preguntas"
    if r.get('evaluar_intentos'):
        txt += f" · máx. {int(r['max_intentos'])} intentos"
    return html.escape(txt)


def _task_card_html(title, meta, right, accent):
    return f"""
    <div class="task-card" style="border-left-color: {accent};">
        <div class="task-main">
            <div class="task-title">{html.escape(str(title))}</div>
            <div class="task-meta">{meta}</div>
        </div>
        <div class="task-right">{right}</div>
    </div>"""


def render_progress_chart(ins):
    finished = ins['finished_blocks']
    if len(finished) < 2:
        st.caption("Tu gráfica de progreso aparecerá cuando tengas al menos 2 bloques evaluados.")
        return
    import altair as alt
    chart_df = pd.DataFrame([
        {'Entrega': format_short_date(b['dt'], with_time=False) if pd.notna(b['dt']) else str(b['fecha']),
         'Orden': i, 'Calificación': round(b['grade'], 1)}
        for i, b in enumerate(finished)
    ])
    y_scale = alt.Scale(domain=[0, ins['max_grade']])
    x_enc = alt.X('Entrega:N', sort=alt.SortField('Orden'), title=None, axis=alt.Axis(labelAngle=0, grid=False))
    line = alt.Chart(chart_df).mark_line(
        strokeWidth=2, color='#2563eb',
        point=alt.OverlayMarkDef(size=70, filled=True, color='#2563eb')
    ).encode(
        x=x_enc,
        y=alt.Y('Calificación:Q', scale=y_scale, title=None, axis=alt.Axis(gridOpacity=0.4, tickCount=5)),
        tooltip=[alt.Tooltip('Entrega:N'), alt.Tooltip('Calificación:Q', format='.1f')]
    )
    rule_df = pd.DataFrame({'y': [ins['min_pass']], 'label': [f"Mínimo aprobatorio ({ins['min_pass']:g})"]})
    rule = alt.Chart(rule_df).mark_rule(strokeDash=[4, 4], color='#94a3b8', strokeWidth=1.5).encode(y='y:Q')
    rule_text = alt.Chart(rule_df).mark_text(align='left', dx=4, dy=-7, color='#64748b', fontSize=11).encode(
        y='y:Q', x=alt.value(0), text='label:N'
    )
    st.altair_chart((rule + rule_text + line).properties(height=240), width='stretch')


def render_badges(ins):
    cards = []
    for b in ins['badges']:
        cls = "badge-card earned" if b['earned'] else "badge-card locked"
        detail = b['desc'] if b['earned'] else f"<em>Cómo conseguirlo:</em> {b['how']}"
        state = "✔ Conseguido" if b['earned'] else "🔒 Por conseguir"
        cards.append(f"""
        <div class="{cls}">
            <div class="badge-icon">{b['icon']}</div>
            <div class="badge-title">{b['title']}</div>
            <div class="badge-state">{state}</div>
            <div class="badge-desc">{detail}</div>
        </div>""")
    st.markdown(compact_html(f"<div class='badge-grid'>{''.join(cards)}</div>"), unsafe_allow_html=True)


def render_student_home(ins):
    style = STATUS_STYLES.get(ins['status'], STATUS_STYLES[None])
    title, body = build_motivation_message(ins)
    avg_txt = f"{ins['avg']:.1f}" if ins['avg'] is not None else "—"
    status_txt = ins['status'] or "Sin evaluar"
    sel = ins.get('parcial_sel')
    if ins.get('components'):
        hero_label = f"Khan Academy · {sel}" if sel else "Promedio en Khan Academy"
    else:
        hero_label = f"Calificación del {sel}" if sel else "Promedio general"
    st.markdown(compact_html(f"""
    <div class="hero-card" style="border-left-color: {style['accent']};">
        <div class="hero-top">
            <div>
                <div class="hero-label">{hero_label}</div>
                <div class="hero-grade">{avg_txt}<span> / {ins['scale']}</span></div>
            </div>
            <div class="hero-status" style="background: {style['bg']}; color: {style['fg']};">{style['icon']} {status_txt}</div>
        </div>
        <div class="hero-msg"><strong>{html.escape(title)}</strong><br>{html.escape(body)}</div>
    </div>
    """), unsafe_allow_html=True)

    # Fila compacta de indicadores (se mantiene en una sola fila también en celular)
    if sel and ins.get('components'):
        # Con evidencias/examen, el promedio de Khan del semestre no es una calificación: mejor, lo pendiente del parcial
        first_stat = ("📝 Por entregar", f"{len(ins['upcoming']) + len(ins['overdue'])} <small>actividad(es)</small>")
    elif sel:
        sem_val = ins.get('semester_avg')
        first_stat = ("📚 Promedio de los parciales", (f"{sem_val:.1f}" if sem_val is not None else "—") +
                      (f" <small>({ins['n_parciales']} parcial{'es' if ins['n_parciales'] != 1 else ''})</small>" if sem_val is not None else ""))
    else:
        parcial_label = f"Promedio {ins['parcial_actual']}" if ins['parcial_actual'] else "Parcial actual"
        first_stat = (parcial_label, f"{ins['parcial_avg']:.1f}" if ins['parcial_avg'] is not None else "—")
    mini_stats = [
        first_stat,
        ("🔥 Racha puntual", f"{ins['streak']} <small>bloque(s)</small>"),
        ("⏰ A tiempo", f"{ins['on_time_pct']:.0f}%" if ins['on_time_pct'] is not None else "—"),
    ]
    st.markdown(
        "<div class='mini-stats'>" + "".join(
            f"<div class='mini-stat'><div class='mini-label'>{html.escape(lbl)}</div><div class='mini-val'>{val}</div></div>"
            for lbl, val in mini_stats
        ) + "</div>",
        unsafe_allow_html=True
    )

    # Próximo paso
    if not ins['upcoming'].empty:
        next_dt = ins['upcoming']['dt_entrega'].iloc[0]
        n_next = int((ins['upcoming']['dt_entrega'] == next_dt).sum())
        st.info(f"⏰ **Tu próxima entrega:** {format_short_date(next_dt)} ({relative_days_label(next_dt)}) — {n_next} actividad(es). Revisa la pestaña **Pendientes**.")
    elif not ins['overdue'].empty:
        st.warning(f"📝 Tienes **{len(ins['overdue'])} actividad(es) atrasada(s)** que todavía puedes entregar. Revisa la pestaña **Pendientes**.")
    elif ins['avg'] is not None:
        st.success("✅ ¡Estás al día! No tienes actividades pendientes por ahora.")

    st.markdown("#### 📈 Mi progreso por bloque")
    render_progress_chart(ins)

    st.markdown("#### 🏅 Mis logros")
    render_badges(ins)


def render_student_pending(ins, key_prefix):
    upcoming, overdue, scheduled = ins['upcoming'], ins['overdue'], ins['scheduled']
    sel = ins.get('parcial_sel')
    noun = f"tu calificación del {sel}" if sel else "tu promedio"

    # Calculadora de recuperación
    if ins['avg_best'] is not None:
        st.markdown(f"#### 🧮 ¿Cuánto puede subir {noun}?")
        delta = (ins['avg_best'] - ins['avg']) if ins['avg'] is not None else None
        delta_html = f" <small class='delta-up'>▲ {delta:.1f}</small>" if delta is not None and delta >= 0.05 else ""
        st.markdown(f"""
        <div class='mini-stats' style='grid-template-columns: repeat(2, 1fr);'>
            <div class='mini-stat'><div class='mini-label'>{f"Llevas en el {sel}" if sel else "Promedio actual"}</div><div class='mini-val'>{f"{ins['avg']:.1f}" if ins['avg'] is not None else "—"}</div></div>
            <div class='mini-stat'><div class='mini-label'>Si entregas todo lo pendiente</div><div class='mini-val'>{ins['avg_best']:.1f}{delta_html}</div></div>
        </div>""", unsafe_allow_html=True)
        lines = []
        if ins['avg_upcoming_on_time'] is not None:
            lines.append(f"- Si entregas **a tiempo** tus {len(upcoming)} actividad(es) en curso: **{ins['avg_upcoming_on_time']:.1f}**. Si no las entregas: **{ins['avg_upcoming_missed']:.1f}**.")
        if ins['avg_recover_overdue'] is not None:
            lines.append(f"- Si entregas tus {len(overdue)} actividad(es) atrasada(s), aunque sea tarde: **{ins['avg_recover_overdue']:.1f}**.")
        if lines:
            st.markdown("\n".join(lines))
        st.caption((f"Solo cuentan las actividades del {sel}. " if sel else "") +
                   "Estimación suponiendo que respondes todo correctamente sin pasarte del máximo de intentos. "
                   "En los ejercicios, los puntos dependen de tus aciertos; si una entrega tardía supera el máximo de intentos, vale 0. "
                   "Las entregas tardías valen menos, ¡pero siempre suman!")
        st.link_button("🚀 Ir a Khan Academy", "https://es.khanacademy.org/", type="primary", width='stretch')
        st.divider()

    # En curso, agrupadas por fecha de entrega
    st.markdown(f"#### ⏳ Por entregar ({len(upcoming)})")
    if upcoming.empty:
        st.caption("No tienes actividades en curso. 🎉")
    else:
        for due_label, grp in upcoming.groupby('Fecha de entrega', sort=False):
            due_dt = grp['dt_entrega'].iloc[0]
            rel = relative_days_label(due_dt)
            urgent = rel in ("hoy", "mañana")
            st.markdown(f"**📅 Vence {format_short_date(due_dt)}** · {'🔴 ' if urgent else ''}{rel}")
            cards = [
                _task_card_html(
                    r['Nombre de la tarea'],
                    html.escape(str(r['Tipo de tarea'])) + _exercise_detail(r, late=False),
                    f"Vale hasta<br><strong>{r['potential_max']:.1f} pts</strong>",
                    '#dc2626' if urgent else '#2563eb'
                ) for _, r in grp.iterrows()
            ]
            st.markdown(compact_html("".join(cards)), unsafe_allow_html=True)

    st.markdown(f"#### ⚠️ Atrasadas — aún puedes entregarlas ({len(overdue)})")
    if overdue.empty:
        st.caption("No tienes actividades atrasadas. ¡Muy bien!")
    else:
        cards = [
            _task_card_html(
                r['Nombre de la tarea'],
                f"{html.escape(str(r['Tipo de tarea']))} · Venció {format_short_date(r['dt_entrega'], with_time=False)} ({relative_days_label(r['dt_entrega'])})" + _exercise_detail(r, late=True),
                f"Recuperas hasta<br><strong>{r['potential_late']:.1f} pts</strong>",
                '#d97706'
            ) for _, r in overdue.iterrows()
        ]
        st.markdown(compact_html("".join(cards)), unsafe_allow_html=True)

    if ins.get('other_overdue'):
        others = ", ".join(f"{n} del {p}" for p, n in sorted(ins['other_overdue'].items()))
        st.caption(f"📂 También tienes actividades atrasadas de otro parcial ({others}). Elige ese parcial arriba para verlas; "
                   "pregúntale a tu docente si todavía cuentan.")

    if not scheduled.empty:
        next_start = scheduled['dt_inicio'].iloc[0]
        st.caption(f"📅 Próximamente: {len(scheduled)} actividad(es) programada(s). La siguiente se habilita el {format_short_date(next_start)}.")


def render_student_experience(student_name, tasks, criteria_config, key_prefix="student", updated_at=None, eval_ctx=None, student_id=None):
    """Vista completa del alumno. El docente la ve igual desde el drill-down (key_prefix='admin')."""
    if tasks.empty:
        st.info("Todavía no hay actividades registradas para ti en esta asignatura. Si crees que es un error, avísale a tu docente.")
        return

    cfg = criteria_config if isinstance(criteria_config, dict) else {}
    if updated_at is not None and pd.notna(updated_at):
        st.caption(f"🔄 Datos actualizados al {format_short_date(updated_at)}. Lo que entregues después aparecerá cuando tu docente actualice los reportes de Khan Academy.")

    # Cada parcial se califica por separado: Inicio y Pendientes muestran solo el parcial elegido
    # (por defecto, el que está en curso), para no mezclarlo con los anteriores.
    parcial_opts = [p for p in PARCIALES if 'Parcial' in tasks.columns and (tasks['Parcial'] == p).any()]
    sel_parcial = None
    view_tasks = tasks
    if parcial_opts:
        cur = current_parcial(cfg)
        default_p = cur if cur in parcial_opts else parcial_opts[-1]
        view_key = f"{key_prefix}_view_parcial"
        extra = {} if view_key in st.session_state else {'default': default_p}
        sel_parcial = st.segmented_control("Parcial", parcial_opts, key=view_key, required=True,
                                           label_visibility="collapsed", **extra) or default_p
        view_tasks = tasks[tasks['Parcial'] == sel_parcial]
    ins = build_student_insights(view_tasks, cfg)
    ins['parcial_sel'] = sel_parcial
    p_avgs = [a for a in (_average_block_grade(tasks[tasks['Parcial'] == p], cfg) for p in parcial_opts) if a is not None]
    ins['semester_avg'] = sum(p_avgs) / len(p_avgs) if p_avgs else None
    ins['n_parciales'] = len(p_avgs)
    other = tasks[(tasks['status'] == 'No completado') & (tasks['Parcial'] != sel_parcial)] if sel_parcial else tasks.iloc[0:0]
    ins['other_overdue'] = other.groupby('Parcial').size().to_dict() if not other.empty else {}

    n_pend = len(ins['upcoming']) + len(ins['overdue'])
    # Pestaña de evaluación del parcial: solo si el docente usa otros componentes o registró algo del alumno
    show_eval = bool(eval_ctx) and bool(student_id) and (
        any(float(v) > 0 for v in (cfg.get('componentes') or {}).values())
        or any(not t.empty and (t['ID alumno'] == student_id).any() for t in (eval_ctx['evid'], eval_ctx['extra'], eval_ctx['att']))
    )
    folder_id = eval_ctx.get('folder_id') if eval_ctx else None
    topics_map = load_topics_map(folder_id) if eval_ctx else {}
    show_goals = bool(eval_ctx) and bool(student_id)
    tab_labels = ["🏠 Inicio", f"📝 Pendientes ({n_pend})" if n_pend else "📝 Pendientes", "📋 Mis calificaciones"]
    if show_eval:
        tab_labels.append("🧾 Mi evaluación")
    if topics_map:
        tab_labels.append("📚 Mis temas")
    if show_goals:
        tab_labels.append("🎯 Mi meta")
    tabs = st.tabs(tab_labels)
    tab_of = dict(zip(tab_labels, tabs))
    with tabs[0]:
        render_student_home(ins)
    with tabs[1]:
        if eval_ctx and student_id:
            render_evidence_motivation({**eval_ctx, 'tasks': tasks}, student_id, cfg, sel_parcial or current_parcial(cfg), compact=True)
        render_student_pending(ins, key_prefix)
    with tabs[2]:
        render_student_dashboard(student_name, tasks, criteria_config=criteria_config, is_admin_drilldown=(key_prefix == 'admin'))
    if show_eval:
        with tab_of["🧾 Mi evaluación"]:
            render_student_evaluation({**eval_ctx, 'tasks': tasks}, student_id, criteria_config, key_prefix, sel_parcial)
    if topics_map:
        with tab_of["📚 Mis temas"]:
            render_student_topics(tasks, topics_map)
    if show_goals:
        with tab_of["🎯 Mi meta"]:
            render_student_goals(folder_id, student_id, tasks, cfg, key_prefix, eval_ctx)


# ==============================================================================
# PANEL DOCENTE: RESUMEN, ALUMNOS QUE NECESITAN ATENCIÓN Y RECONOCIMIENTOS
# ==============================================================================
# Paleta categórica (orden fijo) para distinguir grupos en las gráficas
GROUP_PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']


def group_color_map(all_groups):
    """El color sigue al grupo (no a su posición en el filtro)."""
    return {g: GROUP_PALETTE[i % len(GROUP_PALETTE)] for i, g in enumerate(sorted(all_groups))}


def build_class_insights(tasks, block_summary, criteria_config):
    """
    Resume el desempeño de cada alumno para detectar a quién apoyar y a quién reconocer.
    Retorna un DataFrame con una fila por alumno.
    """
    cfg = criteria_config if isinstance(criteria_config, dict) else {}
    keys = ['Grupo', 'Nombre del estudiante', 'Fecha de entrega']

    blocks = block_summary.copy()
    status_by_block = tasks.groupby(keys)['status']
    blocks = blocks.merge(
        pd.DataFrame({
            'has_pending': status_by_block.agg(lambda s: s.isin(NOT_EVALUATED_STATUSES).any()),
            'all_on_time': status_by_block.agg(lambda s: s.astype(str).str.startswith('A tiempo').all()),
            'all_missing': status_by_block.agg(lambda s: (s == 'No completado').all()),
        }).reset_index(),
        on=keys, how='left'
    )
    blocks['finished'] = (~blocks['has_pending'].fillna(True).astype(bool)) & blocks['block_grade'].notna()

    rows = []
    for (grupo, nombre), b in blocks.groupby(['Grupo', 'Nombre del estudiante']):
        fb = b[b['finished']].sort_values('dt_entrega')
        grades = b['block_grade'].dropna()
        avg = float(grades.mean()) if not grades.empty else None

        last = prev_avg = trend = None
        if len(fb) >= 1:
            last = float(fb['block_grade'].iloc[-1])
        if len(fb) >= 2:
            prev_avg = float(fb['block_grade'].iloc[:-1].mean())
            trend = last - prev_avg

        missing_streak = 0
        for v in reversed(fb['all_missing'].tolist()):
            if not v:
                break
            missing_streak += 1
        on_time_streak = 0
        for v in reversed(fb['all_on_time'].tolist()):
            if not v:
                break
            on_time_streak += 1

        t = tasks[(tasks['Grupo'] == grupo) & (tasks['Nombre del estudiante'] == nombre)]
        evaluated = t[~t['status'].isin(NOT_EVALUATED_STATUSES)]
        completed = evaluated[evaluated['is_completed'].astype(bool)]
        n_late = int(evaluated['is_late'].astype(bool).sum())
        n_on_time = int(evaluated['status'].astype(str).str.startswith('A tiempo').sum())
        excess = t[t['evaluar_intentos'].astype(bool) & (t['attempts_count'] > t['max_intentos']) & ~t['status'].isin(NOT_EVALUATED_STATUSES)]

        rows.append({
            'Grupo': grupo,
            'Nombre del estudiante': nombre,
            'avg': avg,
            'status': classify_for(avg, cfg, grupo) if avg is not None else None,
            'last': last,
            'prev_avg': prev_avg,
            'trend': trend,
            'missing_streak': missing_streak,
            'on_time_streak': on_time_streak,
            'n_evaluated': len(evaluated),
            'n_completed': len(completed),
            'n_late': n_late,
            'n_on_time': n_on_time,
            'n_overdue': int((t['status'] == 'No completado').sum()),
            'n_excess_attempts': len(excess),
        })
    return pd.DataFrame(rows)


def build_attention_lists(class_df, criteria_config, attendance=None):
    """Aplica reglas simples y explicables para las listas de atención y reconocimiento."""
    cfg = criteria_config if isinstance(criteria_config, dict) else {}
    scale = int(cfg.get('escala_maxima', 10))
    step = 1.0 if scale == 10 else 10.0
    th = cfg.get('thresholds', {}) or {}
    min_pass = float(th.get('regular', 6.0 if scale == 10 else 60.0))

    attention, recognition = [], []
    for _, r in class_df.iterrows():
        reasons, actions, severity = [], [], 0
        if r['missing_streak'] >= 2:
            reasons.append(f"No entregó nada en los últimos {r['missing_streak']} bloques")
            actions.append("Contactarlo (y a su familia si es necesario); verificar que pueda entrar a Khan Academy")
            severity += 3
        if r['status'] == 'En riesgo':
            g_min = float((group_config(cfg, r['Grupo']).get('thresholds') or {}).get('regular', min_pass))
            reasons.append(f"Promedio {r['avg']:.1f}, bajo el mínimo ({g_min:g})")
            actions.append(f"Plática individual y plan para entregar sus {r['n_overdue']} atrasada(s)" if r['n_overdue'] else "Plática individual y seguimiento semanal")
            severity += 2
        if r['trend'] is not None and r['trend'] <= -1.5 * step:
            reasons.append(f"Bajó de {r['prev_avg']:.1f} a {r['last']:.1f} en su último bloque")
            actions.append("Preguntarle qué pasó esta semana")
            severity += 2
        if r['n_completed'] >= 3 and r['n_late'] / r['n_completed'] >= 0.4:
            reasons.append(f"Entrega tarde el {r['n_late'] / r['n_completed'] * 100:.0f}% de sus actividades")
            actions.append("Recordatorios de fechas; ayudarle a organizar su semana")
            severity += 1
        if r['n_excess_attempts'] >= 2:
            reasons.append(f"Excede los intentos en {r['n_excess_attempts']} ejercicios")
            actions.append("Repasar el tema con él; posible dificultad de comprensión")
            severity += 1
        att_pct = (attendance or {}).get(r['Nombre del estudiante'])
        min_att = float(cfg.get('asistencia_minima', 80))
        if att_pct is not None and att_pct < min_att:
            reasons.append(f"Asistencia de {att_pct:.0f}% (mínimo {min_att:g}%)")
            actions.append("Avisar a su tutor(a) académico(a) y revisar justificantes")
            severity += 3
        elif att_pct is not None and att_pct < min_att + 5:
            reasons.append(f"Asistencia de {att_pct:.0f}%, cerca del mínimo ({min_att:g}%)")
            actions.append("Recordarle la importancia de asistir")
            severity += 1
        if reasons:
            attention.append({
                'Prioridad': '🔴 Alta' if severity >= 3 else '🟠 Media',
                '_sev': severity,
                'Nombre del estudiante': r['Nombre del estudiante'],
                'Grupo': r['Grupo'],
                'Promedio': f"{r['avg']:.1f}" if r['avg'] is not None else "—",
                'Motivos': " · ".join(reasons),
                'Acción sugerida': "; ".join(dict.fromkeys(actions)),
                '_reasons': reasons,
                '_actions': list(dict.fromkeys(actions)),
                'Atrasadas': int(r['n_overdue']),
            })

        kudos = []
        if r['status'] == 'Excelente':
            kudos.append(f"Promedio excelente ({r['avg']:.1f})")
        if r['on_time_streak'] >= 3:
            kudos.append(f"{r['on_time_streak']} bloques seguidos entregando todo a tiempo")
        if r['trend'] is not None and r['trend'] >= step:
            kudos.append(f"Mejoró de {r['prev_avg']:.1f} a {r['last']:.1f}")
        if r['n_evaluated'] >= 5 and r['n_on_time'] == r['n_evaluated']:
            kudos.append("100% de actividades a tiempo")
        if kudos:
            recognition.append({
                'Nombre del estudiante': r['Nombre del estudiante'],
                'Grupo': r['Grupo'],
                'Promedio': f"{r['avg']:.1f}" if r['avg'] is not None else "—",
                'Motivo de reconocimiento': " · ".join(kudos),
                '_kudos': kudos,
                '_improved': r['trend'] is not None and r['trend'] >= step,
            })

    att_df = pd.DataFrame(attention)
    if not att_df.empty:
        att_df = att_df.sort_values(['_sev', 'Atrasadas'], ascending=[False, False]).drop(columns='_sev')
    rec_df = pd.DataFrame(recognition)
    if not rec_df.empty:
        # Primero quienes mejoraron: el esfuerzo también merece reconocimiento
        rec_df = rec_df.sort_values('_improved', ascending=False).drop(columns='_improved')
    return att_df, rec_df


def render_group_trend_chart(block_summary, tasks, criteria_config, color_map):
    cfg = criteria_config if isinstance(criteria_config, dict) else {}
    scale = int(cfg.get('escala_maxima', 10))
    max_grade = scale * float(cfg.get('peso_khan', 100)) / 100.0
    min_pass = float((cfg.get('thresholds', {}) or {}).get('regular', 6.0 if scale == 10 else 60.0))

    # Solo bloques cerrados (sin actividades en curso ni programadas)
    pending_dates = set(tasks.loc[tasks['status'].isin(NOT_EVALUATED_STATUSES), 'Fecha de entrega'])
    data = block_summary[block_summary['block_grade'].notna() & ~block_summary['Fecha de entrega'].isin(pending_dates)]
    if data.empty:
        st.caption("La gráfica aparecerá cuando haya bloques cerrados.")
        return
    # Se agrupa por semana (lunes) porque cada grupo puede tener fechas de entrega distintas
    data = data.dropna(subset=['dt_entrega']).copy()
    data['semana'] = data['dt_entrega'].dt.normalize() - pd.to_timedelta(data['dt_entrega'].dt.weekday, unit='D')
    trend = data.groupby(['Grupo', 'semana'], as_index=False).agg(
        Promedio=('block_grade', 'mean'), Alumnos=('Nombre del estudiante', 'nunique')
    ).rename(columns={'semana': 'dt'}).sort_values('dt')
    trend['Promedio'] = trend['Promedio'].round(1)
    trend['Entrega'] = trend['dt'].apply(lambda d: "Sem. " + format_short_date(d, with_time=False))
    order = trend.drop_duplicates('Entrega')['Entrega'].tolist()

    import altair as alt
    groups = sorted(trend['Grupo'].unique())
    color = alt.Color('Grupo:N', scale=alt.Scale(domain=groups, range=[color_map[g] for g in groups]),
                      legend=alt.Legend(orient='top', title=None) if len(groups) > 1 else None)
    line = alt.Chart(trend).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=64, filled=True)).encode(
        x=alt.X('Entrega:N', sort=order, title=None, axis=alt.Axis(labelAngle=0, grid=False)),
        y=alt.Y('Promedio:Q', scale=alt.Scale(domain=[0, max_grade]), title=None, axis=alt.Axis(gridOpacity=0.4, tickCount=5)),
        color=color,
        tooltip=[alt.Tooltip('Grupo:N'), alt.Tooltip('Entrega:N'), alt.Tooltip('Promedio:Q', format='.1f'), alt.Tooltip('Alumnos:Q')]
    )
    rule_df = pd.DataFrame({'y': [min_pass], 'label': [f"Mínimo aprobatorio ({min_pass:g})"]})
    rule = alt.Chart(rule_df).mark_rule(strokeDash=[4, 4], color='#94a3b8', strokeWidth=1.5).encode(y='y:Q')
    rule_text = alt.Chart(rule_df).mark_text(align='left', dx=4, dy=-7, color='#64748b', fontSize=11).encode(
        y='y:Q', x=alt.value(0), text='label:N'
    )
    st.altair_chart((rule + rule_text + line).properties(height=280), width='stretch')


# ------------------------------------------------------------------------------
# Seguimiento: alumnos que el docente ya atendió
# ------------------------------------------------------------------------------
def load_followups(folder_id):
    return _norm_table(load_teacher_table(folder_id, SEGUIMIENTO_FILE), SEGUIMIENTO_COLS)


def latest_followups(followups):
    """{(grupo, alumno): última fila de seguimiento}."""
    if followups is None or followups.empty:
        return {}
    fu = followups.sort_values('Fecha')
    return {(r['Grupo'], r['Alumno']): r.to_dict() for _, r in fu.iterrows()}


def last_evaluated_date(tasks, grupo, alumno):
    """Fecha de entrega de la actividad evaluada más reciente del alumno (la información "nueva" más reciente)."""
    t = tasks[(tasks['Grupo'] == grupo) & (tasks['Nombre del estudiante'] == alumno) & ~tasks['status'].isin(NOT_EVALUATED_STATUSES)]
    d = t['dt_entrega'].dropna()
    return d.max().date() if not d.empty else None


def split_attended(att_df, tasks, followups):
    """
    Separa la lista de atención en (pendientes, atendidos). Un alumno marcado como atendido no vuelve a la
    lista hasta que se cierra una entrega posterior a la fecha en que se le atendió (hay información nueva).
    """
    if att_df.empty:
        return att_df, att_df
    latest = latest_followups(followups)
    hidden = []
    for idx, r in att_df.iterrows():
        fu = latest.get((r['Grupo'], r['Nombre del estudiante']))
        if not fu:
            continue
        try:
            fu_date = pd.to_datetime(fu['Fecha']).date()
        except Exception:
            continue
        last = last_evaluated_date(tasks, r['Grupo'], r['Nombre del estudiante'])
        if last is None or fu_date >= last:
            hidden.append(idx)
    attended = att_df.loc[hidden].copy()
    if not attended.empty:
        attended['_fu'] = [latest[(g, n)] for g, n in zip(attended['Grupo'], attended['Nombre del estudiante'])]
    return att_df.drop(index=hidden), attended


def render_followup_controls(folder_id, pending_df, attended_df):
    """Controles discretos para marcar alumnos como atendidos (con nota) o volver a mostrarlos."""
    _show_pending_upload("dl_pending_followup")
    if not pending_df.empty:
        with st.expander("✅ Ya atendí a un alumno de esta lista"), st.form("fu_form", clear_on_submit=True, border=False):
            labels = {f"{r['Nombre del estudiante']} · {r['Grupo']}": (r['Grupo'], r['Nombre del estudiante']) for _, r in pending_df.iterrows()}
            who = st.selectbox("Alumno:", list(labels), key="fu_student")
            note = st.text_input("Nota (opcional):", key="fu_note", max_chars=200,
                                 placeholder="Ej. Platiqué con él y con su mamá; se comprometió a entregar el viernes.")
            st.caption("Saldrá de la lista. Si en una entrega posterior vuelve a cumplir algún motivo, aparecerá de nuevo.")
            if st.form_submit_button("Marcar como atendido", type="primary"):
                grupo, alumno = labels[who]
                table = _norm_table(read_teacher_table(folder_id, SEGUIMIENTO_FILE), SEGUIMIENTO_COLS)
                new = pd.DataFrame([{'Grupo': grupo, 'Alumno': alumno, 'Fecha': now_local().strftime('%Y-%m-%d %H:%M'),
                                     'Nota': note.strip()}])
                _finish_save([save_teacher_table(folder_id, SEGUIMIENTO_FILE, pd.concat([table, new], ignore_index=True), "Seguimiento")])
    if not attended_df.empty:
        with st.expander(f"✔️ Atendidos ({len(attended_df)}) · reaparecen si hay información nueva"):
            for _, r in attended_df.iterrows():
                fu = r['_fu']
                when = format_short_date(pd.to_datetime(fu['Fecha']), with_time=False) if fu.get('Fecha') else ""
                st.markdown(f"**{html.escape(r['Nombre del estudiante'])}** · {html.escape(str(r['Grupo']))} · atendido el {when}"
                            + (f"  \n<span style='color:#475569'>📝 {html.escape(fu['Nota'])}</span>" if fu.get('Nota') else ""),
                            unsafe_allow_html=True)
            labels = {f"{r['Nombre del estudiante']} · {r['Grupo']}": (r['Grupo'], r['Nombre del estudiante']) for _, r in attended_df.iterrows()}
            c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
            with c1:
                who = st.selectbox("Volver a mostrar en la lista:", list(labels), key="fu_undo_student")
            with c2:
                if st.button("↺ Volver a mostrar", width='stretch', key="fu_undo"):
                    grupo, alumno = labels[who]
                    table = _norm_table(read_teacher_table(folder_id, SEGUIMIENTO_FILE), SEGUIMIENTO_COLS)
                    mine = table[(table['Grupo'] == grupo) & (table['Alumno'] == alumno)]
                    if not mine.empty:
                        table = table.drop(index=mine.sort_values('Fecha').index[-1])
                    _finish_save([save_teacher_table(folder_id, SEGUIMIENTO_FILE, table, "Seguimiento")])


def render_teacher_summary(tasks, block_summary, criteria_config, color_map, asignatura="la materia", attendance=None, folder_id=None, parcial_label=None):
    """Pestaña 'Resumen y acciones' del panel docente."""
    cfg = criteria_config if isinstance(criteria_config, dict) else {}
    class_df = build_class_insights(tasks, block_summary, cfg)
    if class_df.empty:
        st.info("Aún no hay información suficiente para el resumen.")
        return
    att_df, rec_df = build_attention_lists(class_df, cfg, attendance)
    att_df, attended_df = split_attended(att_df, tasks, load_followups(folder_id))
    scale = int(cfg.get('escala_maxima', 10))
    step = 1.0 if scale == 10 else 10.0

    # --- Indicadores clave
    total = len(class_df)
    n_riesgo = int((class_df['status'] == 'En riesgo').sum())
    n_bajaron = int((class_df['trend'].fillna(0) <= -step).sum())

    evaluated = tasks[~tasks['status'].isin(NOT_EVALUATED_STATUSES)]
    pending_dates = set(tasks.loc[tasks['status'].isin(NOT_EVALUATED_STATUSES), 'Fecha de entrega'])
    closed = evaluated[~evaluated['Fecha de entrega'].isin(pending_dates)].dropna(subset=['dt_entrega'])
    on_time_txt, on_time_delta, on_time_label = "—", "", "⏰ A tiempo (última semana)"
    if not closed.empty:
        # Ventanas de 7 días (los grupos pueden tener fechas de entrega distintas)
        last_dt = closed['dt_entrega'].max()
        week = closed[closed['dt_entrega'] > last_dt - pd.Timedelta(days=7)]
        prev_week = closed[(closed['dt_entrega'] <= last_dt - pd.Timedelta(days=7)) & (closed['dt_entrega'] > last_dt - pd.Timedelta(days=14))]
        last_pct = week['status'].astype(str).str.startswith('A tiempo').mean() * 100
        on_time_txt = f"{last_pct:.0f}%"
        if not prev_week.empty:
            diff = last_pct - prev_week['status'].astype(str).str.startswith('A tiempo').mean() * 100
            arrow = "▲" if diff >= 0 else "▼"
            cls = "delta-up" if diff >= 0 else "delta-down"
            on_time_delta = f" <small class='{cls}'>{arrow} {abs(diff):.0f} pts vs. semana anterior</small>"

    worst_txt, worst_detail = "—", ""
    by_task = evaluated.groupby('Nombre de la tarea').agg(
        tasa=('is_completed', 'mean'), n=('is_completed', 'size'), tipo=('Tipo de tarea', 'first')
    )
    by_task = by_task[by_task['n'] >= 3]
    if not by_task.empty:
        worst = by_task['tasa'].idxmin()
        worst_txt = f"{by_task.loc[worst, 'tasa'] * 100:.0f}% <small>la completó</small>"
        worst_detail = f"<div class='mini-sub'>{html.escape(str(worst))}</div>"

    stats = [
        ("🚨 En riesgo", f"{n_riesgo} <small>de {total}</small>", ""),
        ("📉 Bajaron en su último bloque", f"{n_bajaron}", ""),
        (on_time_label, f"{on_time_txt}{on_time_delta}", ""),
        ("🧩 Actividad con menos entregas", worst_txt, worst_detail),
    ]
    st.markdown(
        "<div class='mini-stats teacher-stats'>" + "".join(
            f"<div class='mini-stat'><div class='mini-label'>{lbl}</div><div class='mini-val'>{val}</div>{sub}</div>"
            for lbl, val, sub in stats
        ) + "</div>",
        unsafe_allow_html=True
    )

    # --- Entrega en curso: quién ya completó y quién no
    in_progress = tasks[tasks['status'] == 'En curso']
    if not in_progress.empty:
        next_dt = in_progress['dt_entrega'].min()
        due_rows = tasks[tasks['dt_entrega'] == next_dt]
        per_student = due_rows.groupby(['Grupo', 'Nombre del estudiante'])['status'].agg(
            lambda s: int((s == 'En curso').sum())
        )
        done = int((per_student == 0).sum())
        st.info(f"📅 **Próxima entrega: {format_short_date(next_dt)} ({relative_days_label(next_dt)})** — "
                f"{done} de {len(per_student)} alumnos ya completaron todo.")
        missing = per_student[per_student > 0].reset_index().rename(columns={'status': 'Actividades por entregar'})
        if not missing.empty:
            with st.expander(f"Ver los {len(missing)} alumnos que aún no completan esta entrega (para enviarles un recordatorio)"):
                st.dataframe(missing.sort_values(['Grupo', 'Nombre del estudiante']), hide_index=True, width='stretch')
        with st.expander("📢 Mensaje de recordatorio para el grupo"):
            activities = due_rows['Nombre de la tarea'].dropna().astype(str).unique().tolist()
            render_copy_message(build_group_reminder(next_dt, activities, asignatura), key="wa_group_reminder")

    # --- Listas de acción
    export_cols_att = ['Prioridad', 'Nombre del estudiante', 'Grupo', 'Promedio', 'Motivos', 'Acción sugerida', 'Atrasadas']
    export_cols_rec = ['Nombre del estudiante', 'Grupo', 'Promedio', 'Motivo de reconocimiento']

    st.markdown("#### 🆘 Necesitan atención" + (f" · {parcial_label}" if parcial_label else ""))
    if att_df.empty:
        st.success("🎉 Ningún alumno requiere atención especial con los filtros actuales."
                   + (f" ({len(attended_df)} ya atendido(s).)" if not attended_df.empty else ""))
    else:
        st.caption(f"{len(att_df)} alumno(s), ordenados por prioridad. Para ver el detalle de alguno, usa la sección **🔍 Alumno**.")
        cards = []
        for _, r in att_df.iterrows():
            high = r['Prioridad'].endswith('Alta')
            reasons = "".join(f"<li>{html.escape(x)}</li>" for x in r['_reasons'])
            actions = "".join(f"<li>{html.escape(x)}</li>" for x in r['_actions'])
            cards.append(f"""
            <div class="student-card" style="border-left-color: {'#dc2626' if high else '#d97706'};">
                <div class="sc-head">
                    <div><span class="sc-name">{html.escape(r['Nombre del estudiante'])}</span>
                    <span class="sc-meta">{html.escape(str(r['Grupo']))} · Promedio {r['Promedio']}{f" · {r['Atrasadas']} atrasada(s)" if r['Atrasadas'] else ""}</span></div>
                    <span class="sc-badge" style="background: {'#fee2e2' if high else '#fef3c7'}; color: {'#991b1b' if high else '#92400e'};">{r['Prioridad']}</span>
                </div>
                <div class="sc-body">
                    <div><div class="sc-label">Motivos</div><ul>{reasons}</ul></div>
                    <div><div class="sc-label">Acción sugerida</div><ul>{actions}</ul></div>
                </div>
            </div>""")
        st.markdown(compact_html("<div class='student-cards'>" + "".join(cards) + "</div>"), unsafe_allow_html=True)
        st.download_button(
            "📥 Descargar lista (CSV)", att_df[export_cols_att].to_csv(index=False).encode('utf-8-sig'),
            file_name=f"Alumnos_atencion_{now_local().strftime('%Y%m%d')}.csv", mime="text/csv",
            key="dl_attention"
        )
    render_followup_controls(folder_id, att_df, attended_df)

    st.markdown("#### 🌟 Para reconocer")
    if rec_df.empty:
        st.caption("Aún no hay alumnos con logros destacados en este periodo.")
    else:
        st.caption("Reconócelos en clase: quienes mejoraron aparecen primero, porque el esfuerzo también cuenta.")
        cards = []
        for _, r in rec_df.iterrows():
            kudos = "".join(f"<li>{html.escape(x)}</li>" for x in r['_kudos'])
            cards.append(f"""
            <div class="student-card" style="border-left-color: #16a34a;">
                <div class="sc-head">
                    <div><span class="sc-name">{html.escape(r['Nombre del estudiante'])}</span>
                    <span class="sc-meta">{html.escape(str(r['Grupo']))} · Promedio {r['Promedio']}</span></div>
                </div>
                <ul>{kudos}</ul>
            </div>""")
        st.markdown(compact_html("<div class='student-cards'>" + "".join(cards) + "</div>"), unsafe_allow_html=True)
        st.download_button(
            "📥 Descargar lista (CSV)", rec_df[export_cols_rec].to_csv(index=False).encode('utf-8-sig'),
            file_name=f"Alumnos_reconocimiento_{now_local().strftime('%Y%m%d')}.csv", mime="text/csv",
            key="dl_recognition"
        )

    render_study_pairs(class_df)

    st.markdown("#### 📈 Tendencia por grupo")
    st.caption("Promedio de cada grupo en los bloques ya cerrados.")
    render_group_trend_chart(block_summary, tasks, cfg, color_map)


# ==============================================================================
# FASE 3: ANÁLISIS POR ACTIVIDAD, PAREJAS DE ESTUDIO Y MENSAJES SUGERIDOS
# ==============================================================================
def build_task_analysis(tasks):
    """Una fila por actividad: participación, puntualidad, aciertos e intentos."""
    active = tasks[tasks['status'] != 'Programada']
    if active.empty:
        return pd.DataFrame()
    rows = []
    for (name, tipo), t in active.groupby(['Nombre de la tarea', 'Tipo de tarea']):
        n = len(t)
        completed = t[t['is_completed'].astype(bool)]
        in_progress = (t['status'] == 'En curso').any()
        exercises = completed[completed['total_count'] > 0]
        aciertos = (exercises['correct_count'] / exercises['total_count']).mean() * 100 if not exercises.empty else None
        intentos = exercises['attempts_count'].mean() if not exercises.empty else None
        pct_done = len(completed) / n * 100
        pct_on_time = t['status'].astype(str).str.startswith('A tiempo').sum() / n * 100

        issues = []
        if not in_progress and pct_done < 60:
            issues.append(f"solo el {pct_done:.0f}% la completó")
        if aciertos is not None and len(exercises) >= 3 and aciertos < 70:
            issues.append(f"aciertos promedio de {aciertos:.0f}%")
        if in_progress:
            signal = "⏳ En curso"
        elif issues:
            signal = "⚠️ Repasar"
        else:
            signal = "✅ Bien"
        rows.append({
            'Señal': signal,
            'Actividad': name,
            'Tipo': tipo,
            'Grupos': ", ".join(sorted(t['Grupo'].dropna().astype(str).unique())),
            'Entrega': format_short_date(t['dt_entrega'].min(), with_time=False),
            'Completada': round(pct_done, 0),
            'A tiempo': round(pct_on_time, 0),
            'Aciertos': round(aciertos, 0) if aciertos is not None else None,
            'Intentos prom.': round(intentos, 1) if intentos is not None else None,
            'Sin entregar': n - len(completed),
            '_issues': issues,
            '_dt': t['dt_entrega'].min(),
        })
    df = pd.DataFrame(rows)
    order = {"⚠️ Repasar": 0, "⏳ En curso": 1, "✅ Bien": 2}
    df['_ord'] = df['Señal'].map(order)
    return df.sort_values(['_ord', 'Completada', '_dt']).drop(columns='_ord')


def render_task_analysis(tasks):
    st.caption("Cómo les fue a tus alumnos en cada actividad. Si muchos no la completaron o tuvieron pocos aciertos, "
               "probablemente el tema necesita repasarse en clase.")
    df = build_task_analysis(tasks)
    if df.empty:
        st.info("Aún no hay actividades iniciadas en este periodo.")
        return

    flagged = df[df['Señal'] == "⚠️ Repasar"]
    if flagged.empty:
        st.success("✅ Ninguna actividad cerrada muestra señales de dificultad.")
    else:
        items = "".join(
            f"<li><strong>{html.escape(str(r['Actividad']))}</strong> ({html.escape(str(r['Grupos']))}): {html.escape(', '.join(r['_issues']))}</li>"
            for _, r in flagged.head(5).iterrows()
        )
        st.markdown(compact_html(f"""
        <div class="student-card" style="border-left-color: #d97706;">
            <div class="sc-label">🧩 Temas que conviene repasar</div>
            <ul>{items}</ul>
        </div>"""), unsafe_allow_html=True)
        st.write("")

    show = df.drop(columns=['_issues', '_dt'])
    for col in ['Aciertos', 'Intentos prom.']:
        show[col] = pd.to_numeric(show[col], errors='coerce')
    st.dataframe(
        show, hide_index=True, width='stretch', height=min(520, 40 + len(show) * 36),
        column_config={
            'Señal': st.column_config.TextColumn(width="medium"),
            'Actividad': st.column_config.TextColumn(width="large"),
            'Completada': st.column_config.ProgressColumn("Completada", format="%d%%", min_value=0, max_value=100),
            'A tiempo': st.column_config.ProgressColumn("A tiempo", format="%d%%", min_value=0, max_value=100),
            'Aciertos': st.column_config.NumberColumn("Aciertos (ejercicios)", format="%d%%"),
            'Intentos prom.': st.column_config.NumberColumn(format="%.1f"),
        }
    )
    st.download_button(
        "📥 Descargar análisis (CSV)", show.to_csv(index=False).encode('utf-8-sig'),
        file_name=f"Analisis_actividades_{now_local().strftime('%Y%m%d')}.csv", mime="text/csv", key="dl_task_analysis"
    )

    st.markdown("##### ¿Quién no la ha completado?")
    options = df['Actividad'].tolist()
    selected = st.selectbox("Actividad:", options, key="task_analysis_select")
    pending = tasks[(tasks['Nombre de la tarea'] == selected) & ~tasks['is_completed'].astype(bool) & (tasks['status'] != 'Programada')]
    if pending.empty:
        st.success("🎉 Todos los alumnos la completaron.")
    else:
        st.dataframe(
            pending[['Grupo', 'Nombre del estudiante', 'status']].rename(columns={'status': 'Estado'})
            .sort_values(['Grupo', 'Nombre del estudiante']),
            hide_index=True, width='stretch'
        )


def build_study_pairs(class_df):
    """
    Dentro de cada grupo, empareja a quien va mejor con quien más necesita apoyo
    (el mejor promedio con el más bajo, y así sucesivamente).
    """
    pairs, unpaired = [], []
    for grupo, g in class_df.groupby('Grupo'):
        tutors = g[g['status'].isin(['Excelente', 'Bien'])].sort_values(['avg', 'on_time_streak'], ascending=[False, False])
        learners = g[g['status'].isin(['En riesgo', 'Regular'])].sort_values('avg')
        for (_, t), (_, l) in zip(tutors.iterrows(), learners.iterrows()):
            pairs.append({
                'Grupo': grupo,
                'Apoya': t['Nombre del estudiante'], 'Promedio (apoya)': f"{t['avg']:.1f}",
                'Recibe apoyo': l['Nombre del estudiante'], 'Promedio (recibe)': f"{l['avg']:.1f}",
                '_note': "Dejó de entregar: conviene hablar primero con él/ella" if l['missing_streak'] >= 2 else "",
            })
        for _, l in learners.iloc[len(tutors):].iterrows():
            unpaired.append(f"{l['Nombre del estudiante']} ({grupo})")
    return pd.DataFrame(pairs), unpaired


def render_study_pairs(class_df):
    st.markdown("#### 🤝 Parejas de estudio sugeridas")
    pairs, unpaired = build_study_pairs(class_df)
    if pairs.empty:
        st.caption("No hay suficientes alumnos con buen desempeño y alumnos que necesiten apoyo en el mismo grupo para sugerir parejas.")
        return
    st.caption("Dentro de cada grupo se empareja al mejor promedio con el más bajo. Es solo una sugerencia: tú conoces mejor a tus alumnos.")
    cards = []
    for _, p in pairs.iterrows():
        note = f"<div class='sc-meta' style='margin-top:4px;'>⚠️ {html.escape(p['_note'])}</div>" if p['_note'] else ""
        cards.append(f"""
        <div class="student-card" style="border-left-color: #2563eb;">
            <div class="sc-meta">{html.escape(str(p['Grupo']))}</div>
            <div class="pair-row">
                <div><span class="sc-label">Apoya</span><span class="sc-name">{html.escape(p['Apoya'])}</span><span class="sc-meta">Promedio {p['Promedio (apoya)']}</span></div>
                <div class="pair-arrow">⟷</div>
                <div><span class="sc-label">Recibe apoyo</span><span class="sc-name">{html.escape(p['Recibe apoyo'])}</span><span class="sc-meta">Promedio {p['Promedio (recibe)']}</span></div>
            </div>
            {note}
        </div>""")
    st.markdown(compact_html("<div class='student-cards'>" + "".join(cards) + "</div>"), unsafe_allow_html=True)
    if unpaired:
        st.caption("Sin pareja disponible en su grupo: " + ", ".join(unpaired))
    st.download_button(
        "📥 Descargar parejas (CSV)", pairs.drop(columns='_note').to_csv(index=False).encode('utf-8-sig'),
        file_name=f"Parejas_estudio_{now_local().strftime('%Y%m%d')}.csv", mime="text/csv", key="dl_pairs"
    )


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _pending_parts(ins):
    parts = []
    if len(ins['overdue']):
        parts.append(_plural(len(ins['overdue']), "actividad atrasada", "actividades atrasadas"))
    if len(ins['upcoming']):
        parts.append(_plural(len(ins['upcoming']), "actividad por entregar", "actividades por entregar"))
    return " y ".join(parts)


def _meaningful_gain(avg, best):
    """True si la mejora se nota con un decimal (evita 'puede llegar a 8.8' cuando ya tiene 8.8)."""
    return best is not None and avg is not None and round(best, 1) > round(avg, 1)


def build_student_message(ins, student_name, asignatura, teacher_name, audience):
    """Mensaje listo para copiar: tono de reconocimiento o de apoyo según el desempeño."""
    name = str(student_name).title()
    status, avg, best = ins['status'], ins['avg'], ins['avg_best']
    parts = _pending_parts(ins)
    can_improve = _meaningful_gain(avg, best)
    n_pend = len(ins['overdue']) + len(ins['upcoming'])
    las = "la" if n_pend == 1 else "las"
    streak = f" y lleva {ins['streak']} bloques seguidos entregando todo a tiempo" if ins['streak'] >= 2 else ""

    if audience == 'alumno':
        sign = f"\n\n— {teacher_name}"
        if status is None:
            return f"¡Hola {name}! Bienvenido(a) a {asignatura}. Recuerda entregar a tiempo tus actividades de Khan Academy: cada una cuenta para tu calificación.{sign}"
        streak_a = streak.replace("lleva", "llevas")
        if status == 'Excelente':
            return f"¡Hola {name}! Quiero felicitarte por tu trabajo en {asignatura}: tienes un promedio de {avg:.1f}{streak_a}. Tu constancia se nota. ¡Sigue con ese ritmo todo el semestre! 🌟{sign}"
        pend = f" Tienes {parts} en Khan Academy; si {las} entregas, tu promedio puede llegar a {best:.1f}." if (parts and can_improve) else ""
        if status == 'Bien':
            gap = max(0.0, ins['min_excelente'] - avg)
            return f"¡Hola {name}! Vas muy bien en {asignatura}, con promedio de {avg:.1f}. Estás a {gap:.1f} de llegar a Excelente.{pend} ¡Tú puedes! 💪{sign}"
        if status == 'Regular':
            return f"Hola {name}, vas aprobando {asignatura} con {avg:.1f}, pero sé que puedes dar más.{pend} Si algún tema se te complica, pregúntame en clase.{sign}"
        recovery = f": si entregas tus {parts}, tu promedio puede subir a {best:.1f}" if (parts and can_improve) else ""
        return f"Hola {name}, quiero ayudarte en {asignatura}. Tu promedio va en {avg:.1f}, pero todavía estás a tiempo de recuperarte{recovery}. ¿Platicamos en la próxima clase para hacer un plan juntos? Cuenta conmigo.{sign}"

    # Mensaje para la familia
    intro = f"Buen día. Le escribe {teacher_name}, docente de {asignatura} del CBTA 24. Le comparto el avance de {name}"
    close = "\n\nQuedo a sus órdenes. Saludos cordiales."
    pend = f" Tiene {parts} en Khan Academy." if parts else ""
    if status is None:
        return f"{intro}: aún no tiene actividades evaluadas en este periodo.{pend} Le agradezco su apoyo para que entregue sus actividades a tiempo.{close}"
    if status == 'Excelente':
        return f"{intro}: tiene un promedio de {avg:.1f} (Excelente){streak}. Le felicito por su acompañamiento; es un gusto tener a {name} en clase.{close}"
    if status == 'Bien':
        return f"{intro}: tiene un promedio de {avg:.1f} (Bien).{pend} Le agradezco su apoyo para que mantenga este ritmo.{close}"
    if status == 'Regular':
        return f"{intro}: tiene un promedio de {avg:.1f}, que es aprobatorio pero puede mejorar.{pend} Le pido su apoyo para que revise con {name} sus actividades pendientes.{close}"
    recovery = f" Si entrega sus pendientes, su promedio puede subir a {best:.1f}." if (parts and can_improve) else ""
    return (f"{intro}: actualmente su promedio es de {avg:.1f}, por debajo del mínimo aprobatorio.{pend} Todavía está a tiempo de recuperarse.{recovery} "
            f"Le pido su apoyo para revisar juntos sus pendientes y, si lo considera conveniente, podemos agendar una reunión.{close}")


def build_group_reminder(due_dt, activities, asignatura):
    lines = "\n".join(f"• {a}" for a in activities)
    return (f"📢 Recordatorio de {asignatura}: el {format_short_date(due_dt)} ({relative_days_label(due_dt)}) vence la entrega de:\n"
            f"{lines}\n\n¡No lo dejes para el último momento! Revisa tus pendientes y tu calificación en el portal. 💪")


def render_copy_message(text, key):
    """Muestra el mensaje con botón de copiar y un acceso directo a WhatsApp."""
    from urllib.parse import quote
    st.code(text, language=None, wrap_lines=True)
    st.link_button("💬 Abrir en WhatsApp", f"https://wa.me/?text={quote(text)}", key=key)


# ==============================================================================
# FASE 4: LISTA OFICIAL DEL GRUPO, VÍNCULO DE CUENTAS DE KHAN Y ACCESO CON PIN
# ==============================================================================
ROSTER_FILE = "lista_alumnos.xlsx"
LINKS_FILE = "vinculos_khan.xlsx"
ROSTER_COLS = ['ID', 'Matrícula', 'Código provisional', 'Nombre', 'Grupo', 'PIN']
LINK_COLS = ['Cuenta de Khan', 'Grupo Khan', 'ID alumno']
NO_LINK_LABEL = "— Sin vincular —"
_NAME_STOPWORDS = {'de', 'del', 'la', 'las', 'los', 'y', 'da', 'do', 'van', 'von'}


def _drive_ready(folder_id):
    return bool(get_drive_service()) and bool(folder_id) and not str(folder_id).startswith('PEGA_AQUÍ')


@st.cache_data(ttl=600)
def load_teacher_table(folder_id, filename):
    """Versión en caché de read_teacher_table (para mostrar datos sin consultar Drive en cada clic)."""
    return read_teacher_table(folder_id, filename)


def read_teacher_table(folder_id, filename):
    """
    Lee una tabla (.xlsx) de la carpeta del docente en Drive, o de datos/ en modo local. Todo como texto.
    Antes de guardar siempre se usa esta lectura directa (sin caché), para no sobrescribir cambios
    hechos a mano en el archivo o desde otro dispositivo.
    """
    try:
        if _drive_ready(folder_id):
            service = get_drive_service()
            item = find_drive_item(service, filename, folder_id, is_folder=False)
            if not item:
                return pd.DataFrame()
            df = read_drive_excel(service, item['id'], dtype=str)
        else:
            path = os.path.join(DATA_DIR, filename)
            if not os.path.exists(path):
                return pd.DataFrame()
            df = pd.read_excel(path, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        return df.fillna('')
    except Exception as e:
        st.warning(f"No se pudo leer {filename}: {e}")
        return pd.DataFrame()


def table_to_xlsx_bytes(df, sheet_name="Hoja1"):
    buff = io.BytesIO()
    with pd.ExcelWriter(buff, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return buff.getvalue()


def save_teacher_table(folder_id, filename, df, sheet_name="Hoja1"):
    """
    Guarda una tabla como .xlsx en la carpeta del docente (o en datos/ en modo local).
    Retorna (nivel, mensaje, guardado). Si Drive no permite crear el archivo, deja los bytes
    listos para que el docente lo descargue y lo suba él mismo a su carpeta.
    """
    data = table_to_xlsx_bytes(df, sheet_name)
    mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if not _drive_ready(folder_id):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, filename), "wb") as f:
                f.write(data)
            load_teacher_table.clear()
            list_teacher_file_names.clear()
            return ('success', f"✅ {filename} guardado (modo local).", True)
        except Exception as e:
            return ('error', f"No se pudo guardar {filename}: {e}", False)

    service = get_drive_service()
    try:
        existing = find_drive_item(service, filename, folder_id, is_folder=False)
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype, resumable=True)
        if existing:
            service.files().update(fileId=existing['id'], media_body=media, supportsAllDrives=True).execute()
        else:
            service.files().create(body={'name': filename, 'parents': [folder_id]}, media_body=media,
                                   supportsAllDrives=True).execute()
        load_teacher_table.clear()
        list_teacher_file_names.clear()
        pending = st.session_state.get('_pending_upload')
        if pending and pending[0] == filename:
            st.session_state.pop('_pending_upload', None)
        return ('success', f"✅ {filename} guardado en tu carpeta de Google Drive.", True)
    except HttpError as e:
        status = getattr(getattr(e, 'resp', None), 'status', None)
        if 'storage quota' in str(e).lower() or status == 403:
            st.session_state['_pending_upload'] = (filename, data)
            return ('warning', f"⚠️ Google Drive no permitió crear {filename} automáticamente. Descárgalo con el botón de abajo y súbelo a tu carpeta (o usa **⚙️ Ajustes → 🚀 Primeros pasos** para descargar todas las plantillas); a partir de ahí el sistema lo actualizará solo.", False)
        if status in (429, 500, 503):
            return ('error', "⚠️ Google Drive está ocupado. Intenta de nuevo en unos segundos.", False)
        return ('error', f"Error al guardar {filename} en Google Drive: {e}", False)
    except Exception as e:
        return ('error', f"Error inesperado al guardar {filename}: {e}", False)


def name_tokens(name):
    """'ALBORES CLEMENTE Paulo César' -> ('albores', 'cesar', 'clemente', 'paulo') sin acentos ni orden."""
    import unicodedata
    s = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().lower()
    return tuple(sorted(t for t in re.findall(r'[a-z]+', s) if len(t) > 1 and t not in _NAME_STOPWORDS))


def name_similarity(a, b):
    """0..1. Considera el orden distinto de nombre/apellidos y nombres abreviados en Khan."""
    from difflib import SequenceMatcher
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    jaccard = len(sa & sb) / len(sa | sb)
    if len(sa & sb) >= 2 and (sa <= sb or sb <= sa):
        jaccard = max(jaccard, 0.85)  # p. ej. "Paulo Albores" dentro de "Albores Clemente Paulo Cesar"
    seq = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    return round(max(jaccard, 0.5 * jaccard + 0.5 * seq), 3)


def _normalize_group(value):
    value = str(value or '').strip()
    return extract_group(value) if value else ''


def normalize_roster(df):
    """Detecta columnas (matrícula, nombre, grupo...) y regresa la lista con las columnas estándar."""
    if df is None or df.empty:
        return pd.DataFrame(columns=ROSTER_COLS)
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        cl = c.lower()
        if cl == 'id':
            rename[c] = 'ID'
        elif 'matr' in cl:
            rename[c] = 'Matrícula'
        elif 'provisional' in cl or cl.startswith('código') or cl.startswith('codigo'):
            rename[c] = 'Código provisional'
        elif 'nombre' in cl or 'alumno' in cl or 'estudiante' in cl:
            rename[c] = 'Nombre'
        elif 'grupo' in cl:
            rename[c] = 'Grupo'
        elif 'pin' in cl:
            rename[c] = 'PIN'
    df = df.rename(columns=rename)
    for col in ROSTER_COLS:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str).str.strip().replace({'nan': ''})
    df['Matrícula'] = df['Matrícula'].str.replace(r'\.0$', '', regex=True)
    df['PIN'] = df['PIN'].str.replace(r'\.0$', '', regex=True)
    df['Grupo'] = df['Grupo'].apply(_normalize_group)
    df = df[df['Nombre'] != ''].copy()
    return ensure_roster_ids(df[ROSTER_COLS].reset_index(drop=True))


def ensure_roster_ids(roster):
    """Asigna ID interno estable y código provisional a quien aún no tiene matrícula."""
    roster = roster.copy()
    used_ids = set(roster.loc[roster['ID'] != '', 'ID'])
    n = 1
    for i in roster.index[roster['ID'] == '']:
        while f"A{n:04d}" in used_ids:
            n += 1
        roster.at[i, 'ID'] = f"A{n:04d}"
        used_ids.add(f"A{n:04d}")
    used_codes = set(roster.loc[roster['Código provisional'] != '', 'Código provisional'].str.upper())
    for i in roster.index[(roster['Matrícula'] == '') & (roster['Código provisional'] == '')]:
        base = "P" + re.sub(r'[^0-9A-Za-z]', '', roster.at[i, 'Grupo']).upper()
        k = 1
        while f"{base}{k:02d}" in used_codes:
            k += 1
        roster.at[i, 'Código provisional'] = f"{base}{k:02d}"
        used_codes.add(f"{base}{k:02d}")
    return roster


def roster_login_id(row):
    return row['Matrícula'] if str(row['Matrícula']).strip() else row['Código provisional']


def roster_label(row):
    who = roster_login_id(row)
    return f"{row['Nombre']} ({row['Grupo'] or 'sin grupo'} · {who})"


def generate_missing_pins(roster):
    import secrets
    roster = roster.copy()
    count = 0
    for i in roster.index[roster['PIN'] == '']:
        roster.at[i, 'PIN'] = f"{secrets.randbelow(10**6):06d}"
        count += 1
    return roster, count


def merge_roster_upload(current, uploaded):
    """Agrega o actualiza alumnos sin perder su ID, PIN ni sus vínculos con Khan."""
    current = normalize_roster(current)
    uploaded = normalize_roster(uploaded)
    if current.empty:
        return uploaded
    merged = current.copy()
    for _, u in uploaded.iterrows():
        match = pd.Series(False, index=merged.index)
        if u['Matrícula']:
            match = merged['Matrícula'] == u['Matrícula']
        if not match.any():
            toks = name_tokens(u['Nombre'])
            match = merged['Nombre'].apply(name_tokens).eq(toks) & ((merged['Grupo'] == u['Grupo']) | (u['Grupo'] == ''))
        if match.any():
            i = merged.index[match][0]
            for col in ['Matrícula', 'Nombre', 'Grupo']:
                if u[col]:
                    merged.at[i, col] = u[col]
        else:
            new_row = u.copy()
            new_row['ID'] = ''
            new_row['PIN'] = u['PIN']
            merged = pd.concat([merged, new_row.to_frame().T], ignore_index=True)
    return ensure_roster_ids(merged)


def normalize_links(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=LINK_COLS)
    df = df.copy()
    for col in LINK_COLS:
        if col not in df.columns:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str).str.strip()
    df['Grupo Khan'] = df['Grupo Khan'].apply(_normalize_group)
    return df[LINK_COLS][df['Cuenta de Khan'] != ''].drop_duplicates(['Cuenta de Khan', 'Grupo Khan'], keep='last')


def khan_accounts(raw_df):
    """Cuentas de Khan presentes en los reportes: (nombre, grupo, actividades)."""
    if raw_df.empty or 'Nombre del estudiante' not in raw_df.columns:
        return pd.DataFrame(columns=['Cuenta de Khan', 'Grupo Khan', 'Actividades'])
    acc = raw_df.groupby(['Nombre del estudiante', 'Grupo']).size().reset_index(name='Actividades')
    return acc.rename(columns={'Nombre del estudiante': 'Cuenta de Khan', 'Grupo': 'Grupo Khan'})


def build_link_map(raw_df, roster, links):
    """
    (cuenta de Khan, grupo) -> ID del alumno. Usa los vínculos guardados por el docente y,
    para el resto, las coincidencias exactas de nombre (mismas palabras en cualquier orden).
    """
    if roster.empty:
        return {}
    link_map = {}
    saved = {(r['Cuenta de Khan'], r['Grupo Khan']): r['ID alumno'] for _, r in links.iterrows()}
    roster_tokens = [(r['ID'], r['Grupo'], name_tokens(r['Nombre'])) for _, r in roster.iterrows()]
    for _, a in khan_accounts(raw_df).iterrows():
        key = (a['Cuenta de Khan'], a['Grupo Khan'])
        if key in saved:
            if saved[key]:
                link_map[key] = saved[key]
            continue
        toks = name_tokens(a['Cuenta de Khan'])
        exact = [rid for rid, grp, rt in roster_tokens if rt == toks and (not grp or grp == a['Grupo Khan'])]
        if len(exact) == 1:
            link_map[key] = exact[0]
    return link_map


def apply_roster_links(raw_df, roster, links):
    """
    Reemplaza el nombre de Khan por el de la lista oficial y combina las cuentas duplicadas
    de un mismo alumno, conservando el mejor resultado de cada actividad.
    """
    if raw_df.empty or roster.empty:
        return raw_df
    link_map = build_link_map(raw_df, roster, links)
    if not link_map:
        return raw_df
    by_id = roster.set_index('ID')
    df = raw_df.copy()
    df['Cuenta Khan'] = df['Nombre del estudiante']
    keys = list(zip(df['Nombre del estudiante'], df['Grupo']))
    ids = [link_map.get(k) for k in keys]
    df['ID alumno'] = ids
    linked = df['ID alumno'].notna() & df['ID alumno'].isin(by_id.index)
    df.loc[linked, 'Nombre del estudiante'] = df.loc[linked, 'ID alumno'].map(by_id['Nombre'])
    roster_group = df.loc[linked, 'ID alumno'].map(by_id['Grupo'])
    df.loc[linked, 'Grupo'] = roster_group.where(roster_group != '', df.loc[linked, 'Grupo'])

    # Mejor resultado por actividad: completada, más aciertos, entregada antes
    done = df['Última fecha de terminación'].astype(str).str.strip().replace({'nan': ''}).ne('') if 'Última fecha de terminación' in df.columns else pd.Series(False, index=df.index)
    correct = pd.to_numeric(df.get('Mayor número de preguntas correctas hasta ahora'), errors='coerce').fillna(-1) if 'Mayor número de preguntas correctas hasta ahora' in df.columns else pd.Series(0, index=df.index)
    df['_done'] = done.astype(int)
    df['_correct'] = correct
    df['_when'] = df['dt_terminacion'] if 'dt_terminacion' in df.columns else pd.NaT
    df = df.sort_values(['_done', '_correct', '_when'], ascending=[False, False, True], na_position='last')
    key_cols = [c for c in ASSIGNMENT_KEY_COLS if c in df.columns]
    df = df.drop_duplicates(subset=key_cols, keep='first').drop(columns=['_done', '_correct', '_when'])
    return df.sort_index()


def load_roster_and_links(folder_id):
    roster = normalize_roster(load_teacher_table(folder_id, ROSTER_FILE))
    links = normalize_links(load_teacher_table(folder_id, LINKS_FILE))
    return roster, links


def build_link_table(raw_df, roster, links):
    """Tabla para el docente: cada cuenta de Khan con su estado de vínculo o una sugerencia."""
    accounts = khan_accounts(raw_df)
    if accounts.empty:
        return accounts
    saved = {(r['Cuenta de Khan'], r['Grupo Khan']): r['ID alumno'] for _, r in links.iterrows()}
    link_map = build_link_map(raw_df, roster, links)
    labels = {r['ID']: roster_label(r) for _, r in roster.iterrows()}
    roster_rows = [(r['ID'], r['Grupo'], name_tokens(r['Nombre'])) for _, r in roster.iterrows()]
    rows = []
    for _, a in accounts.iterrows():
        key = (a['Cuenta de Khan'], a['Grupo Khan'])
        toks = name_tokens(a['Cuenta de Khan'])
        if key in saved and saved[key]:
            estado, rid = "✅ Vinculada", saved[key]
        elif key in saved:
            estado, rid = "🚫 Marcada sin vínculo", ''
        elif key in link_map:
            estado, rid = "✅ Coincidencia exacta", link_map[key]
        else:
            same_group = [x for x in roster_rows if x[1] == a['Grupo Khan']] or roster_rows
            best = max(same_group, key=lambda x: name_similarity(toks, x[2]), default=None)
            score = name_similarity(toks, best[2]) if best else 0
            if best and score >= 0.6:
                estado, rid = f"💡 Sugerencia ({score * 100:.0f}% parecido)", best[0]
            else:
                estado, rid = "❓ Sin vincular", ''
        rows.append({
            'Cuenta de Khan': a['Cuenta de Khan'],
            'Grupo Khan': a['Grupo Khan'],
            'Actividades': int(a['Actividades']),
            'Estado': estado,
            'Alumno de la lista': labels.get(rid, NO_LINK_LABEL),
        })
    df = pd.DataFrame(rows)
    order = df['Estado'].str[0].map({'💡': 0, '❓': 1, '🚫': 2, '✅': 3}).fillna(4)
    return df.assign(_o=order).sort_values(['_o', 'Grupo Khan', 'Cuenta de Khan']).drop(columns='_o').reset_index(drop=True)


def roster_status(raw_df, roster, links):
    """Resumen para avisos: cuentas sin vincular, alumnos sin cuenta y cuentas combinadas."""
    accounts = khan_accounts(raw_df)
    link_map = build_link_map(raw_df, roster, links)
    # Las cuentas que el docente marcó a propósito como "sin vínculo" ya no se reportan como pendientes
    dismissed = {(r['Cuenta de Khan'], r['Grupo Khan']) for _, r in links.iterrows() if not r['ID alumno']}
    linked_ids = pd.Series(list(link_map.values()), dtype=str)
    counts = linked_ids.value_counts()
    return {
        'n_accounts': len(accounts),
        'n_linked': len(link_map),
        'unlinked': [k for k in zip(accounts['Cuenta de Khan'], accounts['Grupo Khan']) if k not in link_map and k not in dismissed],
        'without_account': roster[~roster['ID'].isin(set(link_map.values()))] if not roster.empty else roster,
        'combined': {rid: [k[0] for k, v in link_map.items() if v == rid] for rid in counts[counts > 1].index},
    }


def roster_template_bytes():
    sample = pd.DataFrame([
        {'Matrícula': '24123456', 'Nombre': 'ALBORES CLEMENTE PAULO CESAR', 'Grupo': '5°H'},
        {'Matrícula': '', 'Nombre': 'GONZÁLEZ MARTÍNEZ MARÍA FERNANDA', 'Grupo': '1°A'},
    ])
    return table_to_xlsx_bytes(sample, "Lista")


def access_cards_bytes(roster):
    cards = roster[roster['PIN'] != ''].copy()
    cards['Usuario'] = cards.apply(roster_login_id, axis=1)
    cards = cards[['Grupo', 'Nombre', 'Usuario', 'PIN']].sort_values(['Grupo', 'Nombre'])
    return table_to_xlsx_bytes(cards, "Fichas de acceso")


def _finish_save(results):
    """Muestra el peor resultado de una o varias operaciones de guardado tras recargar la página."""
    order = {'error': 0, 'warning': 1, 'success': 2}
    level, message, _ = sorted(results, key=lambda r: order.get(r[0], 3))[0]
    set_flash(level, message)
    st.rerun()


def render_roster_tab(folder_id, raw_df, roster, links, carpeta_nombre):
    """Pestaña 'Alumnos y cuentas' del panel docente."""
    pending = st.session_state.get('_pending_upload')
    if pending:
        st.download_button(f"📥 Descargar {pending[0]} para subirlo a tu carpeta", pending[1], file_name=pending[0],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary", key="dl_pending_upload")

    st.caption("La **lista oficial** es la base: une las cuentas de Khan de cada alumno (aunque tenga más de una) "
               "y le permite entrar al portal con su **matrícula y un PIN**, sin depender de sus datos de Khan.")

    status = roster_status(raw_df, roster, links)
    stats = [
        ("👥 Alumnos en la lista", f"{len(roster)}"),
        ("🔗 Cuentas de Khan vinculadas", f"{status['n_linked']} <small>de {status['n_accounts']}</small>"),
        ("❓ Cuentas sin vincular", f"{len(status['unlinked'])}"),
        ("🚫 Alumnos sin cuenta de Khan", f"{len(status['without_account'])}"),
    ]
    st.markdown(compact_html("<div class='mini-stats teacher-stats'>" + "".join(
        f"<div class='mini-stat'><div class='mini-label'>{lbl}</div><div class='mini-val'>{val}</div></div>" for lbl, val in stats
    ) + "</div>"), unsafe_allow_html=True)

    # --- Crear o actualizar la lista
    with st.expander("📋 Crear o actualizar la lista oficial", expanded=roster.empty):
        st.markdown("Sube tu lista con las columnas **Matrícula**, **Nombre** y **Grupo** (Excel o CSV). "
                    "Si un alumno aún no tiene matrícula, déjala vacía: el sistema le asigna un **código provisional**. "
                    "Puedes subir la lista de nuevo cuando quieras; se actualizan los datos sin perder PIN ni vínculos.")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📥 Plantilla de lista", roster_template_bytes(), file_name="plantilla_lista_alumnos.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch',
                               key="dl_roster_template")
        with c2:
            if st.button("✨ Crear lista a partir de los reportes de Khan", width='stretch', key="roster_from_khan",
                         help="Toma los nombres y grupos de los reportes. Después solo completas las matrículas."):
                acc = khan_accounts(raw_df)
                seed = pd.DataFrame({'Nombre': acc['Cuenta de Khan'], 'Grupo': acc['Grupo Khan']})
                seed['_t'] = seed['Nombre'].apply(name_tokens)
                seed = seed.drop_duplicates(['_t', 'Grupo']).drop(columns='_t')
                current = normalize_roster(read_teacher_table(folder_id, ROSTER_FILE))
                _finish_save([save_teacher_table(folder_id, ROSTER_FILE, merge_roster_upload(current, seed), "Lista")])
        up = st.file_uploader("Lista oficial (Excel o CSV)", type=["xlsx", "csv"], key="roster_upload")
        if up is not None and st.button(f"⬆️ Cargar '{up.name}'", type="primary", key="roster_upload_btn"):
            try:
                new = pd.read_csv(up, dtype=str) if up.name.lower().endswith('.csv') else pd.read_excel(up, dtype=str)
                merged = merge_roster_upload(normalize_roster(read_teacher_table(folder_id, ROSTER_FILE)), new)
                _finish_save([save_teacher_table(folder_id, ROSTER_FILE, merged, "Lista")])
            except Exception as e:
                st.error(f"No se pudo leer el archivo: {e}")

    if roster.empty:
        st.info("Aún no tienes lista oficial. Súbela o créala a partir de los reportes de Khan para empezar.")
        return

    # --- Vincular cuentas
    st.markdown("#### 🔗 Vincular cuentas de Khan con tu lista")
    st.caption("Las coincidencias exactas se vinculan solas. Revisa las **sugerencias** y asigna las cuentas **sin vincular**. "
               "Si un alumno tiene dos cuentas, vincula ambas a él: sus actividades se combinan con el mejor resultado.")
    table = build_link_table(raw_df, roster, links)
    if table.empty:
        st.caption("Aún no hay reportes de Khan para vincular.")
    else:
        show_all = st.toggle("Mostrar también las cuentas ya vinculadas", value=False, key="links_show_all")
        view = table if show_all else table[~table['Estado'].str.startswith('✅')]
        if view.empty:
            st.success("✅ Todas las cuentas de Khan están vinculadas.")
        else:
            options = [NO_LINK_LABEL] + sorted(roster.apply(roster_label, axis=1).tolist())
            edited = st.data_editor(
                view, hide_index=True, width='stretch', key="links_editor",
                disabled=['Cuenta de Khan', 'Grupo Khan', 'Actividades', 'Estado'],
                column_config={
                    'Alumno de la lista': st.column_config.SelectboxColumn(options=options, required=True, width="large"),
                    'Estado': st.column_config.TextColumn(width="medium"),
                },
            )
            if st.button("💾 Guardar vínculos", type="primary", key="save_links_btn"):
                label_to_id = {roster_label(r): r['ID'] for _, r in roster.iterrows()}
                new_links = normalize_links(read_teacher_table(folder_id, LINKS_FILE))
                for _, r in edited.iterrows():
                    key_mask = (new_links['Cuenta de Khan'] == r['Cuenta de Khan']) & (new_links['Grupo Khan'] == r['Grupo Khan'])
                    new_links = new_links[~key_mask]
                    new_links = pd.concat([new_links, pd.DataFrame([{
                        'Cuenta de Khan': r['Cuenta de Khan'], 'Grupo Khan': r['Grupo Khan'],
                        'ID alumno': label_to_id.get(r['Alumno de la lista'], ''),
                    }])], ignore_index=True)
                _finish_save([save_teacher_table(folder_id, LINKS_FILE, normalize_links(new_links), "Vinculos")])

    if status['combined']:
        names = roster.set_index('ID')['Nombre']
        items = "".join(f"<li><strong>{html.escape(names.get(rid, rid))}</strong>: {html.escape(', '.join(accs))}</li>"
                        for rid, accs in status['combined'].items())
        st.markdown(compact_html(f"<div class='student-card' style='border-left-color:#2563eb;'><div class='sc-label'>🔀 Cuentas combinadas (alumnos con más de una cuenta de Khan)</div><ul>{items}</ul></div>"),
                    unsafe_allow_html=True)

    if not status['without_account'].empty:
        with st.expander(f"🚫 {len(status['without_account'])} alumno(s) de tu lista sin cuenta de Khan vinculada"):
            st.caption("No aparecen en los reportes de Khan o su cuenta no está vinculada. Si no se han unido a la clase de Khan, "
                       "no tendrán calificación: conviene buscarlos.")
            st.dataframe(status['without_account'][['Grupo', 'Nombre', 'Matrícula', 'Código provisional']]
                         .sort_values(['Grupo', 'Nombre']), hide_index=True, width='stretch')

    # --- Acceso de los alumnos con PIN
    st.markdown("#### 🔑 Acceso de los alumnos con matrícula y PIN")
    n_without_pin = int((roster['PIN'] == '').sum())
    st.caption("Los alumnos entran en **Acceso Estudiantes** con su matrícula (o código provisional) y su PIN de 6 dígitos. "
               "No necesitan su usuario ni contraseña de Khan.")
    p1, p2 = st.columns(2)
    with p1:
        if st.button(f"🔑 Generar PIN a {n_without_pin} alumno(s) que no tienen" if n_without_pin else "🔑 Todos tienen PIN",
                     disabled=n_without_pin == 0, width='stretch', key="gen_pins_btn"):
            updated, _ = generate_missing_pins(normalize_roster(read_teacher_table(folder_id, ROSTER_FILE)))
            _finish_save([save_teacher_table(folder_id, ROSTER_FILE, updated, "Lista")])
    with p2:
        st.download_button("🖨️ Descargar fichas de acceso (Excel)", access_cards_bytes(roster),
                           file_name=f"fichas_acceso_{now_local().strftime('%Y%m%d')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           disabled=(roster['PIN'] == '').all(), width='stretch', key="dl_access_cards")
    st.caption(f"Puedes corregir matrículas, nombres o PIN directamente en **{ROSTER_FILE}** dentro de tu carpeta "
               f"`{carpeta_nombre}` (se abre con Google Sheets); después presiona **Sincronizar**.")


# ==============================================================================
# FASE 5: EVIDENCIAS (SELLOS), EXAMEN, PRODUCTO, ASISTENCIA Y CALIFICACIÓN FINAL
# ==============================================================================
EVID_FILE = "evidencias.xlsx"
EXTRA_FILE = "calificaciones_parcial.xlsx"
ATT_FILE = "asistencia.xlsx"
EVID_COLS = ['ID alumno', 'Grupo', 'Bloque', 'Fecha bloque', 'Nivel', 'Actualizado']
EXTRA_COLS = ['ID alumno', 'Parcial', 'Componente', 'Calificación', 'Actualizado']
ATT_COLS = ['ID alumno', 'Grupo', 'Fecha', 'Estado', 'Nota']
SEGUIMIENTO_FILE = "seguimiento.xlsx"
SEGUIMIENTO_COLS = ['Grupo', 'Alumno', 'Fecha', 'Nota']

# Rúbrica de evidencias: nivel -> porcentaje del componente
EVID_LEVELS = [
    ("0 · No presentó", 0, "Sin evidencia del procedimiento."),
    ("1 · En proceso", 50, "Procedimiento incompleto o con errores de fondo. Puede volver a presentarlo."),
    ("2 · Suficiente", 80, "Procedimiento correcto, pero le cuesta explicarlo."),
    ("3 · Dominio", 100, "Procedimiento correcto y lo explica, o resuelve una variante en el momento."),
]
EVID_PCT = {lbl: pct for lbl, pct, _ in EVID_LEVELS}


def default_rubrica():
    return [{'nivel': lbl, 'valor': pct, 'descripcion': desc} for lbl, pct, desc in EVID_LEVELS]


def evid_levels(cfg):
    """
    Rúbrica de sellos del docente: los nombres de los niveles son fijos (así se guardan los sellos),
    pero cada docente puede cambiar la descripción y el valor (%) de cada nivel.
    """
    custom = {r.get('nivel'): r for r in ((cfg or {}).get('rubrica_evidencias') or []) if isinstance(r, dict)}
    levels = []
    for lbl, pct, desc in EVID_LEVELS:
        c = custom.get(lbl, {})
        try:
            value = float(c.get('valor', pct))
        except (TypeError, ValueError):
            value = float(pct)
        levels.append((lbl, value, str(c.get('descripcion') or desc).strip()))
    return levels


def evid_pct_map(cfg):
    return {lbl: pct for lbl, pct, _ in evid_levels(cfg)}


def evid_color(pct, cfg):
    top = max(p for _, p, _ in evid_levels(cfg)) or 100
    if pct is None or pd.isna(pct) or pct <= 0:
        return '#dc2626'
    if pct >= top:
        return '#16a34a'
    return '#d97706' if pct < 0.6 * top else '#2563eb'


def rubric_markdown(cfg, suffix=""):
    return "\n".join(f"- **{lbl}** ({pct:g}%{suffix}): {desc}" for lbl, pct, desc in evid_levels(cfg))
ATT_STATES = ["✅ Asistió", "⏰ Retardo", "📝 Justificada", "❌ Falta"]
ATT_NOTE_STATES = ("⏰ Retardo", "📝 Justificada")
PARCIALES = ['Parcial 1', 'Parcial 2', 'Parcial 3']


def _norm_table(df, cols):
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = ''
        df[c] = df[c].fillna('').astype(str).str.strip().replace({'nan': ''})
    return df[cols]


def load_eval_tables(folder_id):
    return (_norm_table(load_teacher_table(folder_id, EVID_FILE), EVID_COLS),
            _norm_table(load_teacher_table(folder_id, EXTRA_FILE), EXTRA_COLS),
            _norm_table(load_teacher_table(folder_id, ATT_FILE), ATT_COLS))


def fresh_table(folder_id, filename, cols):
    """Lectura directa (sin caché) justo antes de guardar."""
    return _norm_table(read_teacher_table(folder_id, filename), cols)


def upsert_rows(table, new_rows, key_cols):
    """Reemplaza las filas con las mismas llaves y agrega las nuevas."""
    if new_rows.empty:
        return table
    keys_new = set(map(tuple, new_rows[key_cols].astype(str).values))
    keep = ~table[key_cols].astype(str).apply(tuple, axis=1).isin(keys_new) if not table.empty else pd.Series([], dtype=bool)
    return pd.concat([table[keep] if not table.empty else table, new_rows], ignore_index=True)


def parcial_of(d, criteria_config):
    """Parcial al que pertenece una fecha (date, Timestamp o 'YYYY-MM-DD')."""
    try:
        d = pd.to_datetime(d).date()
    except Exception:
        return None
    for p_name, rng in parse_parciales_dates((criteria_config or {}).get('parciales', {})).items():
        if rng['start'] <= d <= rng['end']:
            return p_name
    return None


def current_parcial(criteria_config):
    return parcial_of(now_local().date(), criteria_config) or 'Parcial 1'


def compute_components(roster, evid, extra, att, criteria_config, parcial):
    """Una fila por alumno de la lista con el valor de cada componente en el parcial (NaN = sin registro)."""
    cfg = criteria_config or {}
    scale = float(cfg.get('escala_maxima', 10))
    out = roster[['ID', 'Nombre', 'Grupo']].copy().set_index('ID')

    ev = evid.copy()
    if not ev.empty:
        ev['Parcial'] = ev['Fecha bloque'].apply(lambda d: parcial_of(d, cfg))
        ev = ev[ev['Parcial'] == parcial]
        ev['pct'] = ev['Nivel'].map(evid_pct_map(cfg))
        g = ev.dropna(subset=['pct']).groupby('ID alumno')['pct']
        out['Evidencias %'] = g.mean()
        out['Bloques con evidencia'] = g.size()
    else:
        out['Evidencias %'] = float('nan')
        out['Bloques con evidencia'] = 0
    out['Bloques con evidencia'] = out['Bloques con evidencia'].fillna(0).astype(int)

    for comp, label in [('examen', 'Examen'), ('producto', 'Producto')]:
        rows = extra[(extra['Parcial'] == parcial) & (extra['Componente'] == comp)] if not extra.empty else extra
        vals = pd.to_numeric(rows['Calificación'], errors='coerce') if not rows.empty else pd.Series(dtype=float)
        out[label] = pd.Series(vals.values, index=rows['ID alumno'].values).groupby(level=0).last() if not rows.empty else float('nan')
        out[label] = out[label].clip(0, scale) if label in out else out[label]

    a = att.copy()
    if not a.empty:
        a['Parcial'] = a['Fecha'].apply(lambda d: parcial_of(d, cfg))
        a = a[a['Parcial'] == parcial]
    if not a.empty:
        g = a.groupby('ID alumno')['Estado']
        out['Sesiones'] = g.size()
        out['Faltas'] = g.apply(lambda s: int((s == "❌ Falta").sum()))
    else:
        out['Sesiones'] = 0
        out['Faltas'] = 0
    out['Sesiones'] = out['Sesiones'].fillna(0).astype(int)
    out['Faltas'] = out['Faltas'].fillna(0).astype(int)
    out['Asistencia %'] = ((out['Sesiones'] - out['Faltas']) / out['Sesiones'].where(out['Sesiones'] > 0) * 100)
    return out.reset_index()


def compute_final_grades(components, khan_by_name, criteria_config, parcial=None):
    """
    Calificación del parcial = promedio ponderado de los componentes con registro.
    Khan se lleva a escala completa (sin el factor de ponderación) y se pondera con su peso.
    Con criterios por grupo, cada alumno usa los pesos de su grupo (y del parcial, si se definieron).
    """
    base_cfg = criteria_config or {}
    scale = float(base_cfg.get('escala_maxima', 10))
    rows = []
    for _, r in components.iterrows():
        cfg = group_config(base_cfg, r['Grupo'], parcial)
        peso_khan = khan_weight(cfg)
        weights = {**DEFAULT_COMPONENTES, **(cfg.get('componentes') or {})}
        khan_full = khan_by_name.get(r['Nombre'])
        values = {
            'khan': (peso_khan, khan_full),
            'evidencias': (weights['evidencias'], r['Evidencias %'] / 100 * scale if pd.notna(r['Evidencias %']) else None),
            'examen': (weights['examen'], r['Examen'] if pd.notna(r['Examen']) else None),
            'producto': (weights['producto'], r['Producto'] if pd.notna(r['Producto']) else None),
            'asistencia': (weights['asistencia'], r['Asistencia %'] / 100 * scale if pd.notna(r['Asistencia %']) else None),
        }
        used = [(w, v) for w, v in values.values() if w > 0 and v is not None]
        pending = [k for k, (w, v) in values.items() if w > 0 and v is None]
        final = sum(w * v for w, v in used) / sum(w for w, _ in used) if used else None
        rows.append({
            'ID': r['ID'], 'Grupo': r['Grupo'], 'Nombre': r['Nombre'],
            'Khan': round(khan_full, 1) if khan_full is not None else None,
            'Evidencias': round(values['evidencias'][1], 1) if values['evidencias'][1] is not None else None,
            'Examen': r['Examen'] if pd.notna(r['Examen']) else None,
            'Producto': r['Producto'] if pd.notna(r['Producto']) else None,
            'Asistencia %': round(r['Asistencia %'], 0) if pd.notna(r['Asistencia %']) else None,
            'Final': round(final, 1) if final is not None else None,
            'Pendiente': ", ".join(dict(COMPONENTES).get(k, 'Khan').split(' ', 1)[-1] for k in pending),
        })
    return pd.DataFrame(rows)


def attendance_flag(pct, minimum):
    if pct is None or pd.isna(pct):
        return ""
    if pct < minimum:
        return "🔴 Debajo del mínimo"
    if pct < minimum + 5:
        return "🟠 Cerca del mínimo"
    return "🟢 Bien"


def _khan_avg_by_name(tasks, criteria_config, parcial):
    """Promedio de Khan por alumno en el parcial, en escala completa (sin el factor de ponderación)."""
    t = tasks[tasks['Parcial'] == parcial] if 'Parcial' in tasks.columns else tasks
    if t.empty:
        return {}
    blocks = compute_student_block_grades(t, {**(criteria_config or {}), 'peso_khan': 100, 'criterios_por_grupo': False})
    return blocks.dropna(subset=['block_grade']).groupby('Nombre del estudiante')['block_grade'].mean().to_dict()


def _eval_selectors(roster, cfg, key_prefix, with_parcial=True):
    """Selector de grupo (y parcial) compartido por las secciones de evaluación."""
    groups = sorted(g for g in roster['Grupo'].unique() if g) or ['']
    if with_parcial:
        s1, s2 = st.columns(2)
        with s1:
            grupo = st.selectbox("Grupo:", groups, key=f"{key_prefix}_group")
        with s2:
            cur = current_parcial(cfg)
            parcial = st.selectbox("Parcial:", PARCIALES, index=PARCIALES.index(cur), key=f"{key_prefix}_parcial")
    else:
        grupo = st.selectbox("Grupo:", groups, key=f"{key_prefix}_group")
        parcial = None
    return grupo, parcial, roster[roster['Grupo'] == grupo].sort_values('Nombre')


def _show_pending_upload(key):
    pending = st.session_state.get('_pending_upload')
    if pending:
        st.download_button(f"📥 Descargar {pending[0]} para subirlo a tu carpeta", pending[1], file_name=pending[0],
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", key=key)


def _needs_roster(roster):
    if roster.empty:
        st.info("Para registrar asistencia, sellos, examen o producto necesitas tu **lista oficial**. "
                "Créala en **⚙️ Ajustes → 👥 Alumnos y cuentas**.")
        return True
    return False


_ATT_SHORT = {"✅ Asistió": "✅ Asistió", "⏰ Retardo": "⏰ Retardo", "📝 Justificada": "📝 Justif.", "❌ Falta": "❌ Falta"}
_EVID_SHORT = {"0 · No presentó": "0 No presentó", "1 · En proceso": "1 En proceso", "2 · Suficiente": "2 Suficiente", "3 · Dominio": "3 Dominio"}


def render_attendance_section(folder_id, roster, criteria_config):
    """Pase de lista pensado para el celular: un renglón por alumno con botones grandes."""
    cfg = criteria_config or {}
    minimum = float(cfg.get('asistencia_minima', 80))
    _show_pending_upload("dl_pending_att")
    if _needs_roster(roster):
        return
    evid, extra, att = load_eval_tables(folder_id)
    grupo, _, students = _eval_selectors(roster, cfg, "att", with_parcial=False)
    fecha = st.date_input("Fecha de la clase:", value=now_local().date(), key="att_date")
    f_iso = fecha.isoformat()
    day = att[(att['Grupo'] == grupo) & (att['Fecha'] == f_iso)].set_index('ID alumno') if not att.empty else pd.DataFrame(columns=['Estado', 'Nota'])
    current = day['Estado']
    current_notes = day['Nota']
    st.caption("✅ Ya hay pase de lista para esta fecha; puedes corregirlo." if not current.empty else
               "Todos empiezan como **Asistió**: toca solo a quien faltó o llegó tarde. El retardo y la falta justificada no cuentan como falta.")

    keys = {sid: f"att_{grupo}_{f_iso}_{sid}" for sid in students['ID']}
    if st.button("↺ Marcar a todos como Asistió", key=f"att_reset_{grupo}_{f_iso}"):
        for k in keys.values():
            st.session_state[k] = ATT_STATES[0]
    states, notes = {}, {}
    for _, s in students.iterrows():
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        with c1:
            st.markdown(f"**{html.escape(s['Nombre'])}**")
        with c2:
            default = {} if keys[s['ID']] in st.session_state else {'default': current.get(s['ID'], ATT_STATES[0])}
            val = st.pills("Estado", ATT_STATES, key=keys[s['ID']], required=True,
                           format_func=lambda o: _ATT_SHORT[o], label_visibility="collapsed", wrap=True, **default)
            states[s['ID']] = val or ATT_STATES[0]
        # Nota opcional solo para retardos y justificantes (no estorba al resto del pase de lista)
        if states[s['ID']] in ATT_NOTE_STATES:
            notes[s['ID']] = st.text_input(
                "Nota", value=str(current_notes.get(s['ID'], '') or ''), key=f"attnote_{grupo}_{f_iso}_{s['ID']}",
                label_visibility="collapsed", max_chars=150,
                placeholder="📝 Nota opcional: ej. trajo receta médica; avisó su mamá por WhatsApp"
            ).strip()
    n_f = sum(v == "❌ Falta" for v in states.values())
    n_r = sum(v == "⏰ Retardo" for v in states.values())
    st.markdown(f"**{len(states) - n_f} presentes** · {n_f} falta(s) · {n_r} retardo(s)")
    if st.button("💾 Guardar asistencia", type="primary", width='stretch', key="save_att_btn"):
        new = pd.DataFrame({'ID alumno': list(states), 'Grupo': grupo, 'Fecha': f_iso, 'Estado': list(states.values()),
                            'Nota': [notes.get(i, '') if states[i] in ATT_NOTE_STATES else '' for i in states]})
        base = fresh_table(folder_id, ATT_FILE, ATT_COLS)
        _finish_save([save_teacher_table(folder_id, ATT_FILE, upsert_rows(base, new, ['ID alumno', 'Fecha']), "Asistencia")])

    parcial = parcial_of(fecha, cfg) or current_parcial(cfg)
    comps = compute_components(students, evid, extra, att, cfg, parcial)
    summ = comps[comps['Sesiones'] > 0][['Nombre', 'Sesiones', 'Faltas', 'Asistencia %']].copy()
    if not summ.empty:
        summ['Asistencia %'] = summ['Asistencia %'].round(0)
        summ['Estado'] = summ['Asistencia %'].apply(lambda p: attendance_flag(p, minimum))
        n_low = int((summ['Asistencia %'] < minimum).sum())
        with st.expander(f"📊 Resumen de asistencia · {parcial} (mínimo {minimum:g}%)" + (f" · 🔴 {n_low} debajo del mínimo" if n_low else ""),
                         expanded=bool(n_low)):
            st.dataframe(summ.sort_values('Asistencia %'), hide_index=True, width='stretch',
                         column_config={'Asistencia %': st.column_config.ProgressColumn(format="%d%%", min_value=0, max_value=100)})
    # Notas de retardos y justificantes del parcial, para revisarlas al cerrar el parcial
    if not att.empty:
        ids = set(students['ID'])
        noted = att[att['ID alumno'].isin(ids) & (att['Nota'] != '')].copy()
        noted = noted[noted['Fecha'].apply(lambda d: parcial_of(d, cfg)) == parcial]
        if not noted.empty:
            names = students.set_index('ID')['Nombre']
            noted['Alumno'] = noted['ID alumno'].map(names)
            noted = noted.sort_values(['Alumno', 'Fecha'])[['Alumno', 'Fecha', 'Estado', 'Nota']]
            with st.expander(f"📝 Notas de retardos y justificantes · {parcial} ({len(noted)})"):
                st.dataframe(noted, hide_index=True, width='stretch')


def render_evidence_section(folder_id, roster, tasks, criteria_config):
    """Sellos de evidencia por bloque, también con botones grandes para el celular."""
    cfg = criteria_config or {}
    _show_pending_upload("dl_pending_evid")
    if _needs_roster(roster):
        return
    evid, _, _ = load_eval_tables(folder_id)
    grupo, parcial, students = _eval_selectors(roster, cfg, "evid")
    with st.expander("📏 Rúbrica (tus alumnos también la ven en su portal)"):
        st.markdown(rubric_markdown(cfg) +
                    "\n\n✏️ Puedes cambiar descripciones y valores en **⚙️ Ajustes → Criterios y componentes**."
                    "\n\n💡 Para distinguir a quien entendió de quien copió, pídele que resuelva una pequeña variante del ejercicio.")
    g_tasks = tasks[tasks['Grupo'] == grupo] if 'Grupo' in tasks.columns else tasks
    if 'Parcial' in g_tasks.columns:
        g_tasks = g_tasks[g_tasks['Parcial'] == parcial]
    blocks = g_tasks.dropna(subset=['dt_entrega']).drop_duplicates('Fecha de entrega').sort_values('dt_entrega')
    if blocks.empty:
        st.info(f"No hay bloques de Khan Academy del grupo {grupo} en {parcial}.")
        return
    labels = {b: f"{format_short_date(d, with_time=False)} · {b}" for b, d in zip(blocks['Fecha de entrega'], blocks['dt_entrega'])}
    bloque = st.selectbox("Bloque de tareas:", blocks['Fecha de entrega'].tolist(), format_func=lambda b: labels[b], key="eval_block")
    fecha_bloque = blocks.loc[blocks['Fecha de entrega'] == bloque, 'dt_entrega'].iloc[0].date().isoformat()
    current = evid[(evid['Grupo'] == grupo) & (evid['Bloque'] == bloque)].set_index('ID alumno')['Nivel'] if not evid.empty else pd.Series(dtype=str)
    st.caption("✅ Este bloque ya tiene sellos; actualízalos si alguien vuelve a presentar." if not current.empty else
               "Este bloque aún no tiene sellos. Al guardar, quien quede en **0 No presentó** cuenta como 0% en este bloque.")
    levels = [l for l, _, _ in EVID_LEVELS]
    values = {}
    for _, s in students.iterrows():
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        with c1:
            st.markdown(f"**{html.escape(s['Nombre'])}**")
        with c2:
            k = f"evid_{grupo}_{bloque}_{s['ID']}"
            default = {} if k in st.session_state else {'default': current.get(s['ID'], levels[0])}
            val = st.pills("Nivel", levels, key=k, required=True,
                           format_func=lambda o: _EVID_SHORT[o], label_visibility="collapsed", wrap=True, **default)
            values[s['ID']] = val or levels[0]
    if st.button("💾 Guardar sellos del bloque", type="primary", width='stretch', key="save_evid_btn"):
        new = pd.DataFrame({'ID alumno': list(values), 'Grupo': grupo, 'Bloque': bloque, 'Fecha bloque': fecha_bloque,
                            'Nivel': list(values.values()), 'Actualizado': now_local().strftime('%Y-%m-%d %H:%M')})
        base = fresh_table(folder_id, EVID_FILE, EVID_COLS)
        _finish_save([save_teacher_table(folder_id, EVID_FILE, upsert_rows(base, new, ['ID alumno', 'Bloque']), "Evidencias")])


def render_extra_section(folder_id, roster, criteria_config):
    """Calificaciones de examen y producto del parcial."""
    cfg = criteria_config or {}
    scale = int(cfg.get('escala_maxima', 10))
    _show_pending_upload("dl_pending_extra")
    if _needs_roster(roster):
        return
    _, extra, _ = load_eval_tables(folder_id)
    grupo, parcial, students = _eval_selectors(roster, cfg, "extra")
    weights = {**DEFAULT_COMPONENTES, **(group_config(cfg, grupo, parcial).get('componentes') or {})}
    off = [l for k, l in [('examen', '📝 Examen'), ('producto', '📦 Producto del parcial')] if not weights.get(k)]
    if off:
        st.caption("⚠️ " + " y ".join(off) + " tiene(n) peso 0% en ⚙️ Ajustes: puedes registrar, pero no cuenta(n) en la calificación final.")
    cur_vals = {}
    for k in ['examen', 'producto']:
        rows = extra[(extra['Parcial'] == parcial) & (extra['Componente'] == k)] if not extra.empty else extra
        cur_vals[k] = pd.to_numeric(rows.set_index('ID alumno')['Calificación'], errors='coerce') if not rows.empty else pd.Series(dtype=float)
    edit = pd.DataFrame({'ID': students['ID'].values, 'Alumno': students['Nombre'].values,
                         'Examen': [cur_vals['examen'].get(i) for i in students['ID']],
                         'Producto': [cur_vals['producto'].get(i) for i in students['ID']]})
    edited = st.data_editor(edit, hide_index=True, width='stretch', disabled=['ID', 'Alumno'], key=f"extra_editor_{grupo}_{parcial}",
                            column_config={'ID': None,
                                           'Examen': st.column_config.NumberColumn(f"Examen (0-{scale})", min_value=0, max_value=scale, step=0.1),
                                           'Producto': st.column_config.NumberColumn(f"Producto (0-{scale})", min_value=0, max_value=scale, step=0.1)})
    st.caption("Deja en blanco a quien aún no tenga calificación; aparecerá como pendiente.")
    if st.button("💾 Guardar calificaciones", type="primary", width='stretch', key="save_extra_btn"):
        stamp = now_local().strftime('%Y-%m-%d %H:%M')
        new_rows = [{'ID alumno': r['ID'], 'Parcial': parcial, 'Componente': k, 'Calificación': f"{float(r[col]):g}", 'Actualizado': stamp}
                    for _, r in edited.iterrows() for k, col in [('examen', 'Examen'), ('producto', 'Producto')] if pd.notna(r[col])]
        table = fresh_table(folder_id, EXTRA_FILE, EXTRA_COLS)
        ids = set(students['ID'])
        if not table.empty:
            table = table[~(table['ID alumno'].isin(ids) & (table['Parcial'] == parcial))]
        table = pd.concat([table, pd.DataFrame(new_rows, columns=EXTRA_COLS)], ignore_index=True)
        _finish_save([save_teacher_table(folder_id, EXTRA_FILE, table, "Calificaciones")])


def render_final_section(folder_id, roster, tasks, criteria_config):
    """Calificación final del parcial ponderada por componentes."""
    base_cfg = criteria_config or {}
    scale = int(base_cfg.get('escala_maxima', 10))
    if _needs_roster(roster):
        return
    evid, extra, att = load_eval_tables(folder_id)
    grupo, parcial, students = _eval_selectors(roster, base_cfg, "final")
    cfg = group_config(base_cfg, grupo, parcial)
    weights = {**DEFAULT_COMPONENTES, **(cfg.get('componentes') or {})}
    total_w = khan_weight(cfg) + sum(float(v) for v in weights.values())
    parts = [f"Khan {khan_weight(cfg):g}%"] + [f"{l.split(' ', 1)[1]} {float(weights[k]):g}%" for k, l in COMPONENTES if float(weights[k])]
    origin = ""
    if base_cfg.get('criterios_por_grupo'):
        over = group_overrides(base_cfg, grupo, parcial)
        origin = (f" (acordada con {grupo} para {parcial})" if over and over['del_parcial'] else
                  f" (acordada con {grupo})" if over else " (criterios generales)")
    st.caption("Ponderación" + origin + ": " + " + ".join(parts) + ". Si a un alumno le falta algún componente, su calificación se calcula "
               "con lo registrado y el faltante aparece en **Pendiente**.")
    if abs(total_w - 100) > 0.01:
        st.warning(f"⚠️ Los pesos suman {total_w:g}%. Ajústalos en ⚙️ Ajustes → Criterios y componentes.")
    comps = compute_components(students, evid, extra, att, cfg, parcial)
    final = compute_final_grades(comps, _khan_avg_by_name(tasks, cfg, parcial), base_cfg, parcial)
    if final.empty:
        st.info("Sin alumnos en este grupo.")
        return
    final['Estatus'] = final['Final'].apply(lambda v: classify_student(v, cfg.get('thresholds', {}), scale) if v is not None else "Sin datos")
    show = final.drop(columns=['ID'])
    for col in ['Khan', 'Evidencias', 'Examen', 'Producto', 'Asistencia %', 'Final']:
        show[col] = pd.to_numeric(show[col], errors='coerce')
    # Vista: celdas sin registro como "—" (Streamlit mostraría "None")
    view = show.copy()
    for col in ['Khan', 'Evidencias', 'Examen', 'Producto', 'Final']:
        view[col] = view[col].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
    view['Asistencia %'] = view['Asistencia %'].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—")
    st.dataframe(view, hide_index=True, width='stretch', height=min(560, 40 + len(view) * 36))
    st.download_button("📥 Descargar calificaciones del parcial (Excel)", table_to_xlsx_bytes(show, parcial),
                       file_name=f"Calificaciones_{parcial.replace(' ', '')}_{grupo.replace('°', '')}_{now_local().strftime('%Y%m%d')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_final_grades")


def attendance_by_name(roster, att, criteria_config, parcial=None):
    """{nombre: % de asistencia} en el parcial indicado (o en todo el semestre)."""
    if roster.empty or att.empty:
        return {}
    a = att.copy()
    if parcial:
        a = a[a['Fecha'].apply(lambda d: parcial_of(d, criteria_config)) == parcial]
    if a.empty:
        return {}
    g = a.groupby('ID alumno')['Estado']
    pct = (g.size() - g.apply(lambda s: (s == "❌ Falta").sum())) / g.size() * 100
    names = roster.set_index('ID')['Nombre']
    return {names[i]: float(v) for i, v in pct.items() if i in names.index}


EVID_TIPS = ("Lleva tu libreta con el procedimiento completo y ordenado. Prepárate para explicar cada paso "
             "o resolver un ejercicio parecido frente a tu docente.")


def evidence_opportunities(ctx, student_id, criteria_config, parcial):
    """
    Sellos del alumno que todavía pueden mejorar y cuánto subiría su calificación del parcial
    si vuelve a presentar y obtiene Dominio (por bloque y en total).
    """
    cfg = criteria_config or {}
    roster, evid, extra, att, tasks = ctx['roster'], ctx['evid'], ctx['extra'], ctx['att'], ctx['tasks']
    me = roster[roster['ID'] == student_id]
    if not me.empty:
        cfg = group_config(cfg, me.iloc[0]['Grupo'], parcial)
    if me.empty or evid is None or evid.empty or float((cfg.get('componentes') or {}).get('evidencias', 0)) <= 0:
        return None
    khan = _khan_avg_by_name(tasks, cfg, parcial)

    def final_with(ev):
        return compute_final_grades(compute_components(me, ev, extra, att, cfg, parcial), khan, cfg, parcial).iloc[0]['Final']

    mine = evid[(evid['ID alumno'] == student_id) & (evid['Fecha bloque'].apply(lambda d: parcial_of(d, cfg)) == parcial)]
    pct_map = evid_pct_map(cfg)
    top_pct = max(pct_map.values())
    top = max(pct_map, key=pct_map.get)
    improvable = mine[mine['Nivel'].map(pct_map).fillna(0) < top_pct]
    if improvable.empty:
        return {'current': final_with(evid), 'best': None, 'blocks': []}
    blocks = []
    for idx, r in improvable.sort_values('Fecha bloque').iterrows():
        sim = evid.copy()
        sim.loc[idx, 'Nivel'] = top
        blocks.append({'fecha': r['Fecha bloque'], 'nivel': r['Nivel'], 'final': final_with(sim)})
    sim_all = evid.copy()
    sim_all.loc[improvable.index, 'Nivel'] = top
    return {'current': final_with(evid), 'best': final_with(sim_all), 'blocks': blocks}


def render_evidence_motivation(ctx, student_id, criteria_config, parcial, compact=False):
    """Invita a volver a presentar los sellos que no llegaron a Dominio, con su efecto en la calificación."""
    opp = evidence_opportunities(ctx, student_id, criteria_config, parcial)
    if not opp or not opp['blocks']:
        return False
    cur, best = opp['current'], opp['best']
    n = len(opp['blocks'])
    gain = f" tu calificación de {parcial} puede subir de **{cur:.1f}** a **{best:.1f}**" if (cur is not None and best is not None and round(best, 1) > round(cur, 1)) else " mejoras tu calificación"
    st.info(f"📓 **{'Tienes ' + str(n) + ' sello' + ('s' if n != 1 else '') + ' que puedes mejorar.'}** "
            f"Acércate con tu docente para volver a presentar tu procedimiento: si obtienes **Dominio**,{gain}.")
    if compact:
        return True
    cards = []
    for b in opp['blocks']:
        color = evid_color(evid_pct_map(criteria_config).get(b['nivel'], 0), criteria_config)
        right = (f"Con Dominio<br><strong>{b['final']:.1f}</strong>" if b['final'] is not None else "")
        cards.append(_task_card_html(f"Bloque {format_short_date(pd.to_datetime(b['fecha']), with_time=False)}",
                                     f"Ahora: {html.escape(b['nivel'])}", right, color))
    st.markdown(compact_html("".join(cards)), unsafe_allow_html=True)
    st.caption("💡 " + EVID_TIPS)
    return True


def render_student_evaluation(ctx, student_id, criteria_config, key_prefix, default_parcial=None):
    """Pestaña '🧾 Mi evaluación' del alumno: componentes, sellos y asistencia."""
    cfg = criteria_config or {}
    scale = int(cfg.get('escala_maxima', 10))
    minimum = float(cfg.get('asistencia_minima', 80))
    weights = {**DEFAULT_COMPONENTES, **(cfg.get('componentes') or {})}
    roster, evid, extra, att, tasks = ctx['roster'], ctx['evid'], ctx['extra'], ctx['att'], ctx['tasks']
    me = roster[roster['ID'] == student_id]
    if me.empty:
        st.info("Tu docente aún no te ha registrado en su lista oficial.")
        return
    cur = default_parcial if default_parcial in PARCIALES else current_parcial(cfg)
    parcial = st.selectbox("Parcial:", PARCIALES, index=PARCIALES.index(cur), key=f"{key_prefix}_my_eval_parcial_{cur}")
    cfg = group_config(cfg, me.iloc[0]['Grupo'], parcial)
    weights = {**DEFAULT_COMPONENTES, **(cfg.get('componentes') or {})}
    comps = compute_components(me, evid, extra, att, cfg, parcial)
    final = compute_final_grades(comps, _khan_avg_by_name(tasks, cfg, parcial), cfg, parcial).iloc[0]

    peso_khan = khan_weight(cfg)
    items = [("🎓 Khan Academy", peso_khan, final['Khan'])]
    for k, label in COMPONENTES:
        val = {'evidencias': final['Evidencias'], 'examen': final['Examen'], 'producto': final['Producto'],
               'asistencia': (final['Asistencia %'] / 100 * scale) if final['Asistencia %'] is not None else None}[k]
        if float(weights.get(k, 0)) > 0:
            items.append((label, float(weights[k]), val))
    cards = "".join(
        f"<div class='mini-stat'><div class='mini-label'>{html.escape(lbl)} · {w:g}%</div>"
        f"<div class='mini-val'>{(f'{v:.1f}' if v is not None and not pd.isna(v) else '—')}<small> / {scale}</small></div></div>"
        for lbl, w, v in items if w > 0
    )
    final_txt = f"{final['Final']:.1f}" if final['Final'] is not None else "—"
    st.markdown(compact_html(f"""
    <div class="hero-card" style="border-left-color:#2563eb;">
        <div class="hero-label">Calificación estimada de {parcial}</div>
        <div class="hero-grade">{final_txt}<span> / {scale}</span></div>
        <div class="hero-msg">{('Pendiente por registrar: ' + html.escape(final['Pendiente']) + '.') if final['Pendiente'] else 'Todos los componentes están registrados.'}</div>
    </div>
    <div class="mini-stats teacher-stats">{cards}</div>"""), unsafe_allow_html=True)

    # Sellos por bloque
    with st.expander("📏 ¿Cómo se evalúan los sellos de evidencia?"):
        st.markdown("Esta es la rúbrica de tu docente:\n\n" + rubric_markdown(cfg, " del sello") + f"\n\n💡 {EVID_TIPS}")
    if float(weights.get('evidencias', 0)) > 0:
        render_evidence_motivation(ctx, student_id, cfg, parcial)
    my_ev = evid[evid['ID alumno'] == student_id].copy() if not evid.empty else evid
    if not my_ev.empty:
        my_ev = my_ev[my_ev['Fecha bloque'].apply(lambda d: parcial_of(d, cfg)) == parcial].sort_values('Fecha bloque')
    st.markdown("#### 📓 Mis sellos de evidencia")
    if my_ev.empty:
        if float(weights.get('evidencias', 0)) > 0:
            st.info(f"Tu docente evalúa las evidencias de tu libreta (**{float(weights['evidencias']):g}%** de tu calificación). "
                    f"Aún no tienes sellos en este parcial: {EVID_TIPS}")
        else:
            st.caption("Aún no tienes sellos registrados en este parcial.")
    else:
        desc = {lbl: d for lbl, _, d in evid_levels(cfg)}
        pct_map = evid_pct_map(cfg)
        cards = []
        for _, r in my_ev.iterrows():
            lvl = r['Nivel']
            color = evid_color(pct_map.get(lvl), cfg)
            tip = " Preséntalo para obtener tu sello." if not pct_map.get(lvl) else ""
            cards.append(_task_card_html(f"Bloque {format_short_date(pd.to_datetime(r['Fecha bloque']), with_time=False)}",
                                         html.escape(desc.get(lvl, '') + tip), f"<strong>{html.escape(lvl)}</strong>", color))
        st.markdown(compact_html("".join(cards)), unsafe_allow_html=True)

    # Asistencia
    st.markdown("#### 🙋 Mi asistencia")
    r = comps.iloc[0]
    if r['Sesiones'] == 0:
        st.caption("Aún no hay pase de lista registrado en este parcial.")
    else:
        pct = r['Asistencia %']
        msg = f"{pct:.0f}% de asistencia ({r['Sesiones'] - r['Faltas']} de {r['Sesiones']} clases). Mínimo requerido: {minimum:g}%."
        if pct < minimum:
            st.error("🔴 " + msg + " Habla con tu docente o tu tutor(a) para ver cómo recuperarte.")
        elif pct < minimum + 5:
            st.warning("🟠 " + msg + " Estás cerca del mínimo: cuida tus próximas asistencias.")
        else:
            st.success("🟢 " + msg)


# ==============================================================================
# PRIMEROS PASOS: PLANTILLAS QUE EL DOCENTE SUBE UNA VEZ A SU CARPETA DE DRIVE
# ==============================================================================
@st.cache_data(ttl=300)
def list_teacher_file_names(folder_id):
    """Nombres de los archivos en la carpeta del docente (o en datos/ en modo local)."""
    try:
        if _drive_ready(folder_id):
            res = get_drive_service().files().list(
                q=f"'{folder_id}' in parents and trashed = false", fields='files(name)', pageSize=500,
                supportsAllDrives=True, includeItemsFromAllDrives=True
            ).execute(num_retries=3)
            return sorted({f['name'] for f in res.get('files', [])})
        return sorted(os.listdir(DATA_DIR)) if os.path.isdir(DATA_DIR) else []
    except Exception:
        return []


def setup_files_spec(raw_khan, unique_task_types):
    """
    Archivos que usa el sistema, con una plantilla lista para subir. Google Drive no permite que la
    aplicación cree archivos nuevos en carpetas personales, pero sí actualizar los que ya existen:
    por eso el docente los sube una vez y a partir de ahí la app los mantiene.
    """
    def roster_seed():
        acc = khan_accounts(raw_khan)
        if acc.empty:
            return table_to_xlsx_bytes(pd.DataFrame(columns=ROSTER_COLS), "Lista")
        seed = pd.DataFrame({'Nombre': acc['Cuenta de Khan'], 'Grupo': acc['Grupo Khan']})
        seed['_t'] = seed['Nombre'].apply(name_tokens)
        seed = seed.drop_duplicates(['_t', 'Grupo']).drop(columns='_t')
        roster = ensure_roster_ids(normalize_roster(seed))
        return table_to_xlsx_bytes(roster.sort_values(['Grupo', 'Nombre']), "Lista")

    def topics_seed():
        acts = sorted(raw_khan['Nombre de la tarea'].dropna().astype(str).unique()) if not raw_khan.empty else []
        return table_to_xlsx_bytes(pd.DataFrame({'Actividad': acts, 'Tema': [''] * len(acts)}, columns=TEMAS_COLS), "Temas")

    def criterios_bytes():
        crit = get_default_teacher_criterios(unique_task_types)
        return json.dumps(crit, indent=4, ensure_ascii=False, default=str).encode('utf-8')

    return [
        ("criterios.json", "⚙️ Tu configuración: escala, pesos, fechas de parciales y criterios.", criterios_bytes),
        (ROSTER_FILE, "👥 Lista oficial de alumnos. Ya viene con los nombres y grupos de tus reportes de Khan: solo agrega las matrículas.", roster_seed),
        (LINKS_FILE, "🔗 Vínculos entre cuentas de Khan y tu lista (lo llena la app).", lambda: table_to_xlsx_bytes(pd.DataFrame(columns=LINK_COLS), "Vinculos")),
        (ATT_FILE, "🙋 Pase de lista (lo llena la app).", lambda: table_to_xlsx_bytes(pd.DataFrame(columns=ATT_COLS), "Asistencia")),
        (EVID_FILE, "📓 Sellos de evidencia (lo llena la app).", lambda: table_to_xlsx_bytes(pd.DataFrame(columns=EVID_COLS), "Evidencias")),
        (EXTRA_FILE, "📝 Examen y producto del parcial (lo llena la app).", lambda: table_to_xlsx_bytes(pd.DataFrame(columns=EXTRA_COLS), "Calificaciones")),
        (SEGUIMIENTO_FILE, "✅ Alumnos que marcaste como atendidos en Inicio, con tus notas (lo llena la app).", lambda: table_to_xlsx_bytes(pd.DataFrame(columns=SEGUIMIENTO_COLS), "Seguimiento")),
        (METAS_FILE, "🎯 Metas que se ponen tus alumnos en cada parcial (lo llenan ellos desde su portal).", lambda: table_to_xlsx_bytes(pd.DataFrame(columns=METAS_COLS), "Metas")),
        (TEMAS_FILE, "📚 Tema de cada actividad. Ya viene con tus actividades de Khan: llénalo aquí o en Ajustes → 📚 Temas.", topics_seed),
    ]


def missing_setup_files(folder_id):
    present = set(list_teacher_file_names(folder_id))
    return [name for name in [f[0] for f in setup_files_spec(pd.DataFrame(), [])] if name not in present]


def render_setup_section(folder_id, raw_khan, unique_task_types, carpeta_nombre):
    """Ajustes → Primeros pasos: qué archivos faltan en la carpeta y cómo subirlos."""
    import zipfile
    spec = setup_files_spec(raw_khan, unique_task_types)
    present = set(list_teacher_file_names(folder_id))
    missing = [s for s in spec if s[0] not in present]

    st.markdown("#### 🚀 Primeros pasos")
    st.markdown(
        "Por la configuración de Google, esta aplicación **puede actualizar** los archivos de tu carpeta, pero **no puede "
        "crearlos**. Por eso, la primera vez debes subir unas plantillas vacías. Solo se hace una vez:\n\n"
        "1. Descarga las plantillas que faltan (abajo).\n"
        "2. Si descargaste el .zip, descomprímelo en tu computadora.\n"
        f"3. Sube los archivos **tal cual, sin cambiarles el nombre**, a tu carpeta **{carpeta_nombre}** de Google Drive.\n"
        "4. Regresa aquí y presiona **Verificar**."
    )
    if _drive_ready(folder_id):
        st.link_button(f"📂 Abrir mi carpeta '{carpeta_nombre}' en Google Drive",
                       f"https://drive.google.com/drive/folders/{folder_id}", width='stretch')

    if not missing:
        st.success("✅ Tu carpeta tiene todos los archivos. Ya puedes usar la lista, el pase de lista, los sellos y las calificaciones del parcial.")
    else:
        st.warning(f"Faltan {len(missing)} archivo(s) en tu carpeta.")
        buff = io.BytesIO()
        with zipfile.ZipFile(buff, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name, _, builder in missing:
                zf.writestr(name, builder())
        st.download_button(f"📦 Descargar las {len(missing)} plantillas que faltan (.zip)", buff.getvalue(),
                           file_name="plantillas_portal_cbta24.zip", mime="application/zip", type="primary",
                           width='stretch', key="dl_setup_zip")

    st.markdown("##### Archivos de tu carpeta")
    for name, desc, builder in spec:
        ok = name in present
        c1, c2 = st.columns([4, 2], vertical_alignment="center")
        with c1:
            st.markdown(f"{'✅' if ok else '❌'} **`{name}`**  \n<span style='color:#64748b;font-size:0.85rem'>{html.escape(desc)}</span>",
                        unsafe_allow_html=True)
        with c2:
            if not ok:
                mime = "application/json" if name.endswith('.json') else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                st.download_button("📥 Descargar", builder(), file_name=name, mime=mime, width='stretch', key=f"dl_setup_{name}")
    if st.button("🔄 Verificar", width='stretch', key="verify_setup_btn"):
        list_teacher_file_names.clear()
        load_teacher_table.clear()
        load_teacher_criterios.clear()
        st.rerun()
    st.caption("💡 Los reportes CSV de Khan Academy y `credenciales.xlsx` (si los usas) también van en esta misma carpeta.")


# ==============================================================================
# FASE 6: TUTORÍA (VARIAS MATERIAS), REPORTE PARA LA FAMILIA (PDF), METAS Y TEMAS
# ==============================================================================
SCHOOL_NAME = "CBTA No. 24"
STATUS_DOT = {'Excelente': '🟢', 'Bien': '🟢', 'Regular': '🟡', 'En riesgo': '🔴'}


def parse_tutor_groups(value):
    """'5°H, 5J; todos' -> ['5°H', '5°J'] o ['*'] para todos los grupos."""
    parts = [p.strip() for p in re.split(r'[,;/]', str(value or '')) if p.strip()]
    if any(p.lower() in ('todos', 'todas', '*', 'all') for p in parts):
        return ['*']
    return sorted({_normalize_group(p) for p in parts})


def tutoria_subjects():
    """Materias registradas en docentes.xlsx (una por carpeta). En modo local, la carpeta datos/."""
    docentes = load_docentes_master()
    subjects = []
    if not docentes.empty:
        rows = docentes[docentes['carpeta_nombre'] != ''].drop_duplicates('carpeta_nombre')
        for _, r in rows.iterrows():
            fid = get_cached_folder_id(r['carpeta_nombre'])
            if fid:
                subjects.append({'materia': r['asignatura'] or r['carpeta_nombre'], 'docente': r['Nombre del Docente'],
                                 'email': r.get('e_mail', ''), 'folder_id': fid})
    if not subjects and not _drive_ready('x'):
        subjects.append({'materia': st.session_state.get('asignatura') or 'Materia (modo local)', 'docente': 'Docente',
                         'email': '', 'folder_id': None})
    return subjects


def subject_student_summary(subject, groups, parcial):
    """Resumen por alumno de una materia: promedio, estatus, atrasadas y asistencia."""
    folder_id = subject['folder_id']
    raw_khan = load_teacher_raw_assignments(folder_id)
    roster, links = load_roster_and_links(folder_id)
    raw = apply_roster_links(raw_khan, roster, links)
    if groups != ['*']:
        raw = raw[raw['Grupo'].isin(groups)] if not raw.empty else raw
        roster = roster[roster['Grupo'].isin(groups)] if not roster.empty else roster
    types = sorted(t for t in raw['Tipo de tarea'].dropna().astype(str).unique() if t) if (not raw.empty and 'Tipo de tarea' in raw.columns) else []
    cfg = khan_view_config(load_teacher_criterios(folder_id, types))
    rows = {}
    if not raw.empty:
        graded = assign_parciales_vectorized(apply_dynamic_grading(raw.copy(), cfg), cfg)
        if parcial:
            graded = graded[graded['Parcial'] == parcial]
        if not graded.empty:
            blocks = compute_student_block_grades(graded, cfg)
            avg = blocks.dropna(subset=['block_grade']).groupby(['Grupo', 'Nombre del estudiante'])['block_grade'].mean()
            overdue = graded[graded['status'] == 'No completado'].groupby(['Grupo', 'Nombre del estudiante']).size()
            for (g, n) in graded.groupby(['Grupo', 'Nombre del estudiante']).size().index:
                rows[(g, n)] = {'Grupo': g, 'Nombre': n, 'Promedio': avg.get((g, n)), 'Atrasadas': int(overdue.get((g, n), 0))}
    # Alumnos de la lista sin actividad en Khan también cuentan (son los más invisibles)
    for _, r in roster.iterrows():
        rows.setdefault((r['Grupo'], r['Nombre']), {'Grupo': r['Grupo'], 'Nombre': r['Nombre'], 'Promedio': None, 'Atrasadas': 0, 'sin_khan': True})

    evid, extra, att = load_eval_tables(folder_id)
    att_map = attendance_by_name(roster, att, cfg, parcial) if not roster.empty else {}
    finals = {}
    # En un parcial concreto se usa la calificación del parcial (con evidencias, examen, etc.);
    # en "Todo el semestre", el promedio de Khan, que es lo único comparable entre parciales.
    uses_any = uses_components(cfg) or any(uses_components(group_config(cfg, g, parcial)) for g in roster['Grupo'].unique())
    if parcial and uses_any and not roster.empty:
        p_eval = parcial
        comps = compute_components(roster, evid, extra, att, cfg, p_eval)
        khan_names = {}
        if not raw.empty:
            g_all = assign_parciales_vectorized(apply_dynamic_grading(raw.copy(), cfg), cfg)
            khan_names = _khan_avg_by_name(g_all, cfg, p_eval)
        fin = compute_final_grades(comps, khan_names, cfg, p_eval)
        finals = dict(zip(fin['Nombre'], fin['Final']))

    out = []
    scale = int(cfg.get('escala_maxima', 10))
    for (g, n), r in rows.items():
        value = finals.get(n) if pd.notna(finals.get(n)) else r['Promedio']
        out.append({
            'Grupo': g, 'Nombre': n, 'Materia': subject['materia'], 'Docente': subject['docente'], 'Correo': subject['email'],
            'Promedio': round(value, 1) if value is not None and not pd.isna(value) else None,
            'Estatus': classify_for(value, cfg, g) if value is not None and not pd.isna(value) else 'Sin datos',
            'Atrasadas': r['Atrasadas'],
            'Asistencia %': round(att_map[n]) if n in att_map else None,
            'Asistencia mínima': float(cfg.get('asistencia_minima', 80)),
            'Sin Khan': bool(r.get('sin_khan')),
            '_key': f"{g}|{' '.join(name_tokens(n))}",
        })
    return out


def build_tutoria_data(groups, parcial):
    data = []
    for subj in tutoria_subjects():
        try:
            data.extend(subject_student_summary(subj, groups, parcial))
        except Exception as e:
            st.warning(f"No se pudo leer la materia {subj['materia']}: {e}")
    df = pd.DataFrame(data)
    if df.empty:
        return df
    # Nombre a mostrar: el más frecuente para cada alumno (normalmente el de la lista oficial)
    display = df.groupby('_key')['Nombre'].agg(lambda s: s.value_counts().index[0])
    df['Alumno'] = df['_key'].map(display)
    return df


def tutoria_priorities(df):
    rows = []
    for key, g in df.groupby('_key'):
        risk = g[g['Estatus'] == 'En riesgo']
        low_att = g[g['Asistencia %'].notna() & (g['Asistencia %'] < g['Asistencia mínima'])]
        no_khan = g[g['Sin Khan']]
        n_risk = len(risk)
        if n_risk == 0 and low_att.empty and no_khan.empty:
            continue
        if n_risk >= 3:
            action = "Reunión con la familia y canalizar a orientación educativa"
        elif n_risk == 2:
            action = "Entrevista de tutoría y plan de recuperación con los docentes de esas materias"
        elif n_risk == 1:
            action = f"Dar seguimiento con el docente de {risk.iloc[0]['Materia']}"
        elif low_att.empty:
            action = "Ayudarle a entrar a Khan Academy y avisar a sus docentes"
        else:
            action = "Platicar con el alumno sobre sus faltas"
        if not low_att.empty:
            action += "; revisar faltas y justificantes con la familia"
        rows.append({
            'Alumno': g['Alumno'].iloc[0], 'Grupo': g['Grupo'].iloc[0], 'n_risk': n_risk,
            'risk': [f"{r['Materia']} ({r['Promedio']:.1f})" if pd.notna(r['Promedio']) else r['Materia'] for _, r in risk.iterrows()],
            'att': [f"{r['Materia']} ({r['Asistencia %']:.0f}%)" for _, r in low_att.iterrows()],
            'no_khan': list(no_khan['Materia']),
            'atrasadas': int(g['Atrasadas'].sum()),
            'action': action,
            'min_att': low_att['Asistencia %'].min() if not low_att.empty else 101,
        })
    return sorted(rows, key=lambda r: (-r['n_risk'], r['min_att'], -r['atrasadas']))


def _pdf_txt(text):
    """fpdf con fuentes base solo admite latin-1: se limpian emojis y guiones largos."""
    text = str(text).replace('—', '-').replace('–', '-').replace('•', '-').replace('“', '"').replace('”', '"')
    return text.encode('latin-1', 'ignore').decode('latin-1')


def build_report_pdf(student, group, subtitle, tables, paragraphs):
    """
    Reporte de avance para la familia. tables: [(título, [encabezados], [[celdas]], [anchos])];
    paragraphs: [(título, texto)].
    """
    from fpdf import FPDF
    pdf = FPDF(orientation='P', unit='mm', format='Letter')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(30, 58, 138)
    pdf.rect(0, 0, 216, 28, 'F')
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_xy(12, 7)
    pdf.cell(0, 8, _pdf_txt(f"{SCHOOL_NAME} - Reporte de avance"))
    pdf.set_font('Helvetica', '', 10)
    pdf.set_xy(12, 16)
    pdf.cell(0, 6, _pdf_txt(subtitle))
    pdf.set_text_color(15, 23, 42)
    pdf.set_xy(12, 34)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 7, _pdf_txt(str(student).title()), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Helvetica', '', 10)
    pdf.set_x(12)
    pdf.cell(0, 6, _pdf_txt(f"Grupo {group}  -  Fecha: {now_local().strftime('%d/%m/%Y')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    for title, headers, rows, widths in tables:
        pdf.set_x(12)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 7, _pdf_txt(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(226, 232, 240)
        pdf.set_x(12)
        for h, w in zip(headers, widths):
            pdf.cell(w, 7, _pdf_txt(h), border=1, fill=True)
        pdf.ln()
        pdf.set_font('Helvetica', '', 9)
        for row in rows:
            pdf.set_x(12)
            for c, w in zip(row, widths):
                txt = _pdf_txt(c)
                while pdf.get_string_width(txt) > w - 2 and len(txt) > 3:
                    txt = txt[:-4] + '...'
                pdf.cell(w, 7, txt, border=1)
            pdf.ln()
        pdf.ln(3)
    for title, text in paragraphs:
        pdf.set_x(12)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(0, 7, _pdf_txt(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Helvetica', '', 10)
        pdf.set_x(12)
        pdf.multi_cell(190, 5.5, _pdf_txt(text))
        pdf.ln(2)
    # Las firmas siempre juntas al final (sin quedar solas en otra hoja si caben)
    if pdf.get_y() > pdf.h - 35:
        pdf.add_page()
    pdf.ln(8)
    pdf.set_x(12)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(90, 6, "______________________________")
    pdf.cell(90, 6, "______________________________", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(12)
    pdf.cell(90, 5, _pdf_txt("Firma del docente / tutor(a)"))
    pdf.cell(90, 5, _pdf_txt("Firma de madre, padre o tutor"))
    return bytes(pdf.output())


def tutoria_report_pdf(df, key_name, group):
    g = df[df['Alumno'] == key_name]
    rows = [[r['Materia'], r['Docente'], f"{r['Promedio']:.1f}" if pd.notna(r['Promedio']) else "-",
             r['Estatus'], str(r['Atrasadas']), f"{r['Asistencia %']:.0f}%" if pd.notna(r['Asistencia %']) else "-"]
            for _, r in g.sort_values('Materia').iterrows()]
    n_risk = int((g['Estatus'] == 'En riesgo').sum())
    if n_risk:
        text = (f"{str(key_name).title()} presenta riesgo en {n_risk} materia(s). Le pedimos su apoyo para revisar juntos sus "
                "actividades pendientes y acordar un plan de recuperación con los docentes.")
    else:
        text = f"{str(key_name).title()} no presenta materias en riesgo en este periodo. Le agradecemos su acompañamiento."
    return build_report_pdf(key_name, group, "Resumen por materia (tutoría académica)",
                            [("Avance por materia", ["Materia", "Docente", "Promedio", "Estatus", "Atrasadas", "Asistencia"], rows,
                              [52, 48, 22, 26, 20, 24])],
                            [("Observaciones", text)])


def render_tutoria(groups, show_title=True):
    """Vista de tutoría académica / orientación / subdirección: varias materias a la vez."""
    if show_title:
        st.markdown("### 🧭 Tutoría académica")
    st.caption("Reúne lo que registran todos los docentes: así se ve a quién atender primero, aunque en cada materia "
               "parezca un caso aislado. " + ("Grupos: todos." if groups == ['*'] else f"Grupos: {', '.join(groups)}."))
    p_opts = ["Todo el semestre"] + PARCIALES
    c1, c2 = st.columns(2)
    with c2:
        p_sel = st.selectbox("Periodo:", p_opts, index=p_opts.index(current_parcial({})) if current_parcial({}) in p_opts else 0, key="tut_parcial")
    parcial = None if p_sel == "Todo el semestre" else p_sel
    with st.spinner("Reuniendo la información de todas las materias..."):
        df = build_tutoria_data(groups, parcial)
    if df.empty:
        st.info("Aún no hay información de las materias de estos grupos.")
        return
    with c1:
        g_opts = sorted(df['Grupo'].dropna().unique())
        grupo = st.selectbox("Grupo:", g_opts, key="tut_group")
    df = df[df['Grupo'] == grupo]
    pri = tutoria_priorities(df)
    n_al = df['_key'].nunique()
    n2 = sum(1 for p in pri if p['n_risk'] >= 2)
    n1 = sum(1 for p in pri if p['n_risk'] == 1)
    natt = sum(1 for p in pri if p['att'])
    stats = [("👥 Alumnos", f"{n_al}"), ("🔴 En riesgo en 2+ materias", f"{n2}"),
             ("🟠 En riesgo en 1 materia", f"{n1}"), ("🙋 Asistencia baja", f"{natt}")]
    st.markdown(compact_html("<div class='mini-stats teacher-stats'>" + "".join(
        f"<div class='mini-stat'><div class='mini-label'>{l}</div><div class='mini-val'>{v}</div></div>" for l, v in stats) + "</div>"),
        unsafe_allow_html=True)

    st.markdown("#### 🆘 A quién atender primero")
    if not pri:
        st.success("🎉 Nadie del grupo tiene materias en riesgo ni asistencia baja en este periodo.")
    else:
        cards = []
        for p in pri:
            high = p['n_risk'] >= 2 or bool(p['att'])
            items = []
            if p['risk']:
                items.append(f"<li>En riesgo en <strong>{p['n_risk']}</strong>: {html.escape(', '.join(p['risk']))}</li>")
            if p['att']:
                items.append(f"<li>Asistencia baja en: {html.escape(', '.join(p['att']))}</li>")
            if p['no_khan']:
                items.append(f"<li>Sin actividad en Khan en: {html.escape(', '.join(p['no_khan']))}</li>")
            if p['atrasadas']:
                items.append(f"<li>{p['atrasadas']} actividad(es) atrasada(s) en total</li>")
            cards.append(f"""
            <div class="student-card" style="border-left-color: {'#dc2626' if high else '#d97706'};">
                <div class="sc-head"><div><span class="sc-name">{html.escape(p['Alumno'])}</span>
                <span class="sc-meta">{html.escape(str(p['Grupo']))}</span></div></div>
                <div class="sc-body"><div><div class="sc-label">Situación</div><ul>{''.join(items)}</ul></div>
                <div><div class="sc-label">Acción sugerida</div><ul><li>{html.escape(p['action'])}</li></ul></div></div>
            </div>""")
        st.markdown(compact_html("<div class='student-cards'>" + "".join(cards) + "</div>"), unsafe_allow_html=True)

    st.markdown("#### 📋 Concentrado por materia")
    st.caption("En un parcial se muestra la calificación del parcial de cada materia (con evidencias, examen, etc., si el "
               "docente los usa); en todo el semestre, el promedio de Khan Academy. ⚪ = sin datos todavía.")
    mat = df.pivot_table(index='Alumno', columns='Materia', values='Promedio', aggfunc='first')
    stat = df.pivot_table(index='Alumno', columns='Materia', values='Estatus', aggfunc='first')
    view = mat.copy().astype(object)
    for c in mat.columns:
        view[c] = [f"{STATUS_DOT.get(s, '⚪')} {v:.1f}" if pd.notna(v) else "⚪ —" for v, s in zip(mat[c], stat[c])]
    view['Materias en riesgo'] = (stat == 'En riesgo').sum(axis=1)
    view = view.sort_values('Materias en riesgo', ascending=False).reset_index()
    st.dataframe(view, hide_index=True, width='stretch', height=min(560, 40 + len(view) * 36))
    st.download_button("📥 Descargar concentrado (Excel)", table_to_xlsx_bytes(mat.reset_index(), "Tutoria"),
                       file_name=f"Tutoria_{grupo.replace('°', '')}_{now_local().strftime('%Y%m%d')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_tutoria")

    st.markdown("#### 🔍 Detalle de un alumno")
    al = st.selectbox("Alumno:", sorted(df['Alumno'].unique()), key="tut_student")
    det = df[df['Alumno'] == al][['Materia', 'Docente', 'Correo', 'Promedio', 'Estatus', 'Atrasadas', 'Asistencia %']].sort_values('Materia')
    det_view = det.copy()
    det_view['Promedio'] = det_view['Promedio'].apply(lambda v: f"{v:.1f}" if v is not None and pd.notna(v) else "—")
    det_view['Asistencia %'] = det_view['Asistencia %'].apply(lambda v: f"{v:.0f}%" if v is not None and pd.notna(v) else "—")
    st.dataframe(det_view, hide_index=True, width='stretch')
    st.download_button("📄 Reporte para la familia (PDF)", tutoria_report_pdf(df, al, grupo),
                       file_name=f"Reporte_{re.sub(r'[^A-Za-z0-9]+', '_', str(al))}.pdf", mime="application/pdf",
                       type="primary", key="dl_tutoria_pdf")


def render_tutor_only():
    """Sesión de tutor(a) o directivo sin materia propia: solo la vista de tutoría."""
    name = st.session_state.get('teacher_name', 'Tutor(a)')
    h1, h2 = st.columns([5, 1])
    with h1:
        st.markdown(f"""
        <div class="main-header" style="background: linear-gradient(135deg, #064e3b 0%, #0f766e 100%);">
            <h1>🧭 Tutoría académica</h1><p>{html.escape(str(name))}</p>
        </div>""", unsafe_allow_html=True)
    with h2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", width='stretch', key="tutor_logout"):
            st.session_state.clear()
            st.rerun()
    render_tutoria(st.session_state.get('tutor_groups') or ['*'], show_title=False)



# ------------------------------------------------------------------------------
# Metas del alumno por parcial
# ------------------------------------------------------------------------------
METAS_FILE = "metas.xlsx"
METAS_COLS = ['ID alumno', 'Parcial', 'Meta', 'Plan', 'Actualizado']


def load_goals(folder_id):
    return _norm_table(load_teacher_table(folder_id, METAS_FILE), METAS_COLS)


def student_goal(goals, student_id, parcial):
    if goals is None or goals.empty or not student_id:
        return None
    g = goals[(goals['ID alumno'] == student_id) & (goals['Parcial'] == parcial)]
    if g.empty:
        return None
    r = g.iloc[-1]
    meta = pd.to_numeric(r['Meta'], errors='coerce')
    return {'meta': None if pd.isna(meta) else float(meta), 'plan': r['Plan'], 'actualizado': r['Actualizado']}


def parcial_average(tasks, criteria_config, parcial):
    """Promedio de los bloques ya evaluados del parcial (escala de la vista)."""
    t = tasks[tasks['Parcial'] == parcial] if 'Parcial' in tasks.columns else tasks
    if t.empty:
        return None
    b = compute_student_block_grades(t, criteria_config)['block_grade'].dropna()
    return float(b.mean()) if not b.empty else None


def student_parcial_value(eval_ctx, student_id, tasks, criteria_config, parcial):
    """Calificación del parcial hasta hoy: la final (con componentes) si el docente los usa, si no el promedio de Khan."""
    cfg = criteria_config or {}
    roster = (eval_ctx or {}).get('roster')
    if roster is not None and not roster.empty and student_id in set(roster['ID']):
        cfg = group_config(cfg, roster.set_index('ID').at[student_id, 'Grupo'], parcial)
    if uses_components(cfg) and roster is not None and not roster.empty and student_id in set(roster['ID']):
        comps = compute_components(roster[roster['ID'] == student_id], eval_ctx['evid'], eval_ctx['extra'], eval_ctx['att'], cfg, parcial)
        name = roster.set_index('ID').at[student_id, 'Nombre']
        khan = _khan_avg_by_name(tasks.assign(**{'Nombre del estudiante': name}), cfg, parcial)
        fin = compute_final_grades(comps, khan, cfg, parcial)
        if not fin.empty and fin.iloc[0]['Final'] is not None and pd.notna(fin.iloc[0]['Final']):
            return float(fin.iloc[0]['Final'])
        return None
    return parcial_average(tasks, cfg, parcial)


def render_student_goals(folder_id, student_id, tasks, criteria_config, key_prefix, eval_ctx=None):
    """Pestaña 🎯 Mi meta: el alumno se pone una meta para el parcial y escribe qué hará para lograrla."""
    cfg = criteria_config or {}
    scale = float(cfg.get('escala_maxima', 10))
    parcial = current_parcial(cfg)
    goals = load_goals(folder_id)
    goal = student_goal(goals, student_id, parcial)
    avg = student_parcial_value(eval_ctx, student_id, tasks, cfg, parcial)
    readonly = key_prefix == 'admin'

    st.markdown(f"#### 🎯 Mi meta para el {parcial}")
    st.caption("Ponerte una meta concreta y escribir cómo la vas a lograr ayuda mucho más que solo \"echarle ganas\". "
               "Tu docente puede verla para apoyarte.")
    if goal and goal['meta'] is not None:
        if avg is None:
            st.info(f"Tu meta: **{goal['meta']:g}**. Aún no hay actividades evaluadas en este parcial.")
        else:
            gap = goal['meta'] - avg
            st.progress(min(1.0, max(0.0, avg / goal['meta'])) if goal['meta'] else 1.0,
                        text=f"Llevas {avg:.1f} de tu meta de {goal['meta']:g} (calificación del parcial hasta hoy)")
            if gap <= 0:
                st.success(f"🎉 ¡Vas por encima de tu meta! (+{-gap:.1f}). ¿Te animas a subirla?")
            else:
                st.warning(f"Te faltan **{gap:.1f}** puntos para tu meta. Revisa **📝 Pendientes**: ahí ves cuánto puedes recuperar.")
        if goal['plan']:
            st.markdown(f"**Mi plan:** {html.escape(goal['plan'])}")
    elif readonly:
        st.info("El alumno todavía no registra una meta para este parcial.")

    if readonly:
        return
    if _drive_ready(folder_id) and METAS_FILE not in set(list_teacher_file_names(folder_id)):
        st.info("Tu docente aún no activa las metas en esta materia.")
        return
    with st.form(f"{key_prefix}_goal_form"):
        min_pass = float((cfg.get('thresholds') or {}).get('regular', scale * 0.6))
        if goal and goal['meta'] is not None:
            default = goal['meta']
        elif avg is None:
            default = scale * 0.8
        else:
            # Si va reprobando, la primera meta es aprobar; si no, subir un punto (o 10 en escala de 100)
            default = min_pass if avg < min_pass else min(scale, round(avg + scale / 10, 1))
        meta = st.number_input(f"¿Qué calificación quieres lograr en el {parcial}?", min_value=0.0, max_value=scale,
                               value=float(default), step=0.5 if scale == 10 else 5.0, key=f"{key_prefix}_goal_val")
        plan = st.text_area("¿Qué vas a hacer para lograrlo?", value=goal['plan'] if goal else "", max_chars=250,
                            placeholder="Ej. Hacer los ejercicios de Khan el mismo día que los deja el profe y llevar mi libreta a revisión cada semana.",
                            key=f"{key_prefix}_goal_plan")
        if st.form_submit_button("💾 Guardar mi meta", type="primary", width='stretch'):
            table = _norm_table(read_teacher_table(folder_id, METAS_FILE), METAS_COLS)
            new = pd.DataFrame([{'ID alumno': student_id, 'Parcial': parcial, 'Meta': f"{meta:g}", 'Plan': plan.strip(),
                                 'Actualizado': now_local().strftime('%Y-%m-%d %H:%M')}])
            level, msg, saved = save_teacher_table(folder_id, METAS_FILE, upsert_rows(table, new, ['ID alumno', 'Parcial']), "Metas")
            st.session_state.pop('_pending_upload', None)
            if saved:
                set_flash('success', "✅ ¡Meta guardada! Vuelve seguido para ver cómo vas.")
                st.rerun()
            else:
                st.error("No se pudo guardar tu meta en este momento. Intenta más tarde o avísale a tu docente.")


# ------------------------------------------------------------------------------
# Dominio por tema
# ------------------------------------------------------------------------------
TEMAS_FILE = "temas.xlsx"
TEMAS_COLS = ['Actividad', 'Tema']
TOPIC_LEVELS = [(85, "🟢 Dominado", "#16a34a"), (60, "🟡 En camino", "#d97706"), (0, "🔴 Por reforzar", "#dc2626")]


def load_topics_map(folder_id):
    t = _norm_table(load_teacher_table(folder_id, TEMAS_FILE), TEMAS_COLS)
    t = t[(t['Actividad'] != '') & (t['Tema'] != '')]
    return dict(zip(t['Actividad'].str.strip(), t['Tema'].str.strip()))


def topic_level(pct):
    for lim, label, color in TOPIC_LEVELS:
        if pct >= lim:
            return label, color
    return TOPIC_LEVELS[-1][1], TOPIC_LEVELS[-1][2]


def topic_mastery(tasks, topics_map):
    """Dominio (%) por tema con las actividades ya evaluadas: puntos obtenidos / puntos posibles."""
    if tasks is None or tasks.empty or not topics_map:
        return pd.DataFrame(columns=['Tema', 'Dominio %', 'Evaluadas', 'Por venir', 'Para repasar'])
    t = tasks.copy()
    t['Tema'] = t['Nombre de la tarea'].astype(str).str.strip().map(topics_map)
    t = t.dropna(subset=['Tema'])
    rows = []
    for tema, g in t.groupby('Tema'):
        ev = g[~g['status'].isin(NOT_EVALUATED_STATUSES)]
        mx = ev['max_points'].sum()
        pct = ev['earned_points'].sum() / mx * 100 if mx > 0 else None
        weak = ev[ev['earned_points'] < ev['max_points'] * 0.7]
        rows.append({'Tema': tema, 'Dominio %': round(pct) if pct is not None else None, 'Evaluadas': len(ev),
                     'Por venir': int(g['status'].isin(NOT_EVALUATED_STATUSES).sum()),
                     'Para repasar': list(weak['Nombre de la tarea'].astype(str).unique())[:4]})
    return pd.DataFrame(rows).sort_values('Dominio %', na_position='last').reset_index(drop=True)


def render_topic_bars(mastery):
    bars = []
    for _, r in mastery.iterrows():
        if r['Dominio %'] is None or pd.isna(r['Dominio %']):
            bars.append(f"<div class='topic-row'><div class='topic-name'>{html.escape(r['Tema'])}</div>"
                        f"<div class='topic-meta'>⚪ Aún sin evaluar · {r['Por venir']} actividad(es) por venir</div></div>")
            continue
        label, color = topic_level(r['Dominio %'])
        bars.append(f"""<div class='topic-row'><div class='topic-head'><span class='topic-name'>{html.escape(r['Tema'])}</span>
            <span class='topic-pct' style='color:{color}'>{int(r['Dominio %'])}% · {label}</span></div>
            <div class='topic-track'><div class='topic-fill' style='width:{int(r['Dominio %'])}%;background:{color}'></div></div></div>""")
    st.markdown(compact_html("<div class='topic-list'>" + "".join(bars) + "</div>"), unsafe_allow_html=True)


def render_student_topics(tasks, topics_map):
    st.markdown("#### 📚 Mis temas")
    st.caption("Qué tan bien dominas cada tema, según tus resultados en las actividades ya evaluadas. "
               "🟢 85% o más · 🟡 60 a 84% · 🔴 menos de 60%.")
    mastery = topic_mastery(tasks, topics_map)
    if mastery.empty:
        st.info("Tu docente aún no ha organizado las actividades por tema.")
        return
    render_topic_bars(mastery)
    weak = mastery[mastery['Dominio %'].notna() & (mastery['Dominio %'] < 60)]
    if not weak.empty:
        r = weak.iloc[0]
        tip = f"💡 **Para reforzar {r['Tema']}**, vuelve a practicar: " + ", ".join(f"*{a}*" for a in r['Para repasar']) + "." \
            if r['Para repasar'] else f"💡 Pídele a tu docente material extra de **{r['Tema']}**."
        st.info(tip + " En Khan Academy puedes repetir los ejercicios para practicar aunque ya hayan vencido.")
    elif mastery['Dominio %'].notna().any():
        st.success("🎉 No tienes temas por reforzar. ¡Excelente trabajo!")


def render_topics_setup(folder_id, raw_khan):
    """Ajustes → 📚 Temas: el docente asigna un tema a cada actividad de Khan."""
    st.markdown("#### 📚 Temas de tu materia")
    st.caption("Escribe el tema de cada actividad (por ejemplo, *Distancia entre dos puntos* o *Pendiente de una recta*). "
               "Con esto, cada alumno ve qué temas domina y cuáles debe reforzar, y tú ves los temas que más le cuestan al grupo. "
               "Tip: escribe el tema igual en todas sus actividades; las que dejes vacías no cuentan.")
    if raw_khan.empty:
        st.info("Primero sube tus reportes de Khan Academy.")
        return
    acts = (raw_khan.assign(_d=pd.to_datetime(raw_khan.get('dt_entrega'), errors='coerce'))
            .groupby('Nombre de la tarea', as_index=False).agg(Tipo=('Tipo de tarea', 'first'), Entrega=('_d', 'min'))
            .sort_values(['Entrega', 'Nombre de la tarea']))
    current = load_topics_map(folder_id)
    editor = pd.DataFrame({
        'Actividad': acts['Nombre de la tarea'].astype(str).values,
        'Tipo': acts['Tipo'].astype(str).values,
        'Entrega': acts['Entrega'].apply(lambda d: format_short_date(d, with_time=False) if pd.notna(d) else '').values,
        'Tema': [current.get(a.strip(), '') for a in acts['Nombre de la tarea'].astype(str)],
    })
    known = sorted(set(current.values()))
    if known:
        st.caption("Temas que ya usas: " + " · ".join(f"`{k}`" for k in known))
    edited = st.data_editor(editor, hide_index=True, width='stretch', key="topics_editor",
                            disabled=['Actividad', 'Tipo', 'Entrega'],
                            column_config={'Tema': st.column_config.TextColumn("Tema", width="medium"),
                                           'Actividad': st.column_config.TextColumn("Actividad", width="large")},
                            height=min(600, 40 + len(editor) * 35))
    done = int((edited['Tema'].fillna('').str.strip() != '').sum())
    st.caption(f"{done} de {len(edited)} actividades con tema.")
    if st.button("💾 Guardar temas", type="primary", width='stretch', key="save_topics_btn"):
        out = edited[['Actividad', 'Tema']].copy()
        out['Tema'] = out['Tema'].fillna('').astype(str).str.strip()
        # Conservar temas de actividades que ya no aparecen en los reportes actuales
        prev = _norm_table(read_teacher_table(folder_id, TEMAS_FILE), TEMAS_COLS)
        prev = prev[~prev['Actividad'].isin(out['Actividad']) & (prev['Tema'] != '')]
        level, msg, saved = save_teacher_table(folder_id, TEMAS_FILE, pd.concat([prev, out], ignore_index=True), "Temas")
        _finish_save([(level, msg, saved)])
    _show_pending_upload("dl_pending_topics")


def render_group_topics(tasks, topics_map):
    """Calificaciones → Por tema: dominio promedio de cada tema por grupo y alumnos por reforzar."""
    st.markdown("#### 📚 Dominio por tema")
    if not topics_map:
        st.info("Asigna un tema a tus actividades en **⚙️ Ajustes → 📚 Temas** para ver este análisis.")
        return
    rows = []
    for (grupo, alumno), g in tasks.groupby(['Grupo', 'Nombre del estudiante']):
        m = topic_mastery(g, topics_map)
        for _, r in m.iterrows():
            if r['Dominio %'] is not None and pd.notna(r['Dominio %']):
                rows.append({'Grupo': grupo, 'Alumno': alumno, 'Tema': r['Tema'], 'Dominio %': r['Dominio %']})
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Todavía no hay actividades evaluadas con tema asignado.")
        return
    summary = df.groupby('Tema').agg(**{'Dominio promedio %': ('Dominio %', 'mean'),
                                         'Alumnos por reforzar': ('Dominio %', lambda s: int((s < 60).sum())),
                                         'Alumnos': ('Dominio %', 'size')}).sort_values('Dominio promedio %')
    summary['Dominio promedio %'] = summary['Dominio promedio %'].round(0)
    st.caption("Los temas con menor dominio aparecen primero: buenos candidatos para repasar en clase.")
    render_topic_bars(summary.reset_index().rename(columns={'Dominio promedio %': 'Dominio %'}).assign(**{'Por venir': 0}))
    by_group = df.pivot_table(index='Tema', columns='Grupo', values='Dominio %', aggfunc='mean').round(0)
    st.dataframe(by_group.reset_index(), hide_index=True, width='stretch')
    tema = st.selectbox("Ver alumnos por reforzar en el tema:", list(summary.index), key="topic_detail_sel")
    weak = df[(df['Tema'] == tema) & (df['Dominio %'] < 60)].sort_values('Dominio %')
    if weak.empty:
        st.success("Nadie está por debajo de 60% en este tema.")
    else:
        st.dataframe(weak[['Grupo', 'Alumno', 'Dominio %']], hide_index=True, width='stretch')


# ------------------------------------------------------------------------------
# Reporte de una materia para la familia (desde el panel docente)
# ------------------------------------------------------------------------------
def subject_report_pdf(student, group, asignatura, teacher_name, tasks, criteria_config, final_row=None, att_pct=None,
                       goal=None, mastery=None):
    cfg = criteria_config or {}
    ins = build_student_insights(tasks, cfg)
    scale = int(cfg.get('escala_maxima', 10))
    tables, paragraphs = [], []
    rows = []
    for p in PARCIALES:
        avg = parcial_average(tasks, cfg, p)
        if avg is not None:
            rows.append([p, f"{avg:.1f} / {scale}", classify_student(avg, cfg.get('thresholds', {}), scale)])
    if rows:
        tables.append(("Khan Academy por parcial", ["Parcial", "Promedio", "Estatus"], rows, [50, 50, 50]))
    if final_row is not None:
        weights = {**DEFAULT_COMPONENTES, **(cfg.get('componentes') or {})}
        used = {'Khan': khan_weight(cfg), 'Evidencias': weights['evidencias'], 'Examen': weights['examen'],
                'Producto': weights['producto'], 'Asistencia %': weights['asistencia']}
        keys = [k for k, w in used.items() if w > 0] + ['Final']
        cells = ["-" if final_row.get(k) is None or pd.isna(final_row.get(k)) else
                 (f"{final_row[k]:.0f}%" if k == 'Asistencia %' else f"{final_row[k]:g}") for k in keys]
        heads = [f"{'Asistencia' if k == 'Asistencia %' else k} ({used[k]:g}%)" if k in used else "Calificación" for k in keys]
        tables.append((f"Calificación del {current_parcial(cfg)}", heads, [cells], [round(186 / len(keys))] * len(keys)))
        if final_row.get('Pendiente'):
            paragraphs.append(("Nota", f"Aún falta registrar: {final_row['Pendiente']}. La calificación puede cambiar."))
    if mastery is not None and not mastery.empty:
        trows = [[r['Tema'], "-" if r['Dominio %'] is None or pd.isna(r['Dominio %']) else f"{int(r['Dominio %'])}%",
                  "Sin evaluar" if r['Dominio %'] is None or pd.isna(r['Dominio %']) else topic_level(r['Dominio %'])[0][2:]]
                 for _, r in mastery.iterrows()]
        tables.append(("Dominio por tema", ["Tema", "Dominio", "Nivel"], trows, [100, 30, 50]))
    pend = ins['overdue'].head(8)
    if not pend.empty:
        tables.append(("Actividades vencidas que aún puede hacer", ["Actividad", "Venció"],
                       [[r['Nombre de la tarea'], format_short_date(r['dt_entrega'], with_time=False)] for _, r in pend.iterrows()], [140, 40]))
    if att_pct is not None:
        minimum = float(cfg.get('asistencia_minima', 80))
        paragraphs.append(("Asistencia", f"Asistencia en el periodo: {att_pct:.0f}% (mínimo requerido: {minimum:.0f}%)."))
    if goal and goal.get('meta') is not None:
        paragraphs.append(("Meta del alumno", f"Se propuso obtener {goal['meta']:g} en el {current_parcial(cfg)}."
                           + (f" Su plan: {goal['plan']}" if goal.get('plan') else "")))
    paragraphs.append(("Mensaje del docente", build_student_message(ins, student, asignatura, teacher_name, 'familia')))
    return build_report_pdf(student, group, f"{asignatura} - Docente: {teacher_name}", tables, paragraphs)


def _group_criteria_rows(criterios, groups):
    """Resumen de los criterios que usa cada grupo en cada parcial."""
    view = khan_view_config(criterios)
    rows = []
    for g in groups:
        for p in PARCIALES:
            over = group_overrides(criterios, g, p)
            cfg = group_config(view, g, p)
            w = {**DEFAULT_COMPONENTES, **(cfg.get('componentes') or {})}
            rows.append({'Grupo': g, 'Parcial': p,
                         'Origen': ("Propios del parcial" if over and over['del_parcial'] else "Propios del grupo" if over else "Generales"),
                         'Khan %': khan_weight(cfg), 'Evidencias %': w['evidencias'], 'Examen %': w['examen'],
                         'Producto %': w['producto'], 'Asistencia %': w['asistencia'],
                         'En riesgo si es menor a': float((cfg.get('thresholds') or {}).get('regular', 6))})
    return pd.DataFrame(rows)


def render_group_criteria(folder_id, criterios, groups):
    """Ajustes → Criterios → 👥 Por grupo: pesos y clasificación acordados con cada grupo."""
    st.markdown("##### 👥 Criterios por grupo")
    st.caption("Si acuerdas la forma de evaluar con cada grupo, aquí defines el peso de Khan, los componentes del parcial y "
               "la clasificación de cada uno. La escala, las fechas de los parciales, los criterios por tipo de tarea, la "
               "asistencia mínima y la rúbrica de evidencias son las mismas para todos tus grupos.")
    modes = ["Los mismos criterios para todos mis grupos", "Criterios diferentes para cada grupo"]
    saved_on = bool(criterios.get('criterios_por_grupo'))
    mode = st.radio("¿Cómo evalúas a tus grupos?", modes, index=1 if saved_on else 0, key="grp_mode")
    want_on = mode == modes[1]
    if want_on != saved_on:
        msg = ("Al activarlo, cada grupo usará los criterios que le definas abajo (los que no tengan, usan los generales)."
               if want_on else "Al desactivarlo, todos los grupos usarán los criterios generales. Los criterios por grupo "
               "se conservan guardados por si vuelves a activarlos.")
        st.info(msg)
        if st.button("💾 Guardar este cambio", type="primary", key="save_grp_mode"):
            level, message = save_teacher_criterios(folder_id, {**criterios, 'criterios_por_grupo': want_on})
            set_flash(level, message)
            st.rerun()
    if not want_on:
        return
    if not groups:
        st.info("Aún no hay grupos: sube tus reportes de Khan Academy o tu lista de alumnos.")
        return

    scale = int(criterios.get('escala_maxima', 10))
    # Copia independiente: los cambios no deben tocar la configuración en memoria hasta guardarse
    grupos = json.loads(json.dumps(criterios.get('grupos') or {}, default=str))
    c1, c2 = st.columns(2)
    with c1:
        grupo = st.selectbox("Grupo:", groups, key="grp_sel")
    with c2:
        scopes = ["Todo el semestre"] + [f"Solo {p}" for p in PARCIALES]
        scope = st.selectbox("Aplica a:", scopes, key="grp_scope",
                             help="Si a partir de un parcial cambian los acuerdos, guárdalos solo para ese parcial: así no "
                                  "cambian las calificaciones de los parciales anteriores.")
    parcial = None if scope == scopes[0] else scope.replace("Solo ", "")
    over = group_overrides(criterios, grupo, parcial)
    cur = group_config(khan_view_config({**criterios, 'criterios_por_grupo': True}), grupo, parcial)
    cur_w = {**DEFAULT_COMPONENTES, **(cur.get('componentes') or {})}
    if over and (over['del_parcial'] or parcial is None):
        st.caption(f"✏️ {grupo} ya tiene criterios propios" + (f" para {parcial}." if parcial else "."))
    else:
        st.caption(f"Ahora {grupo} usa los criterios " + ("de su grupo para todo el semestre." if over else "generales.")
                   + " Ajusta y guarda para definir los suyos.")

    k = f"grpc_{grupo}_{scope}"
    cols = st.columns(len(COMPONENTES) + 1)
    with cols[0]:
        peso = st.number_input("🎓 Khan (%)", 0, 100, int(khan_weight(cur)), 5, key=f"{k}_khan")
    comp = {}
    for col, (ckey, clabel) in zip(cols[1:], COMPONENTES):
        with col:
            comp[ckey] = st.number_input(f"{clabel} (%)", 0, 100, int(float(cur_w.get(ckey, 0))), 5, key=f"{k}_{ckey}")
    total = peso + sum(comp.values())
    parts = [f"Khan {peso}%"] + [f"{lbl.split(' ', 1)[1]} {comp[c]}%" for c, lbl in COMPONENTES if comp[c]]
    if total == 100:
        st.success("✅ " + " + ".join(parts) + " = 100%")
    else:
        st.warning("⚠️ " + " + ".join(parts) + f" = **{total}%**. Deben sumar 100%.")

    th = None
    if parcial is None:
        cur_th = cur.get('thresholds') or {}
        step = 0.5 if scale == 10 else 1.0
        t1, t2, t3 = st.columns(3)
        with t1:
            exc = st.number_input("🌟 'Excelente' (mínimo)", 0.0, float(scale), float(cur_th.get('excelente', 9.5)), step, key=f"{k}_exc")
        with t2:
            bien = st.number_input("👍 'Bien' (mínimo)", 0.0, float(scale), float(cur_th.get('bien', 8.0)), step, key=f"{k}_bien")
        with t3:
            reg = st.number_input("👌 'Regular' (mínimo)", 0.0, float(scale), float(cur_th.get('regular', 6.0)), step, key=f"{k}_reg")
        th = {'excelente': exc, 'bien': bien, 'regular': reg, 'en_riesgo': reg}
        if not (exc >= bien >= reg):
            st.warning("⚠️ Los umbrales deben ir de mayor a menor: Excelente ≥ Bien ≥ Regular.")
    else:
        st.caption("La clasificación (Excelente, Bien, Regular) se define para todo el semestre del grupo.")

    b1, b2 = st.columns(2)
    with b1:
        label = f"💾 Guardar criterios de {grupo}" + (f" ({parcial})" if parcial else "")
        if st.button(label, type="primary", width='stretch', disabled=(total != 100), key=f"{k}_save"):
            g = grupos.get(grupo) or {}
            values = {'peso_khan': float(peso), 'componentes': {c: float(v) for c, v in comp.items()}}
            if parcial is None:
                g.update(values)
                g['thresholds'] = th
            else:
                if 'peso_khan' not in g:
                    # Primer acuerdo del grupo solo para un parcial: el resto del semestre sigue con los generales
                    base_view = khan_view_config({k2: v for k2, v in criterios.items() if k2 != 'grupos'})
                    g.update({'peso_khan': khan_weight(base_view), 'componentes': dict(base_view.get('componentes') or {}),
                              'thresholds': base_view.get('thresholds')})
                g.setdefault('parciales', {})[parcial] = values
            grupos[grupo] = g
            try:
                level, message = save_teacher_criterios(folder_id, {**criterios, 'criterios_por_grupo': True, 'grupos': grupos})
            except Exception as e:
                level, message = 'error', f"No se pudieron guardar los criterios de {grupo}: {e}"
            set_flash(level, message if level != 'success' else f"✅ Criterios de {grupo} guardados" + (f" para {parcial}." if parcial else "."))
            st.rerun()
    with b2:
        can_reset = bool(over) and (parcial is None or over['del_parcial'])
        reset_label = f"↩️ Quitar lo de {parcial}" if parcial else f"↩️ {grupo} usa los criterios generales"
        if st.button(reset_label, width='stretch', disabled=not can_reset, key=f"{k}_reset"):
            if parcial:
                grupos[grupo].get('parciales', {}).pop(parcial, None)
            else:
                grupos.pop(grupo, None)
            level, message = save_teacher_criterios(folder_id, {**criterios, 'criterios_por_grupo': True, 'grupos': grupos})
            set_flash(level, message)
            st.rerun()

    st.markdown("###### Resumen de criterios por grupo y parcial")
    st.dataframe(_group_criteria_rows(criterios, groups), hide_index=True, width='stretch')



# ==============================================================================
# VISTA: INICIO DE SESIÓN CON ENRUTAMIENTO DINÁMICO (GOOGLE DRIVE)
# ==============================================================================
def render_login():
    st.markdown("""
    <div class="main-header" style="text-align: center;">
        <h1>📐 Portal de Calificaciones - CBTA 24</h1>
        <p>Centro de Bachillerato Tecnológico Agropecuario No. 24 | Control y Seguimiento de Khan Academy</p>
    </div>
    """, unsafe_allow_html=True)

    service = get_drive_service()
    drive_ready = (service is not None) and (not str(ROOT_FOLDER_ID).startswith('PEGA_AQUÍ'))

    if not drive_ready:
        st.warning(
            "⚠️ **Aviso de Integración con Google Drive:**\n\n"
            "- Define `ROOT_FOLDER_ID` con el ID de la carpeta compartida en `app.py`.\n"
            "- Configura `st.secrets['gcp_service_account']` con las credenciales JSON del Service Account.\n"
            "- *Modo de contingencia:* Si existen datos de prueba en la carpeta `datos/`, el sistema se ejecutará en modo local temporal."
        )

    # Cargar archivo maestro de docentes desde Drive
    docentes_df = load_docentes_master()
    # Si Drive falló (p. ej. tiempo de espera agotado), no conservar el resultado vacío
    # en caché durante una hora: el siguiente intento vuelve a consultar Drive.
    if docentes_df.empty:
        load_docentes_master.clear()

    col1, col2, col3 = st.columns([1, 2.4, 1])
    with col2:
        st.markdown("### Acceso al Portal")
        tab_student, tab_teacher = st.tabs(["🎓 Acceso Estudiantes", "🛡️ Acceso Docentes"])

        # ----------------------------------------------------------------------
        # 1. ACCESO ESTUDIANTES (AISLAMIENTO POR DOCENTE / ASIGNATURA)
        # ----------------------------------------------------------------------
        with tab_student:
            st.caption("Selecciona a tu docente e ingresa con tu **matrícula y PIN** (te los da tu docente) o con tu usuario y contraseña de Khan Academy:")

            # Opciones de docentes disponibles desde docentes.xlsx
            subject_docentes = docentes_df[docentes_df['carpeta_nombre'] != ''] if not docentes_df.empty else docentes_df
            if not subject_docentes.empty and 'Nombre del Docente' in subject_docentes.columns:
                # Solo quienes tienen una materia con carpeta (no los tutores o directivos sin grupo a cargo)
                available_teachers = sorted([t for t in subject_docentes['Nombre del Docente'].unique() if str(t).strip()])
            else:
                available_teachers = ["Docente General"]

            selected_teacher = st.selectbox(
                "👨‍🏫 Docente / Profesor:",
                options=available_teachers,
                key="student_teacher_selector"
            )

            # Filtrar las asignaturas que imparte el docente seleccionado
            teacher_df = subject_docentes[subject_docentes['Nombre del Docente'] == selected_teacher] if not subject_docentes.empty else pd.DataFrame()
            teacher_subjects = sorted([s for s in teacher_df['asignatura'].unique() if str(s).strip()]) if not teacher_df.empty else []

            # Si el docente imparte más de una materia, permitir elegirla; de lo contrario, auto-asignar
            if len(teacher_subjects) > 1:
                selected_asig = st.selectbox(
                    "📚 Materia / Asignatura:",
                    options=teacher_subjects,
                    key="student_asig_selector"
                )
            elif len(teacher_subjects) == 1:
                selected_asig = teacher_subjects[0]
                st.caption(f"📚 Materia asignada: **{selected_asig}**")
            else:
                selected_asig = "Temas Selectos de Matemáticas II"

            # Pre-resolver la subcarpeta y pre-cargar credenciales en memoria
            # para garantizar CERO llamadas a Google Drive API al presionar el botón
            matched_teacher_asig = teacher_df[teacher_df['asignatura'] == selected_asig] if not teacher_df.empty else pd.DataFrame()
            folder_name = matched_teacher_asig.iloc[0]['carpeta_nombre'] if not matched_teacher_asig.empty else ""
            cached_folder_id = get_cached_folder_id(folder_name) if folder_name else None
            if folder_name and not cached_folder_id:
                get_cached_folder_id.clear()
            cached_creds_df = load_teacher_credentials(cached_folder_id)
            if cached_creds_df.empty:
                load_teacher_credentials.clear()
            # Lista oficial con matrícula + PIN (precargada para no consultar Drive al presionar el botón)
            cached_roster = normalize_roster(load_teacher_table(cached_folder_id, ROSTER_FILE)) if (cached_folder_id or not drive_ready) else pd.DataFrame(columns=ROSTER_COLS)

            with st.form("student_login_form", clear_on_submit=False):
                username_input = st.text_input("Matrícula o usuario de Khan Academy", placeholder="ej. 24123456 o alboresclementepaulo", key="login_st_user").strip()
                password_input = st.text_input("PIN o contraseña", type="password", placeholder="••••••", key="login_st_pass").strip()
                submit_st_btn = st.form_submit_button("Ingresar como Estudiante", width='stretch', type="primary")

                if submit_st_btn:
                    # Debounce contra clics rápidos / spam del botón
                    now_ts = time.time()
                    last_click_ts = st.session_state.get('last_student_login_ts', 0)
                    if now_ts - last_click_ts < 0.5:
                        time.sleep(0.5)
                    st.session_state['last_student_login_ts'] = time.time()

                    lock_until = st.session_state.get('student_login_lock_until', 0)
                    if time.time() < lock_until:
                        st.error(f"Demasiados intentos. Espera {int(lock_until - time.time()) + 1} segundos e inténtalo de nuevo.")
                    elif not username_input or not password_input:
                        st.error("Por favor completa tu usuario y contraseña.")
                    elif cached_creds_df.empty and cached_roster.empty:
                        st.error(f"No se encontraron credenciales para la asignatura '{selected_asig}' del docente '{selected_teacher}'. Contacta al docente.")
                    else:
                        # Autenticación estrictamente en memoria contra los datos ya cargados en RAM
                        login = None
                        if not cached_creds_df.empty:
                            matched = cached_creds_df[
                                (cached_creds_df['Usuario'].str.lower() == username_input.lower()) &
                                (cached_creds_df['Contraseña'] == password_input)
                            ]
                            if not matched.empty:
                                login = {'student_name': matched.iloc[0]['Nombre del estudiante'], 'student_id': None}
                        if login is None and not cached_roster.empty:
                            ids = cached_roster.apply(roster_login_id, axis=1).str.strip().str.upper()
                            matched = cached_roster[(ids == username_input.upper()) & (cached_roster['PIN'] != '') &
                                                    (cached_roster['PIN'] == password_input)]
                            if not matched.empty:
                                login = {'student_name': matched.iloc[0]['Nombre'], 'student_id': matched.iloc[0]['ID']}

                        if login:
                            teacher_email = matched_teacher_asig.iloc[0].get('e_mail', '') if not matched_teacher_asig.empty else ''
                            st.session_state.pop('student_login_failures', None)
                            st.session_state['logged_in'] = True
                            st.session_state['role'] = 'student'
                            st.session_state['username'] = username_input
                            st.session_state['student_name'] = login['student_name']
                            st.session_state['student_id'] = login['student_id']
                            st.session_state['teacher_name'] = selected_teacher
                            st.session_state['teacher_email'] = teacher_email
                            st.session_state['asignatura'] = selected_asig
                            st.session_state['carpeta_nombre'] = folder_name
                            st.session_state['teacher_folder_id'] = cached_folder_id
                            st.success(f"Bienvenido(a), {login['student_name']}")
                            st.rerun()
                        else:
                            fails = st.session_state.get('student_login_failures', 0) + 1
                            st.session_state['student_login_failures'] = fails
                            if fails >= 5:
                                st.session_state['student_login_lock_until'] = time.time() + 60
                                st.session_state['student_login_failures'] = 0
                            st.error(f"Usuario o contraseña incorrectos para el docente '{selected_teacher}'.")

        # ----------------------------------------------------------------------
        # 2. ACCESO DOCENTES (ENRUTAMIENTO MAESTRO)
        # ----------------------------------------------------------------------
        with tab_teacher:
            st.caption("Ingresa con tu usuario y contraseña de docente registrados en docentes.xlsx:")

            with st.form("teacher_login_form", clear_on_submit=False):
                doc_user_input = st.text_input("Usuario Docente", placeholder="ej. docente_tsm", key="login_doc_user").strip()
                doc_pass_input = st.text_input("Contraseña", type="password", placeholder="••••••••", key="login_doc_pass").strip()
                submit_doc_btn = st.form_submit_button("Ingresar al Panel Docente", width='stretch', type="primary")

                if submit_doc_btn:
                    # Debounce contra clics repetidos
                    now_ts = time.time()
                    last_click_ts = st.session_state.get('last_teacher_login_ts', 0)
                    if now_ts - last_click_ts < 0.5:
                        time.sleep(0.5)
                    st.session_state['last_teacher_login_ts'] = time.time()

                    if not doc_user_input or not doc_pass_input:
                        st.error("Por favor completa ambos campos.")
                    else:
                        matched_doc = pd.DataFrame()
                        if not docentes_df.empty:
                            matched_doc = docentes_df[
                                (docentes_df['usuario_docente'].str.lower() == doc_user_input.lower()) &
                                (docentes_df['password'] == doc_pass_input)
                            ]

                        # Tutor(a) académico(a), orientación o subdirección: se unen los grupos de todas sus filas
                        tutor_groups = []
                        if not matched_doc.empty:
                            for _, r in matched_doc.iterrows():
                                if r['rol'] in ('tutor', 'tutora', 'directivo', 'directiva', 'orientacion', 'orientación', 'subdireccion', 'subdirección'):
                                    g = parse_tutor_groups(r['grupos_tutoria']) or ['*']
                                    tutor_groups = ['*'] if '*' in g or tutor_groups == ['*'] else sorted(set(tutor_groups) | set(g))
                            with_subject = matched_doc[matched_doc['carpeta_nombre'] != '']
                            if with_subject.empty and tutor_groups:
                                doc_row = matched_doc.iloc[0]
                                st.session_state['logged_in'] = True
                                st.session_state['role'] = 'tutor'
                                st.session_state['username'] = doc_row['usuario_docente']
                                st.session_state['teacher_name'] = doc_row['Nombre del Docente']
                                st.session_state['tutor_groups'] = tutor_groups
                                st.rerun()
                            if not with_subject.empty:
                                matched_doc = with_subject

                        if not matched_doc.empty:
                            doc_row = matched_doc.iloc[0]
                            st.session_state['tutor_groups'] = tutor_groups
                            folder_name = doc_row['carpeta_nombre']
                            asig_name = doc_row['asignatura']
                            teacher_full_name = doc_row.get('Nombre del Docente', doc_row['usuario_docente'])
                            teacher_email = doc_row.get('e_mail', '')
                            folder_id = get_cached_folder_id(folder_name) if folder_name else None

                            st.session_state['logged_in'] = True
                            st.session_state['role'] = 'admin'
                            st.session_state['username'] = doc_row['usuario_docente']
                            st.session_state['teacher_name'] = teacher_full_name
                            st.session_state['teacher_email'] = teacher_email
                            st.session_state['student_name'] = f"Prof. {teacher_full_name}"
                            st.session_state['asignatura'] = asig_name
                            st.session_state['carpeta_nombre'] = folder_name
                            st.session_state['teacher_folder_id'] = folder_id
                            st.success(f"Bienvenido(a), {teacher_full_name}")
                            st.rerun()

                        elif ADMIN_USERNAME and ADMIN_PASSWORD and doc_user_input == ADMIN_USERNAME and doc_pass_input == ADMIN_PASSWORD:
                            st.session_state['logged_in'] = True
                            st.session_state['role'] = 'admin'
                            st.session_state['username'] = ADMIN_USERNAME
                            st.session_state['teacher_name'] = "Administrador General"
                            st.session_state['teacher_email'] = ""
                            st.session_state['student_name'] = "Profesor / Administrador General"
                            st.session_state['asignatura'] = "Temas Selectos de Matemáticas II"
                            st.session_state['carpeta_nombre'] = "datos (Local)"
                            st.session_state['teacher_folder_id'] = None
                            st.success("Acceso concedido como Administrador Maestro.")
                            st.rerun()

                        elif docentes_df.empty and drive_ready:
                            st.error("No se pudo cargar la lista de docentes desde Google Drive. Espera unos segundos y vuelve a intentarlo.")
                        else:
                            st.error("Credenciales de docente no válidas.")

        st.info("💡 **Estudiantes:** Seleccionen a su docente e inicien sesión con su usuario y contraseña de Khan Academy.\n\n"
                "🛡️ **Docentes:** Inicien sesión con sus credenciales maestras.")


# ==============================================================================
# VISTA: PANEL DE ADMINISTRADOR / DOCENTE
# ==============================================================================
NAV_INICIO, NAV_LISTA, NAV_EVAL, NAV_CALIF, NAV_ALUMNO, NAV_AJUSTES = (
    "🏠 Inicio", "🙋 Pase de lista", "📓 Evaluar", "📊 Calificaciones", "🔍 Alumno", "⚙️ Ajustes")
NAV_TUTORIA = "🧭 Tutoría"
ADMIN_SECTIONS = [NAV_INICIO, NAV_LISTA, NAV_EVAL, NAV_CALIF, NAV_ALUMNO, NAV_AJUSTES]
AJ_INICIO, AJ_CRITERIOS, AJ_ALUMNOS, AJ_TEMAS, AJ_ARCHIVOS = ("🚀 Primeros pasos", "Criterios y componentes", "👥 Alumnos y cuentas",
                                                         "📚 Temas", "☁️ Archivos y Drive")
CALIF_CONC, CALIF_FINAL, CALIF_ACT, CALIF_TEMAS = "Concentrado Khan", "Calificación del parcial", "Por actividad", "Por tema"


def render_admin():
    teacher_folder_id = st.session_state.get('teacher_folder_id')
    asignatura = st.session_state.get('asignatura', 'Temas Selectos de Matemáticas II')
    carpeta_nombre = st.session_state.get('carpeta_nombre', 'Google Drive')

    teacher_name = st.session_state.get('teacher_name', st.session_state.get('username', 'Profesor'))
    teacher_email = st.session_state.get('teacher_email', '')
    if not teacher_email:
        docentes_df = load_docentes_master()
        if not docentes_df.empty and 'usuario_docente' in docentes_df.columns:
            m = docentes_df[docentes_df['usuario_docente'].str.lower() == str(st.session_state.get('username', '')).lower()]
            if not m.empty:
                teacher_email = m.iloc[0].get('e_mail', '')
                st.session_state['teacher_email'] = teacher_email

    email_display = f" | Correo: <code>{html.escape(str(teacher_email))}</code>" if teacher_email else ""
    header_col1, header_col2 = st.columns([5, 1])
    with header_col1:
        st.markdown(f"""
        <div class="main-header" style="background: linear-gradient(135deg, #0f172a 0%, #334155 100%);">
            <h1>🛡️ Panel Docente - {html.escape(str(asignatura))}</h1>
            <p>Docente: <strong>{html.escape(str(teacher_name))}</strong>{email_display} | Carpeta Drive: <code>{html.escape(str(carpeta_nombre))}</code> | Sincronización en memoria</p>
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", width='stretch'):
            st.session_state.clear()
            st.rerun()

    show_flash()

    # Navegación por secciones (en lugar de pestañas): solo se dibuja la sección elegida,
    # lo que la hace más rápida y cómoda en el celular.
    tutor_groups = st.session_state.get('tutor_groups') or []
    sections = ADMIN_SECTIONS[:-1] + [NAV_TUTORIA, NAV_AJUSTES] if tutor_groups else ADMIN_SECTIONS
    section = st.segmented_control("Sección", sections, default=NAV_INICIO, key="admin_section",
                                   label_visibility="collapsed") or NAV_INICIO
    if section == NAV_TUTORIA:
        render_tutoria(tutor_groups)
        return
    ajustes_sub = None
    if section == NAV_AJUSTES:
        ajustes_sub = st.segmented_control("Ajustes", [AJ_INICIO, AJ_CRITERIOS, AJ_ALUMNOS, AJ_TEMAS, AJ_ARCHIVOS], default=AJ_INICIO,
                                           key="ajustes_sub", label_visibility="collapsed") or AJ_INICIO

    # Cargar datos base crudos aislados de la carpeta del docente
    raw_khan = load_teacher_raw_assignments(teacher_folder_id)
    all_credentials = load_teacher_credentials(teacher_folder_id)
    # Lista oficial: une cuentas duplicadas y usa el nombre oficial de cada alumno
    roster, roster_links = load_roster_and_links(teacher_folder_id)
    raw_assignments = apply_roster_links(raw_khan, roster, roster_links)

    # Detectar dinámicamente los tipos de tarea presentes en los datos
    if not raw_assignments.empty and 'Tipo de tarea' in raw_assignments.columns:
        unique_task_types = sorted([
            t for t in raw_assignments['Tipo de tarea'].dropna().astype(str).str.strip().unique()
            if t
        ])
    else:
        unique_task_types = ['Video', 'Ejercicio', 'Artículo']

    # Cargar configuración persistente e independiente del docente desde Google Drive (criterios.json)
    criterios_data = load_teacher_criterios(teacher_folder_id, unique_task_types)
    active_scale = int(criterios_data.get('escala_maxima', 10))
    active_peso = float(criterios_data.get('peso_khan', 100))
    active_thresholds = criterios_data.get('thresholds', {})
    saved_task_criteria = criterios_data.get('task_criteria', {})
    saved_parcial_dates = parse_parciales_dates(criterios_data.get('parciales', {}))

    # --------------------------------------------------------------------------
    # SECCIÓN 1: CONFIGURACIONES (CRITERIOS, PARCIALES Y CARGA DE ARCHIVOS)
    # --------------------------------------------------------------------------
    show_config = section == NAV_AJUSTES and ajustes_sub == AJ_CRITERIOS
    if show_config:
        st.caption("Configura de forma persistente e independiente para tu materia la escala máxima, el peso de Khan Academy, los periodos de parciales, los umbrales de rendimiento y los criterios por actividad en tu Google Drive.")

        tab_gral, tab_parciales, tab_tasks, tab_comp, tab_grupos = st.tabs(["🎯 Escala, Peso y Clasificación", "📅 Fechas de Parciales", "📌 Criterios por Tipo de Tarea", "🧮 Componentes y asistencia", "👥 Por grupo"])
        per_group_on = bool(criterios_data.get('criterios_por_grupo'))
        general_note = ("👥 Tienes activados los **criterios por grupo**: estos valores son los **generales**, que se usan en los "
                        "grupos a los que no les hayas definido criterios propios (pestaña **👥 Por grupo**).")

        with tab_grupos:
            config_groups = sorted({g for g in list(raw_assignments['Grupo'].dropna().unique() if not raw_assignments.empty else [])
                                    + list(roster['Grupo'].unique() if not roster.empty else []) if g})
            render_group_criteria(teacher_folder_id, criterios_data, config_groups)

        with tab_gral:
            if per_group_on:
                st.info(general_note)
            st.markdown("##### 📏 Escala de Calificación y Ponderación")
            cg1, cg2 = st.columns(2)
            with cg1:
                sel_scale = st.radio(
                    "Escala Máxima:",
                    options=[10, 100],
                    index=0 if active_scale == 10 else 1,
                    horizontal=True,
                    help="Define si la escala final de evaluación es de 0 a 10 o de 0 a 100.",
                    key="cfg_escala_maxima"
                )
            with cg2:
                sel_peso = st.slider(
                    "Ponderación de Khan Academy (%):",
                    min_value=0,
                    max_value=100,
                    value=int(active_peso),
                    step=5,
                    help="Porcentaje con el que las tareas de Khan Academy contribuyen a la calificación final (ej. si es 80%, la calificación máxima en Khan Academy es el 80% de la escala).",
                    key="cfg_peso_khan"
                )

            perfect_khan_score = round(sel_scale * (sel_peso / 100.0), 1)
            st.info(f"💡 **Cálculo de Ponderación:** Con una escala de **{sel_scale}** y peso del **{sel_peso}%**, un alumno con puntaje perfecto (100%) en Khan Academy obtendrá **{perfect_khan_score:.1f} / {sel_scale}**.")

            st.markdown("---")
            st.markdown("##### 🏆 Clasificación de Rendimiento Académico (Umbrales)")
            st.caption("Define el puntaje mínimo o de corte para clasificar a los estudiantes en el concentrado:")

            th_defaults = get_default_teacher_criterios(scale=sel_scale)['thresholds']
            cur_th = active_thresholds if active_thresholds else th_defaults

            def_exc = float(cur_th.get('excelente', th_defaults['excelente']))
            def_bien = float(cur_th.get('bien', th_defaults['bien']))
            def_reg = float(cur_th.get('regular', th_defaults['regular']))

            if sel_scale == 100 and def_exc <= 10.0:
                def_exc, def_bien, def_reg = 95.0, 80.0, 60.0
            elif sel_scale == 10 and def_exc > 10.0:
                def_exc, def_bien, def_reg = 9.5, 8.0, 6.0

            u_col1, u_col2, u_col3 = st.columns(3)
            with u_col1:
                th_input_exc = st.number_input(
                    "🌟 'Excelente' (Mínimo)",
                    min_value=0.0,
                    max_value=float(sel_scale),
                    value=def_exc,
                    step=0.5 if sel_scale == 10 else 1.0,
                    key=f"th_exc_{sel_scale}"
                )
            with u_col2:
                th_input_bien = st.number_input(
                    "👍 'Bien' (Mínimo)",
                    min_value=0.0,
                    max_value=float(sel_scale),
                    value=def_bien,
                    step=0.5 if sel_scale == 10 else 1.0,
                    key=f"th_bien_{sel_scale}"
                )
            with u_col3:
                th_input_reg = st.number_input(
                    "👌 'Regular' (Mínimo)",
                    min_value=0.0,
                    max_value=float(sel_scale),
                    value=def_reg,
                    step=0.5 if sel_scale == 10 else 1.0,
                    key=f"th_reg_{sel_scale}"
                )
            st.caption(f"🚨 **En riesgo:** promedio menor a {th_input_reg:g} (el mínimo de 'Regular').")
            if not (th_input_exc >= th_input_bien >= th_input_reg):
                st.warning("⚠️ Los umbrales deben ir de mayor a menor: Excelente ≥ Bien ≥ Regular.")

        with tab_parciales:
            st.markdown("##### 📅 Periodos de Calificación por Parcial")
            st.caption("Define el rango de fechas de entrega de Khan Academy que corresponden a cada Parcial:")

            p_col1, p_col2 = st.columns(2)
            with p_col1:
                st.markdown("###### Fechas de Inicio")
                p1_start = st.date_input(
                    "Inicio Parcial 1",
                    value=saved_parcial_dates['Parcial 1']['start'],
                    key="cfg_p1_start"
                )
                p2_start = st.date_input(
                    "Inicio Parcial 2",
                    value=saved_parcial_dates['Parcial 2']['start'],
                    key="cfg_p2_start"
                )
                p3_start = st.date_input(
                    "Inicio Parcial 3",
                    value=saved_parcial_dates['Parcial 3']['start'],
                    key="cfg_p3_start"
                )
            with p_col2:
                st.markdown("###### Fechas de Fin")
                p1_end = st.date_input(
                    "Fin Parcial 1",
                    value=saved_parcial_dates['Parcial 1']['end'],
                    key="cfg_p1_end"
                )
                p2_end = st.date_input(
                    "Fin Parcial 2",
                    value=saved_parcial_dates['Parcial 2']['end'],
                    key="cfg_p2_end"
                )
                p3_end = st.date_input(
                    "Fin Parcial 3",
                    value=saved_parcial_dates['Parcial 3']['end'],
                    key="cfg_p3_end"
                )

            parcial_ranges = [('Parcial 1', p1_start, p1_end), ('Parcial 2', p2_start, p2_end), ('Parcial 3', p3_start, p3_end)]
            parcial_issues = [f"**{n}** termina antes de iniciar" for n, a, b in parcial_ranges if a > b]
            for (n1, _, e1), (n2, s2, _) in zip(parcial_ranges, parcial_ranges[1:]):
                if s2 <= e1:
                    parcial_issues.append(f"**{n2}** inicia antes de que termine **{n1}** (las fechas se traslapan)")
            if parcial_issues:
                st.warning("⚠️ Revisa las fechas: " + "; ".join(parcial_issues) + ".")

        with tab_comp:
            st.markdown("##### 🧮 Componentes de la calificación del parcial")
            if per_group_on:
                st.info(general_note)
            st.caption("Además de Khan Academy, puedes evaluar otros componentes. Los pesos deben sumar 100%. "
                       "Deja en 0% los que no uses. Las evidencias, el examen, el producto y la asistencia se registran "
                       "en las secciones **🙋 Pase de lista** y **📓 Evaluar** (requiere tu lista oficial de alumnos).")
            saved_comp = {**DEFAULT_COMPONENTES, **(criterios_data.get('componentes') or {})}
            comp_values = {}
            cc = st.columns(len(COMPONENTES))
            for col, (ckey, clabel) in zip(cc, COMPONENTES):
                with col:
                    comp_values[ckey] = st.number_input(f"{clabel} (%)", min_value=0, max_value=100, step=5,
                                                        value=int(float(saved_comp.get(ckey, 0))), key=f"cfg_comp_{ckey}")
            total_w = sel_peso + sum(comp_values.values())
            parts = [f"Khan {sel_peso}%"] + [f"{lbl.split(' ', 1)[1]} {comp_values[k]}%" for k, lbl in COMPONENTES if comp_values[k]]
            if total_w == 100:
                st.success("✅ " + " + ".join(parts) + " = 100%")
            else:
                st.warning("⚠️ " + " + ".join(parts) + f" = **{total_w}%**. Ajusta los pesos (incluido el de Khan, en la primera pestaña) para que sumen 100%.")
            st.markdown("---")
            sel_asist_min = st.number_input(
                "🙋 Asistencia mínima requerida (%)", min_value=0, max_value=100, step=5,
                value=int(float(criterios_data.get('asistencia_minima', 80))), key="cfg_asist_min",
                help="Se avisa al docente y al alumno cuando su asistencia está por debajo de este porcentaje o cerca de él."
            )
            st.markdown("---")
            st.markdown("##### 📏 Rúbrica de los sellos de evidencia")
            st.caption("Ajusta la descripción y el valor de cada nivel. Tus alumnos ven esta misma rúbrica en su portal. "
                       "Los nombres de los niveles no cambian para no afectar los sellos ya registrados.")
            rub_df = pd.DataFrame([{'Nivel': l, 'Valor (%)': p, 'Descripción': d} for l, p, d in evid_levels(criterios_data)])
            rub_edit = st.data_editor(
                rub_df, hide_index=True, width='stretch', disabled=['Nivel'], key="cfg_rubrica_editor",
                column_config={'Nivel': st.column_config.TextColumn(width="small"),
                               'Valor (%)': st.column_config.NumberColumn(min_value=0, max_value=100, step=5, required=True, width="small"),
                               'Descripción': st.column_config.TextColumn(width="large", required=True)}
            )
            rubrica_values = [{'nivel': r['Nivel'], 'valor': float(r['Valor (%)']), 'descripcion': str(r['Descripción']).strip()}
                              for _, r in rub_edit.iterrows()]
            vals = [r['valor'] for r in rubrica_values]
            if any(b < a for a, b in zip(vals, vals[1:])):
                st.warning("⚠️ Los valores deberían ir de menor a mayor (No presentó ≤ En proceso ≤ Suficiente ≤ Dominio).")

        with tab_tasks:
            st.markdown("##### 📌 Criterios de Calificación por Tipo de Tarea")
            current_task_criteria = {}
            for t_idx, task_type in enumerate(unique_task_types):
                cfg_t = saved_task_criteria.get(task_type, {})
                st.markdown(f"###### Actividad: `{task_type}`")
                c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 2, 1.8, 1.8])
                with c1:
                    v_tiempo = st.number_input(
                        "Valor a tiempo",
                        min_value=0.0,
                        value=float(cfg_t.get('valor_a_tiempo', 1.0)),
                        step=0.5,
                        key=f"crit_ot_{task_type}"
                    )
                with c2:
                    v_tardio = st.number_input(
                        "Valor tardío",
                        min_value=0.0,
                        value=float(cfg_t.get('valor_tardio', 0.1)),
                        step=0.05,
                        key=f"crit_lt_{task_type}"
                    )
                with c3:
                    st.write("")
                    st.write("")
                    mult = st.checkbox(
                        "Multiplicar por aciertos",
                        value=bool(cfg_t.get('multiplicar_por_aciertos', False)),
                        key=f"crit_mult_{task_type}",
                        help="Si se activa, el valor base se multiplica por las preguntas correctas. Si no, es un puntaje fijo (ej. videos o lecturas)."
                    )
                with c4:
                    st.write("")
                    st.write("")
                    eval_int = st.checkbox(
                        "Evaluar intentos",
                        value=bool(cfg_t.get('evaluar_intentos', False)),
                        key=f"crit_eval_int_{task_type}",
                        help="Si se activa, se penalizan los intentos que excedan el límite configurado."
                    )
                with c5:
                    max_int = st.number_input(
                        "Máx. intentos libres",
                        min_value=1,
                        max_value=10,
                        value=int(cfg_t.get('max_intentos', 3)),
                        step=1,
                        disabled=not eval_int,
                        key=f"crit_max_int_{task_type}",
                        help="Intentos libres permitidos. Cada intento adicional resta 1 acierto. Si es tardía y supera este límite, la nota es 0."
                    )

                current_task_criteria[task_type] = {
                    'valor_a_tiempo': v_tiempo,
                    'valor_tardio': v_tardio,
                    'multiplicar_por_aciertos': mult,
                    'evaluar_intentos': eval_int,
                    'max_intentos': max_int
                }
                if t_idx < len(unique_task_types) - 1:
                    st.divider()

        st.write("")
        b_col1, b_col2, _ = st.columns([2.5, 2.2, 2.5])
        with b_col1:
            if st.button("💾 Guardar Configuración en Google Drive", type="primary", width='stretch', key="save_teacher_crit_btn"):
                # 1. Crear explícitamente el diccionario de configuración con todos los ajustes
                updated_criterios = {
                    'escala_maxima': int(sel_scale),
                    'peso_khan': float(sel_peso),
                    'thresholds': {
                        'excelente': float(th_input_exc),
                        'bien': float(th_input_bien),
                        'regular': float(th_input_reg),
                        'en_riesgo': float(th_input_reg)
                    },
                    'parciales': {
                        'Parcial 1': {
                            'start': p1_start.isoformat() if hasattr(p1_start, 'isoformat') else str(p1_start),
                            'end': p1_end.isoformat() if hasattr(p1_end, 'isoformat') else str(p1_end)
                        },
                        'Parcial 2': {
                            'start': p2_start.isoformat() if hasattr(p2_start, 'isoformat') else str(p2_start),
                            'end': p2_end.isoformat() if hasattr(p2_end, 'isoformat') else str(p2_end)
                        },
                        'Parcial 3': {
                            'start': p3_start.isoformat() if hasattr(p3_start, 'isoformat') else str(p3_start),
                            'end': p3_end.isoformat() if hasattr(p3_end, 'isoformat') else str(p3_end)
                        }
                    },
                    'task_criteria': current_task_criteria,
                    'componentes': {k: float(v) for k, v in comp_values.items()},
                    'asistencia_minima': float(sel_asist_min),
                    'rubrica_evidencias': rubrica_values,
                    # Los criterios por grupo se editan en su propia pestaña; aquí se conservan tal cual
                    'criterios_por_grupo': bool(criterios_data.get('criterios_por_grupo', False)),
                    'grupos': criterios_data.get('grupos') or {}
                }

                level, message = save_teacher_criterios(teacher_folder_id, updated_criterios)
                reset_config_widgets()
                set_flash(level, message)
                st.rerun()

        with b_col2:
            if st.button("🔄 Restablecer Predeterminados", width='stretch', key="reset_teacher_crit_btn"):
                def_crit = get_default_teacher_criterios(unique_task_types, scale=sel_scale)
                # Los criterios acordados con cada grupo no se borran al restablecer los generales
                def_crit['criterios_por_grupo'] = bool(criterios_data.get('criterios_por_grupo', False))
                def_crit['grupos'] = criterios_data.get('grupos') or {}
                level, message = save_teacher_criterios(teacher_folder_id, def_crit)
                reset_config_widgets()
                if level == 'success':
                    level, message = 'info', "Configuración restablecida a los valores predeterminados."
                set_flash(level, message)
                st.rerun()

    else:
        # Sin el formulario de configuración a la vista, se usan los valores guardados
        sel_scale = active_scale
        sel_peso = int(active_peso)
        th_defaults = get_default_teacher_criterios(scale=sel_scale)['thresholds']
        cur_th = active_thresholds if active_thresholds else th_defaults
        th_input_exc = float(cur_th.get('excelente', th_defaults['excelente']))
        th_input_bien = float(cur_th.get('bien', th_defaults['bien']))
        th_input_reg = float(cur_th.get('regular', th_defaults['regular']))
        p1_start, p1_end = saved_parcial_dates['Parcial 1']['start'], saved_parcial_dates['Parcial 1']['end']
        p2_start, p2_end = saved_parcial_dates['Parcial 2']['start'], saved_parcial_dates['Parcial 2']['end']
        p3_start, p3_end = saved_parcial_dates['Parcial 3']['start'], saved_parcial_dates['Parcial 3']['end']
        current_task_criteria = {t: saved_task_criteria.get(t, get_default_criteria_config([t])[t]) for t in unique_task_types}
        comp_values = {k: float(v) for k, v in {**DEFAULT_COMPONENTES, **(criterios_data.get('componentes') or {})}.items()}
        sel_asist_min = float(criterios_data.get('asistencia_minima', 80))
        rubrica_values = criterios_data.get('rubrica_evidencias') or default_rubrica()

    show_files = (section == NAV_AJUSTES and ajustes_sub == AJ_ARCHIVOS) or (raw_khan.empty and section == NAV_INICIO)
    if show_files:
        st.markdown(f"**Carpeta asignada en Google Drive:** `📁 {carpeta_nombre}`")
        if teacher_email:
            st.markdown(f"**Acceso exclusivo asignado a:** `📧 {teacher_email}`")

        if teacher_folder_id:
            drive_folder_url = f"https://drive.google.com/drive/folders/{teacher_folder_id}"
            st.success("🟢 Conexión activa con Google Drive (Lectura en memoria sin almacenamiento en disco).")
            st.link_button(f"📂 Abrir Carpeta '{carpeta_nombre}' en Google Drive", drive_folder_url, width='stretch')
        else:
            drive_folder_url = "https://drive.google.com"
            st.info("ℹ️ Sesión en modo local/administrador general.")

        if st.button("🔄 Sincronizar / Refrescar Datos de Google Drive", width='stretch', type="primary", key="admin_refresh_drive_btn"):
            st.cache_data.clear()
            set_flash('success', "✅ Datos sincronizados directamente desde Google Drive.")
            st.rerun()

        st.markdown("---")
        st.markdown("##### 📋 Instrucciones para Actualizar Datos en Google Drive")
        st.markdown(f"""
        1. **Tareas de Khan Academy:** Descarga los reportes CSV desde Khan Academy y colócalos directamente dentro de tu carpeta **[{carpeta_nombre}]({drive_folder_url})** en Google Drive.
        2. **Credenciales de Alumnos:** Guarda tu archivo **`credenciales.xlsx`** dentro de la misma carpeta.
        3. **Sincronización:** Una vez copiados tus archivos en Google Drive, presiona el botón **'🔄 Sincronizar / Refrescar Datos de Google Drive'** de arriba para recalcular el concentrado y el drill-down al instante.
        """)

        if teacher_email:
            st.info(f"🔒 **Seguridad y Acceso Restringido:** El enlace anterior conduce de forma directa a tu carpeta. Solo la cuenta de Google registrada (**{teacher_email}**) tiene permisos para acceder y editar los documentos de esta carpeta. Cualquier otra persona que intente abrir este enlace tendrá el acceso denegado por Google Drive.")

        st.markdown("---")
        st.markdown("##### 📤 Subir Archivo al Sistema (CSV de Khan Academy o credenciales.xlsx)")
        uploaded_file = st.file_uploader(
            "Selecciona un reporte CSV de Khan Academy o un archivo credenciales.xlsx:",
            type=["csv", "xlsx"],
            key="admin_upload_drive_file"
        )
        if uploaded_file is not None:
            if st.button(f"⬆️ Subir '{uploaded_file.name}'", type="primary", width='stretch', key="admin_btn_process_upload"):
                upload_success = False
                service = get_drive_service()
                if teacher_folder_id and service:
                    try:
                        media = MediaIoBaseUpload(io.BytesIO(uploaded_file.getvalue()), mimetype=uploaded_file.type or 'application/octet-stream', resumable=True)
                        # Si ya existe un archivo con el mismo nombre se reemplaza (evita duplicados)
                        existing = find_drive_item(service, uploaded_file.name, teacher_folder_id, is_folder=False)
                        if existing:
                            service.files().update(fileId=existing['id'], media_body=media, supportsAllDrives=True).execute()
                        else:
                            file_metadata = {
                                'name': uploaded_file.name,
                                'parents': [teacher_folder_id]
                            }
                            service.files().create(body=file_metadata, media_body=media, supportsAllDrives=True).execute()
                        upload_success = True
                    except HttpError as e:
                        if 'storage quota' in str(e).lower() or (getattr(e, 'resp', None) and e.resp.status == 403):
                            st.warning(f"⚠️ Tu cuenta de Google Drive no permite subir directamente vía API por cuota de Service Account institucional. Por favor, coloca el archivo en tu carpeta de Drive usando el botón **'📂 Abrir Carpeta en Google Drive'** y luego presiona **'🔄 Sincronizar'**.")
                        elif getattr(e, 'resp', None) and e.resp.status in [429, 500, 503]:
                            st.error("⚠️ El servidor está experimentando alto tráfico. Por favor, recarga la página en unos segundos.")
                        else:
                            st.error(f"Error al subir a Google Drive: {e}")
                    except Exception as e:
                        st.error(f"Error de conexión al subir a Google Drive: {e}")
                else:
                    try:
                        os.makedirs(DATA_DIR, exist_ok=True)
                        dest_path = os.path.join(DATA_DIR, uploaded_file.name)
                        with open(dest_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                        upload_success = True
                    except Exception as e:
                        st.error(f"Error al guardar archivo localmente: {e}")

                if upload_success:
                    st.cache_data.clear()
                    destino = "Google Drive" if (teacher_folder_id and service) else "la carpeta local `datos/`"
                    set_flash('success', f"✅ Archivo '{uploaded_file.name}' subido exitosamente a {destino}.")
                    st.rerun()

        st.markdown("---")
        st.markdown("##### 📥 Plantilla de Credenciales (`credenciales.xlsx`)")
        st.caption("Descarga la plantilla de Excel oficial con el formato exacto requerido por el sistema:")

        template_bytes = generate_credentials_template_bytes()
        st.download_button(
            label="📥 Descargar Plantilla credenciales.xlsx",
            data=template_bytes,
            file_name="credenciales.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
            key="dl_cred_template_btn"
        )

        with st.popover("👁️ Ver columnas y formato requerido para credenciales"):
            st.markdown("""
            El archivo debe llamarse **`credenciales.xlsx`** y contener exactamente las siguientes 3 columnas en la primera fila:

            | Usuario | Contraseña | Nombre del estudiante |
            | :--- | :--- | :--- |
            | `alboresclementepaulo` | `Alumno2026*` | `ALBORES CLEMENTE PAULO CESAR` |
            | `gonzalezmartinezmaria` | `Alumno2026*` | `GONZÁLEZ MARTÍNEZ MARÍA FERNANDA` |
            | `hernandezlopezjuan` | `Alumno2026*` | `HERNÁNDEZ LÓPEZ JUAN PABLO` |

            > 💡 **Nota Importante:** La columna **`Nombre del estudiante`** debe coincidir exactamente con el nombre con el que el alumno aparece registrado en los archivos CSV de Khan Academy para vincular su información correctamente.
            """)

    if section == NAV_AJUSTES:
        if ajustes_sub == AJ_ALUMNOS:
            render_roster_tab(teacher_folder_id, raw_khan, roster, roster_links, carpeta_nombre)
        elif ajustes_sub == AJ_INICIO:
            render_setup_section(teacher_folder_id, raw_khan, unique_task_types, carpeta_nombre)
        elif ajustes_sub == AJ_TEMAS:
            render_topics_setup(teacher_folder_id, raw_khan)
        return

    # Criterios activos completos en tiempo real
    active_criteria_config = {
        'escala_maxima': sel_scale,
        'peso_khan': sel_peso,
        'thresholds': {
            'excelente': th_input_exc,
            'bien': th_input_bien,
            'regular': th_input_reg,
            'en_riesgo': th_input_reg
        },
        'parciales': {
            'Parcial 1': {'start': p1_start, 'end': p1_end},
            'Parcial 2': {'start': p2_start, 'end': p2_end},
            'Parcial 3': {'start': p3_start, 'end': p3_end}
        },
        'task_criteria': current_task_criteria,
        'componentes': {k: float(v) for k, v in comp_values.items()},
        'asistencia_minima': float(sel_asist_min),
        'rubrica_evidencias': rubrica_values,
        'criterios_por_grupo': bool(criterios_data.get('criterios_por_grupo', False)),
        'grupos': criterios_data.get('grupos') or {}
    }
    active_criteria_config = khan_view_config(active_criteria_config)

    # El pase de lista no depende de los reportes de Khan
    if section == NAV_LISTA:
        render_attendance_section(teacher_folder_id, roster, active_criteria_config)
        return

    if raw_assignments.empty:
        st.warning(f"No hay reportes CSV de Khan Academy en la carpeta `{carpeta_nombre}`. Súbelos en **⚙️ Ajustes → ☁️ Archivos y Drive**.")
        return

    # Calificación dinámica en tiempo real según los criterios activos
    all_assignments = apply_dynamic_grading(raw_assignments.copy(), active_criteria_config)

    # CRÍTICO: Asignar Parciales vectorialmente comparando .dt.date contra datetime.date de la configuración activa
    assignments_tagged = assign_parciales_vectorized(all_assignments.copy(), active_criteria_config)


    # Grupos disponibles
    available_groups = sorted([g for g in assignments_tagged['Grupo'].dropna().unique() if g])

    # Controles del Master Dashboard
    if section in (NAV_INICIO, NAV_CALIF, NAV_ALUMNO):
        f_col1, f_col2 = st.columns([3, 2])

        with f_col1:
            selected_groups = st.multiselect(
                "Filtrar por Grupo(s):",
                options=available_groups,
                default=available_groups,
                help="Selecciona uno o varios grupos para visualizarlos en el concentrado."
            )

        with f_col2:
            p_filter_opts = ["Todos los Parciales", "Parcial 1", "Parcial 2", "Parcial 3", "Sin asignar"]
            p_now = current_parcial(active_criteria_config)
            has_now = (assignments_tagged['Parcial'] == p_now).any() if 'Parcial' in assignments_tagged.columns else False
            filtro_parcial_master = st.selectbox(
                "Filtrar por Parcial:", p_filter_opts,
                index=p_filter_opts.index(p_now) if has_now else 0, key="master_parcial_filter",
                help="Empieza en el parcial en curso. Elige 'Todos los Parciales' para ver el semestre completo."
            )

    else:
        selected_groups = available_groups
        filtro_parcial_master = "Todos los Parciales"

    # Filtrar asignaciones por grupo(s)
    if selected_groups:
        active_master = assignments_tagged[assignments_tagged['Grupo'].isin(selected_groups)].copy()
    else:
        active_master = assignments_tagged.copy()

    # Filtrar por parcial si se seleccionó uno en específico
    if filtro_parcial_master != "Todos los Parciales":
        active_master = active_master[active_master['Parcial'] == filtro_parcial_master]

    if active_master.empty:
        st.warning("No se encontraron registros para los filtros seleccionados.")
        return

    # Calcular bloques para los datos filtrados con la escala y peso activos
    block_summary = compute_student_block_grades(active_master, active_criteria_config)

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

    # Construir tabla pivote base
    pivot_df = block_summary.pivot(
        index=['Grupo', 'Nombre del estudiante'],
        columns='Fecha de entrega',
        values='block_grade'
    ).reset_index()
    # Bloques que existen pero aún no inician (para distinguirlos de celdas sin actividad)
    future_pivot = block_summary.pivot(
        index=['Grupo', 'Nombre del estudiante'],
        columns='Fecha de entrega',
        values='all_future'
    ).reset_index()
    not_eval_pivot = block_summary.pivot(
        index=['Grupo', 'Nombre del estudiante'],
        columns='Fecha de entrega',
        values='not_evaluated'
    ).reset_index()

    # Columnas de fecha existentes en el pivote
    existing_date_cols = [c for c in date_order if c in pivot_df.columns]

    # Calcular Promedio General del estudiante a través de todos los bloques disponibles (omitiendo bloques futuros)
    numeric_only = pivot_df[existing_date_cols]
    pivot_df['Promedio General'] = numeric_only.mean(axis=1, skipna=True).round(1).fillna(0.0)

    # Clasificación de rendimiento (Estatus) usando la escala y umbrales configurados
    pivot_df['Estatus'] = [classify_for(s, active_criteria_config, g) for s, g in zip(pivot_df['Promedio General'], pivot_df['Grupo'])]

    # Organizar columnas: 'Estatus' al lado del nombre del estudiante
    column_arrangement = ['Grupo', 'Nombre del estudiante', 'Estatus'] + existing_date_cols + ['Promedio General']
    pivot_df = pivot_df[column_arrangement]

    if section == NAV_INICIO and _drive_ready(teacher_folder_id):
        faltan = missing_setup_files(teacher_folder_id)
        if faltan:
            st.info(f"🚀 **Para activar todas las funciones**, sube {len(faltan)} plantilla(s) a tu carpeta de Drive. "
                    "Ve a **⚙️ Ajustes → 🚀 Primeros pasos**: ahí las descargas todas juntas.")

    if section == NAV_INICIO:
        if roster.empty:
            st.info("👥 **Nuevo:** sube tu lista oficial del grupo en **⚙️ Ajustes → 👥 Alumnos y cuentas** para unir cuentas duplicadas de Khan "
                    "y que tus alumnos entren con su matrícula y un PIN.")
        else:
            r_status = roster_status(raw_khan, roster, roster_links)
            pend = []
            if r_status['unlinked']:
                pend.append(f"{len(r_status['unlinked'])} cuenta(s) de Khan sin vincular")
            if not r_status['without_account'].empty:
                pend.append(f"{len(r_status['without_account'])} alumno(s) de tu lista sin cuenta de Khan")
            if pend:
                st.warning("👥 " + " y ".join(pend) + ". Revísalo en **⚙️ Ajustes → 👥 Alumnos y cuentas**.")

    calif_sub = None
    if section == NAV_CALIF:
        calif_sub = st.segmented_control("Vista", [CALIF_CONC, CALIF_FINAL, CALIF_ACT, CALIF_TEMAS], default=CALIF_CONC,
                                         key="calif_sub", label_visibility="collapsed") or CALIF_CONC

    # Evidencias, calificaciones del parcial y asistencia (archivos en la carpeta del docente)
    eval_evid, eval_extra, eval_att = load_eval_tables(teacher_folder_id)
    eval_ctx = {'roster': roster, 'evid': eval_evid, 'extra': eval_extra, 'att': eval_att}
    att_map = attendance_by_name(roster, eval_att, active_criteria_config,
                                 None if filtro_parcial_master in ("Todos los Parciales", "Sin asignar") else filtro_parcial_master)

    if section == NAV_EVAL:
        eval_sub = st.segmented_control("Qué registrar", ["📓 Sellos de evidencia", "📝 Examen y producto"],
                                        default="📓 Sellos de evidencia", key="eval_sub",
                                        label_visibility="collapsed") or "📓 Sellos de evidencia"
        if eval_sub.startswith("📓"):
            render_evidence_section(teacher_folder_id, roster, assignments_tagged, active_criteria_config)
        else:
            render_extra_section(teacher_folder_id, roster, active_criteria_config)

    if section == NAV_CALIF and calif_sub == CALIF_FINAL:
        render_final_section(teacher_folder_id, roster, assignments_tagged, active_criteria_config)

    if section == NAV_INICIO:
        render_teacher_summary(active_master, block_summary, active_criteria_config, group_color_map(available_groups), asignatura, att_map,
                               folder_id=teacher_folder_id,
                               parcial_label=None if filtro_parcial_master in ("Todos los Parciales", "Sin asignar") else filtro_parcial_master)

    if section == NAV_CALIF and calif_sub == CALIF_ACT:
        render_task_analysis(active_master)

    if section == NAV_CALIF and calif_sub == CALIF_TEMAS:
        render_group_topics(active_master, load_topics_map(teacher_folder_id))

    if section == NAV_CALIF and calif_sub == CALIF_CONC:
        # Controles propios del concentrado
        cf_col1, cf_col2 = st.columns([3, 2])
        with cf_col1:
            search_student = st.text_input("🔍 Buscar estudiante:", placeholder="Nombre...").strip()
        with cf_col2:
            fill_option = st.selectbox(
                "Celdas sin actividad:",
                ["N/A", "—", "0.0"],
                help="Cómo mostrar los bloques en los que el alumno no tiene actividades asignadas (p. ej. fechas de otro grupo). Solo afecta la visualización: esas celdas nunca cuentan para el promedio."
            )

        # Búsqueda por nombre si se especificó
        if search_student:
            pivot_df = pivot_df[pivot_df['Nombre del estudiante'].str.contains(search_student, case=False, na=False, regex=False)]

        # --------------------------------------------------------------------------
        # MÉTRICAS Y RESUMEN RÁPIDO DE RENDIMIENTO ACADÉMICO
        # --------------------------------------------------------------------------
        st.markdown("#### 🎯 Distribución de Rendimiento Académico")
        estatus_counts = pivot_df['Estatus'].value_counts()
        c_exc = int(estatus_counts.get('Excelente', 0))
        c_bien = int(estatus_counts.get('Bien', 0))
        c_reg = int(estatus_counts.get('Regular', 0))
        c_riesgo = int(estatus_counts.get('En riesgo', 0))
        total_st = len(pivot_df)

        col_e1, col_e2, col_e3, col_e4 = st.columns(4)
        with col_e1:
            pct = (c_exc / total_st * 100) if total_st else 0
            st.metric(f"🌟 Excelente (≥ {th_input_exc:.1f})", f"{c_exc}", f"{pct:.0f}% alumnos")
        with col_e2:
            pct = (c_bien / total_st * 100) if total_st else 0
            st.metric(f"👍 Bien (≥ {th_input_bien:.1f})", f"{c_bien}", f"{pct:.0f}% alumnos")
        with col_e3:
            pct = (c_reg / total_st * 100) if total_st else 0
            st.metric(f"👌 Regular (≥ {th_input_reg:.1f})", f"{c_reg}", f"{pct:.0f}% alumnos")
        with col_e4:
            pct = (c_riesgo / total_st * 100) if total_st else 0
            st.metric(f"🚨 En riesgo (< {th_input_reg:.1f})", f"{c_riesgo}", f"{pct:.0f}% alumnos")

        st.write("")

        # Formateo de visualización de notas
        display_pivot = pivot_df.copy()
        future_flags = future_pivot.set_index(['Grupo', 'Nombre del estudiante']).reindex(
            pd.MultiIndex.from_frame(display_pivot[['Grupo', 'Nombre del estudiante']])
        )
        not_eval_flags = not_eval_pivot.set_index(['Grupo', 'Nombre del estudiante']).reindex(
            pd.MultiIndex.from_frame(display_pivot[['Grupo', 'Nombre del estudiante']])
        )
        for col in existing_date_cols:
            is_future_block = future_flags[col].fillna(False).astype(bool).to_numpy()
            is_not_eval_block = not_eval_flags[col].fillna(False).astype(bool).to_numpy()
            display_pivot[col] = [
                f"{x:.1f}" if pd.notna(x) else ("Programada" if fut else ("En curso" if ne else fill_option))
                for x, fut, ne in zip(display_pivot[col], is_future_block, is_not_eval_block)
            ]
        display_pivot['Promedio General'] = display_pivot['Promedio General'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "0.0")

        # Renderizar la tabla pivote con Estatus inmediatamente después del nombre
        st.dataframe(
            display_pivot,
            width='stretch',
            hide_index=True,
            height=min(550, 100 + len(display_pivot) * 35),
            column_config={
                "Grupo": st.column_config.TextColumn("Grupo", width="small"),
                "Nombre del estudiante": st.column_config.TextColumn("Nombre del estudiante", width="large"),
                "Estatus": st.column_config.TextColumn("Estatus", width="medium"),
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
                file_name=f"Concentrado_Calificaciones_{now_local().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        with exp_c2:
            excel_buff = io.BytesIO()
            with pd.ExcelWriter(excel_buff, engine='openpyxl') as writer:
                display_pivot.to_excel(writer, index=False, sheet_name="Concentrado")
            st.download_button(
                label="📥 Descargar Concentrado (Excel)",
                data=excel_buff.getvalue(),
                file_name=f"Concentrado_Calificaciones_{now_local().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    if section == NAV_ALUMNO:
        # --------------------------------------------------------------------------
        # SECCIÓN 3: ENHANCED ADMIN DRILL-DOWN (INSPECCIÓN INDIVIDUAL DE ESTUDIANTE)
        # --------------------------------------------------------------------------
        st.markdown("### 🔍 Detalle Individual de Estudiante (Drill-Down)")
        st.caption("Selecciona a un estudiante para inspeccionar el desglose completo de todas sus actividades con formato condicional.")

        candidate_students_df = assignments_tagged[assignments_tagged['Grupo'].isin(selected_groups)] if selected_groups else assignments_tagged
        available_students = sorted(candidate_students_df['Nombre del estudiante'].dropna().unique())

        if not available_students:
            st.info("No hay estudiantes para los grupos seleccionados.")
            return

        drill_col1, drill_col2, drill_col3 = st.columns([3, 1, 1])
        with drill_col1:
            selected_student = st.selectbox(
                "Selecciona un estudiante para inspeccionar en detalle:",
                options=available_students,
                key="admin_drilldown_student_select"
            )

        student_tasks_data = assignments_tagged[assignments_tagged['Nombre del estudiante'] == selected_student].copy()
        student_group = student_tasks_data['Grupo'].iloc[0] if not student_tasks_data.empty else "N/A"
        # Criterios del grupo del alumno (si el docente los define por grupo)
        drill_cfg = group_config(active_criteria_config, student_group)

        # Calcular promedio del estudiante en todos los bloques (omitiendo futuros)
        st_blocks = compute_student_block_grades(student_tasks_data, drill_cfg)
        valid_st_blocks = st_blocks['block_grade'].dropna()
        st_avg = valid_st_blocks.mean() if not valid_st_blocks.empty else 0.0
        st_estatus = classify_student(st_avg, drill_cfg['thresholds'], drill_cfg['escala_maxima'])

        with drill_col2:
            st.write("")
            st.write("")
            st.info(f"**Grupo:** {student_group}")

        with drill_col3:
            st.write("")
            st.write("")
            st.info(f"**Estatus:** {st_estatus} ({st_avg:.1f})")

        # --------------------------------------------------------------------------
        # TABLA COMPLETA CON FORMATO CONDICIONAL (.style)
        # --------------------------------------------------------------------------
        st.markdown("#### 💬 Mensaje sugerido")
        msg_audience = st.radio(
            "Para:", ["El alumno", "Su familia"], horizontal=True, key="msg_audience",
            help="Texto listo para copiar y enviar. Revísalo y ajústalo antes de mandarlo."
        )
        if not student_tasks_data.empty:
            msg_ins = build_student_insights(student_tasks_data, drill_cfg)
            msg_text = build_student_message(
                msg_ins, selected_student, asignatura, teacher_name,
                'alumno' if msg_audience == "El alumno" else 'familia'
            )
            render_copy_message(msg_text, key="wa_student_msg")

        # Metas, dominio por tema y reporte imprimible para la familia
        sel_ids = roster.loc[roster['Nombre'] == selected_student, 'ID'] if not roster.empty else pd.Series(dtype=str)
        sel_id = sel_ids.iloc[0] if not sel_ids.empty else None
        p_now = current_parcial(drill_cfg)
        goal = student_goal(load_goals(teacher_folder_id), sel_id, p_now)
        topics_map = load_topics_map(teacher_folder_id)
        mastery = topic_mastery(student_tasks_data, topics_map)
        if goal and goal['meta'] is not None:
            st.markdown(f"#### 🎯 Meta del alumno ({p_now}): **{goal['meta']:g}**" + (f"  \n*\"{goal['plan']}\"*" if goal['plan'] else ""))
        if not mastery.empty:
            st.markdown("#### 📚 Dominio por tema")
            render_topic_bars(mastery)
        fu_all = load_followups(teacher_folder_id)
        fu_mine = fu_all[(fu_all['Grupo'] == student_group) & (fu_all['Alumno'] == selected_student)] if not fu_all.empty else fu_all
        notes_att = eval_att[(eval_att['ID alumno'] == sel_id) & (eval_att['Nota'] != '')] if (sel_id and not eval_att.empty) else eval_att.iloc[0:0]
        if not fu_mine.empty or not notes_att.empty:
            with st.expander(f"📝 Seguimiento y notas ({len(fu_mine) + len(notes_att)})"):
                for _, r in fu_mine.sort_values('Fecha').iterrows():
                    st.markdown(f"✅ **Atendido** · {html.escape(str(r['Fecha'])[:10])}" + (f" — {html.escape(r['Nota'])}" if r['Nota'] else ""))
                for _, r in notes_att.sort_values('Fecha').iterrows():
                    st.markdown(f"{html.escape(r['Estado'])} · {html.escape(r['Fecha'])} — {html.escape(r['Nota'])}")
        final_row = None
        if uses_components(group_config(drill_cfg, student_group, p_now)) and sel_id:
            comps = compute_components(roster[roster['ID'] == sel_id], eval_evid, eval_extra, eval_att, drill_cfg, p_now)
            fin = compute_final_grades(comps, _khan_avg_by_name(student_tasks_data, drill_cfg, p_now), drill_cfg, p_now)
            final_row = fin.iloc[0].to_dict() if not fin.empty else None
        pdf_att = attendance_by_name(roster, eval_att, drill_cfg, p_now).get(selected_student)
        try:
            pdf_bytes = subject_report_pdf(selected_student, student_group, asignatura, teacher_name, student_tasks_data,
                                           group_config(drill_cfg, student_group, p_now), final_row, pdf_att, goal, mastery)
            st.download_button("📄 Reporte de avance para la familia (PDF imprimible)", pdf_bytes,
                               file_name=f"Reporte_{re.sub(r'[^A-Za-z0-9]+', '_', str(selected_student))}.pdf",
                               mime="application/pdf", key="dl_student_pdf", width='stretch')
        except Exception as e:
            st.caption(f"No se pudo generar el PDF: {e}")

        st.markdown("#### 📋 Listado Completo de Actividades del Alumno")
        st.caption("Semáforo de detección rápida: 🟥 **Rojo tenue:** Calificación de 0 puntos (sin entrega o penalizada) | 🟨 **Amarillo tenue:** Actividad realizada con intentos que superan el límite permitido | ⚪ **Gris/Cursiva:** Actividad programada o en curso (aún no vence).")

        # Ordenar por fecha de entrega y nombre
        all_tasks_sorted = student_tasks_data.sort_values(by=['dt_entrega', 'Nombre de la tarea']).copy()

        # Columnas requeridas: 'Nombre de la tarea', 'Tipo', 'Parcial', 'Fecha de entrega', 'Número de intentos', 'Puntos Obtenidos'
        drill_rows = []
        for _, task_r in all_tasks_sorted.iterrows():
            is_prog = task_r.get('status') in NOT_EVALUATED_STATUSES
            if is_prog:
                pts_display = task_r.get('status')
                attempts_display = "—"
            else:
                pts_display = f"{task_r['earned_points']:.1f}"
                raw_att = task_r.get('Número de intentos')
                attempts_display = str(task_r.get('attempts_count', 0)) if pd.notna(raw_att) and str(raw_att).strip() not in ['', 'En progreso'] else ("1" if task_r.get('is_completed') else "0")

            drill_rows.append({
                'Nombre de la tarea': task_r['Nombre de la tarea'],
                'Tipo': task_r['Tipo de tarea'],
                'Parcial': task_r['Parcial'],
                'Fecha de entrega': task_r['Fecha de entrega'],
                'Número de intentos': attempts_display,
                'Puntos Obtenidos': pts_display,
                '_status': task_r['status'],
                '_earned_points': task_r['earned_points'],
                '_evaluar_intentos': task_r['evaluar_intentos'],
                '_max_intentos': task_r['max_intentos']
            })

        drill_display = pd.DataFrame(drill_rows)

        # Función de formato condicional con Pandas .style
        def highlight_drilldown_rows(row):
            status = row.get('_status', '')
            if status in NOT_EVALUATED_STATUSES:
                return ['background-color: #f8fafc; color: #64748b; font-style: italic;'] * len(row)

            score = row.get('_earned_points', 0)
            attempts = row.get('Número de intentos', 0)
            eval_attempts = row.get('_evaluar_intentos', False)
            max_attempts = row.get('_max_intentos', 3)
            try:
                s_val = float(score)
            except (ValueError, TypeError):
                s_val = 0.0
            try:
                a_val = int(float(str(attempts).strip()))
            except (ValueError, TypeError):
                a_val = 0

            # Rojo tenue para puntaje final de 0 en actividades activas
            if s_val == 0.0:
                return ['background-color: #fee2e2; color: #991b1b; font-weight: 500;'] * len(row)
            # Amarillo tenue para intentos extras (> max_intentos) SOLO si la actividad evalúa intentos
            elif eval_attempts and a_val > max_attempts:
                return ['background-color: #fef9c3; color: #854d0e; font-weight: 500;'] * len(row)
            return [''] * len(row)

        cols_to_show = ['Nombre de la tarea', 'Tipo', 'Parcial', 'Fecha de entrega', 'Número de intentos', 'Puntos Obtenidos']
        styled_drilldown = drill_display.style.apply(highlight_drilldown_rows, axis=1)

        st.dataframe(
            styled_drilldown,
            column_order=cols_to_show,
            width='stretch',
            hide_index=True,
            height=min(550, 100 + len(drill_display) * 35),
            column_config={
                "Nombre de la tarea": st.column_config.TextColumn("Nombre de la tarea", width="large"),
                "Tipo": st.column_config.TextColumn("Tipo", width="small"),
                "Parcial": st.column_config.TextColumn("Parcial", width="small"),
                "Fecha de entrega": st.column_config.TextColumn("Fecha de entrega", width="medium"),
                "Número de intentos": st.column_config.TextColumn("Número de intentos", width="small"),
                "Puntos Obtenidos": st.column_config.TextColumn("Puntos Obtenidos", width="small"),
            }
        )

        st.write("")

        # Visualización complementaria: Dashboard idéntico con desglose por bloques y filtros
        with st.expander("👁️ Ver como alumno (vista previa de su portal, útil para explicarle su avance)", expanded=False):
            updated_at = student_tasks_data['Archivo_Modificado'].max() if 'Archivo_Modificado' in student_tasks_data.columns else None
            render_student_experience(selected_student, student_tasks_data, drill_cfg, key_prefix="admin", updated_at=updated_at,
                                      eval_ctx={**eval_ctx, 'folder_id': teacher_folder_id}, student_id=sel_id)


# ==============================================================================
# VISTA: ESTUDIANTE (DASHBOARD PERSONALIZADO)
# ==============================================================================
def render_student():
    student_name = st.session_state.get('student_name', '')
    username = st.session_state.get('username', '')
    asignatura = st.session_state.get('asignatura', 'Temas Selectos de Matemáticas II')
    teacher_folder_id = st.session_state.get('teacher_folder_id')

    # Cargar datos crudos exclusivamente de la carpeta de la asignatura/docente en Drive
    raw_khan = load_teacher_raw_assignments(teacher_folder_id)
    roster, roster_links = load_roster_and_links(teacher_folder_id)
    raw_assignments = apply_roster_links(raw_khan, roster, roster_links)

    # Nombre oficial del alumno: por su ID (acceso con PIN) o por su cuenta de Khan vinculada
    student_id = st.session_state.get('student_id')
    if not roster.empty:
        if student_id and student_id in set(roster['ID']):
            student_name = roster.set_index('ID').at[student_id, 'Nombre']
        else:
            linked_id = next((rid for (acc, _), rid in build_link_map(raw_khan, roster, roster_links).items()
                              if acc.strip() == str(student_name).strip()), None)
            if linked_id:
                student_name = roster.set_index('ID').at[linked_id, 'Nombre']

    if not raw_assignments.empty and 'Tipo de tarea' in raw_assignments.columns:
        unique_task_types = sorted([
            t for t in raw_assignments['Tipo de tarea'].dropna().astype(str).str.strip().unique()
            if t
        ])
    else:
        unique_task_types = ['Video', 'Ejercicio', 'Artículo']

    criterios_data = khan_view_config(load_teacher_criterios(teacher_folder_id, unique_task_types))

    # Calificar solo las actividades del alumno (no las de todo el grupo)
    if not raw_assignments.empty and 'Nombre del estudiante' in raw_assignments.columns:
        own_rows = raw_assignments[raw_assignments['Nombre del estudiante'].str.strip() == student_name.strip()]
    else:
        own_rows = pd.DataFrame()
    student_tasks = apply_dynamic_grading(own_rows.copy(), criterios_data)

    # CRÍTICO: Asignar Parciales vectorialmente comparando .dt.date contra datetime.date de criterios.json del docente
    student_tasks = assign_parciales_vectorized(student_tasks, criterios_data)
    student_group = student_tasks['Grupo'].iloc[0] if not student_tasks.empty else ""
    if not student_group and student_id and not roster.empty and student_id in set(roster['ID']):
        student_group = roster.set_index('ID').at[student_id, 'Grupo']
    # Criterios acordados con su grupo (si el docente los define por grupo)
    criterios_data = group_config(criterios_data, student_group)

    teacher_name = st.session_state.get('teacher_name', 'Docente')
    header_col1, header_col2 = st.columns([5, 1])
    with header_col1:
        st.markdown(f"""
        <div class="main-header">
            <h1>🎓 {html.escape(str(student_name))}</h1>
            <p><strong>{html.escape(str(asignatura))}</strong> · Grupo {html.escape(str(student_group))} · Docente: {html.escape(str(teacher_name))}</p>
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", width='stretch'):
            st.session_state.clear()
            st.rerun()

    if raw_assignments.empty:
        st.warning("No hay tareas registradas en el sistema para esta asignatura. Contacta al docente.")
        return

    updated_at = student_tasks['Archivo_Modificado'].max() if 'Archivo_Modificado' in student_tasks.columns and not student_tasks.empty else None
    my_id = student_id
    if not my_id and not roster.empty:
        ids = roster.loc[roster['Nombre'] == student_name, 'ID']
        my_id = ids.iloc[0] if not ids.empty else None
    eval_evid, eval_extra, eval_att = load_eval_tables(teacher_folder_id) if my_id else (None, None, None)
    eval_ctx = {'roster': roster, 'evid': eval_evid, 'extra': eval_extra, 'att': eval_att, 'folder_id': teacher_folder_id} if my_id else None
    render_student_experience(student_name, student_tasks, criterios_data, key_prefix="student", updated_at=updated_at,
                              eval_ctx=eval_ctx, student_id=my_id)



# ==============================================================================
# CONTROLADOR PRINCIPAL
# ==============================================================================
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['username'] = None
        st.session_state['student_name'] = None
        st.session_state['teacher_name'] = None
        st.session_state['teacher_email'] = None
        st.session_state['asignatura'] = None
        st.session_state['carpeta_nombre'] = None
        st.session_state['teacher_folder_id'] = None

    if not st.session_state['logged_in']:
        render_login()
    else:
        if st.session_state.get('role') == 'admin':
            render_admin()
        elif st.session_state.get('role') == 'tutor':
            render_tutor_only()
        else:
            render_student()



if __name__ == "__main__":
    main()
