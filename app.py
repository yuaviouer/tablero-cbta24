"""
Portal de Calificaciones Khan Academy - CBTA 24
Sincronización con Google Drive API & Gestión Multimateria
"""

import os
import io
import json
import glob
import re
from datetime import date, datetime
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

# Credenciales de administrador por defecto (fallback maestro)
ADMIN_USERNAME = os.environ.get("ADMIN_USER", "javier_admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin_password")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
CONFIG_PARCIALES_PATH = os.path.join(DATA_DIR, "config_parciales.json")
CONFIG_CRITERIOS_PATH = os.path.join(DATA_DIR, "config_criterios.json")

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
    now_year = datetime.now().year
    next_year = now_year + 1
    return {
        'Parcial 1': {'start': f'{now_year}-08-15', 'end': f'{now_year}-10-03'},
        'Parcial 2': {'start': f'{now_year}-10-04', 'end': f'{now_year}-11-21'},
        'Parcial 3': {'start': f'{now_year}-11-22', 'end': f'{next_year}-01-23'}
    }


def load_parciales_config():
    """Carga la configuración de fechas de Parciales desde archivo JSON o default dinámico."""
    os.makedirs(DATA_DIR, exist_ok=True)
    defaults = get_default_parciales_config()
    now_year = datetime.now().year

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
                    # Si el archivo tiene un año inferior al actual, migrar automáticamente al ciclo actual
                    if parsed['Parcial 1']['start'].year < now_year:
                        parsed = {
                            k: {'start': date.fromisoformat(v['start']), 'end': date.fromisoformat(v['end'])}
                            for k, v in defaults.items()
                        }
                        save_parciales_config(parsed)
                    return parsed
        except Exception:
            pass

    parsed_defaults = {
        k: {'start': date.fromisoformat(v['start']), 'end': date.fromisoformat(v['end'])}
        for k, v in defaults.items()
    }
    save_parciales_config(parsed_defaults)
    return parsed_defaults


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


def assign_parciales_vectorized(df, parcial_config):
    """
    CRÍTICO: Asigna la etiqueta 'Parcial' a cada actividad extrayendo .dt.date
    de la columna 'dt_entrega' (Timestamp de Pandas) y comparándola directamente
    contra los objetos datetime.date obtenidos de st.date_input con operadores >= y <=.
    """
    if df.empty or 'dt_entrega' not in df.columns:
        df['Parcial'] = 'Sin asignar'
        return df

    # Extracción explícita de datetime.date desde la columna Timestamp de Pandas
    task_dates = df['dt_entrega'].dt.date
    parcial_series = pd.Series('Sin asignar', index=df.index, dtype='object')

    for p_name in ['Parcial 1', 'Parcial 2', 'Parcial 3']:
        cfg = parcial_config.get(p_name, {})
        start_d = cfg.get('start')
        end_d = cfg.get('end')

        if start_d is not None and end_d is not None:
            if isinstance(start_d, str):
                start_d = date.fromisoformat(start_d)
            if isinstance(end_d, str):
                end_d = date.fromisoformat(end_d)

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
    - Determina dinámicamente el año actual (datetime.now().year)
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
    now = datetime.now()
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
        if parsed_month_num is not None:
            if 1 <= parsed_month_num <= 7 and 8 <= now_month <= 12:
                target_year = now_year + 1

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
def get_default_criteria_config(unique_task_types):
    """
    Genera criterios de evaluación predeterminados para los tipos de tareas detectados:
    - Ejercicios / Pruebas / Cuestionarios: multiplicados por aciertos, evalúan intentos (máx 3 libres).
    - Artículos: 2.0 pts a tiempo, 0.2 tardío, puntaje plano, sin evaluación de intentos.
    - Videos: 1.0 pto a tiempo, 0.1 tardío, puntaje plano, sin evaluación de intentos.
    - Otros: 1.0 pto a tiempo, 0.1 tardío, puntaje plano, sin evaluación de intentos.
    """
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


def load_criteria_config(unique_task_types):
    """
    Carga la configuración de criterios desde config_criterios.json.
    Si faltan tipos de tarea presentes en los datos, los completa con los valores predeterminados.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    defaults = get_default_criteria_config(unique_task_types)

    if os.path.exists(CONFIG_CRITERIOS_PATH):
        try:
            with open(CONFIG_CRITERIOS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            config = {}
            for t in unique_task_types:
                if t in saved:
                    config[t] = {
                        'valor_a_tiempo': float(saved[t].get('valor_a_tiempo', 1.0)),
                        'valor_tardio': float(saved[t].get('valor_tardio', 0.1)),
                        'multiplicar_por_aciertos': bool(saved[t].get('multiplicar_por_aciertos', False)),
                        'evaluar_intentos': bool(saved[t].get('evaluar_intentos', False)),
                        'max_intentos': int(saved[t].get('max_intentos', 3))
                    }
                else:
                    config[t] = defaults.get(t, {
                        'valor_a_tiempo': 1.0,
                        'valor_tardio': 0.1,
                        'multiplicar_por_aciertos': False,
                        'evaluar_intentos': False,
                        'max_intentos': 1
                    })
            return config
        except Exception:
            pass

    save_criteria_config(defaults)
    return defaults


def save_criteria_config(config_dict):
    """Guarda la configuración de criterios en formato JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_CRITERIOS_PATH, "w", encoding="utf-8") as f:
        json.dump(config_dict, f, indent=4, ensure_ascii=False)


def render_criteria_explanation(criteria_config):
    """Genera texto dinámico en formato Markdown explicando los criterios activos."""
    md = ["### Sistema de Criterios de Evaluación Vigente\n"]
    for t_name, cfg in criteria_config.items():
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

    md.append("\n- **Calificación del Bloque:** $\\left( \\frac{\\sum \\text{Puntos Ganados}}{\\sum \\text{Puntos Posibles}} \\right) \\times 10$, redondeado a 1 decimal.")
    return "\n".join(md)


# ==============================================================================
# MOTOR DE CALIFICACIÓN DINÁMICO
# ==============================================================================
def apply_dynamic_grading(df, criteria_config):
    """
    Aplica las reglas de calificación y penalización dinámicamente según criteria_config,
    sin recurrir a cadenas fijas ('Video', 'Artículo', etc.):
    - Busca la configuración del 'Tipo de tarea' correspondiente.
    - Si evaluar_intentos es True: penaliza cada intento > max_intentos restando 1 acierto.
      Si la entrega es tardía Y los intentos > max_intentos, califica con 0 puntos.
    - Si evaluar_intentos es False: no penaliza intentos.
    - Si multiplicar_por_aciertos es True:
        max_points = valor_a_tiempo * total_questions
        earned_points = min(valor_elegido * effective_correct, valor_elegido * total_questions)
    - Si multiplicar_por_aciertos es False:
        max_points = valor_a_tiempo
        earned_points = valor_elegido (si completado y no anulado)
    """
    if df.empty:
        return df

    graded_rows = []
    cfg_lookup = {k.strip().lower(): v for k, v in criteria_config.items()}

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

        now = datetime.now()
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

        if is_future:
            # Tarea futura (no iniciada): se fijan Max Points y Earned Points a 0
            # para no tener ningún peso matemático sobre el promedio del bloque
            earned_pts = 0.0
            max_pts = 0.0
            status = 'Programada'
            obs = 'Programada (no iniciada)'
            is_completed = False
            is_late = False
        else:
            is_completed = pd.notna(comp_dt) and str(comp_dt).strip() != ''
            is_late = is_completed and pd.notna(due_dt) and (comp_dt > due_dt)

            if evaluar_intentos:
                penalty_attempts = max(0, attempts - max_intentos)
            else:
                penalty_attempts = 0

            effective_correct = max(0.0, correct_q - penalty_attempts)
            valor_a_tiempo = float(cfg.get('valor_a_tiempo', 1.0))
            valor_tardio = float(cfg.get('valor_tardio', 0.1))
            multiplicar = bool(cfg.get('multiplicar_por_aciertos', False))

            if not is_completed:
                earned_pts = 0.0
                status = 'No completado'
                obs = 'Sin entrega'
                max_pts = (valor_a_tiempo * total_q) if (multiplicar and total_q > 0) else valor_a_tiempo

            elif is_late and evaluar_intentos and attempts > max_intentos:
                earned_pts = 0.0
                status = f'Tardía (>{max_intentos} intentos)'
                obs = f'Tardía + >{max_intentos} intentos (0 pts)'
                max_pts = (valor_a_tiempo * total_q) if (multiplicar and total_q > 0) else valor_a_tiempo

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
            'evaluar_intentos': evaluar_intentos,
            'max_intentos': max_intentos
        })

    graded_df = pd.DataFrame(graded_rows, index=df.index)
    result_df = df.copy()
    for col in graded_df.columns:
        result_df[col] = graded_df[col]
    return result_df



# ==============================================================================
# CLASIFICACIÓN DE RENDIMIENTO DEL ESTUDIANTE (ESTATUS)
# ==============================================================================
def classify_student(score):
    """
    Clasifica el rendimiento del estudiante según su promedio general:
    - 'Excelente': >= 9.5
    - 'Bien': 8.5 a 9.49
    - 'Regular': 7.0 a 8.49
    - 'Mal': 6.0 a 6.99
    - 'En riesgo': < 6.0
    """
    if pd.isna(score):
        return 'En riesgo'
    try:
        val = float(score)
    except (ValueError, TypeError):
        return 'En riesgo'

    if val >= 9.5:
        return 'Excelente'
    elif val >= 8.5:
        return 'Bien'
    elif val >= 7.0:
        return 'Regular'
    elif val >= 6.0:
        return 'Mal'
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
    if 'gcp_service_account' not in st.secrets:
        return None
    raw_creds = st.secrets['gcp_service_account']
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


def upload_file_to_drive(service, file_bytes, filename, folder_id, mime_type='application/octet-stream'):
    """
    Sube un archivo directamente a una subcarpeta de Google Drive en memoria.
    Si ya existe un archivo con ese nombre en la carpeta, lo actualiza.
    Si no existe, lo crea. NO escribe nada en disco local.
    """
    if not service or not folder_id or str(folder_id).startswith('PEGA_AQUÍ'):
        return False, "Google Drive no está conectado o no se especificó la carpeta del docente."

    try:
        existing = find_drive_item(service, filename, folder_id, is_folder=False)
        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)

        if existing:
            service.files().update(
                fileId=existing['id'],
                media_body=media
            ).execute()
            return True, f"Archivo '{filename}' actualizado exitosamente en Google Drive."
        else:
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            return True, f"Archivo '{filename}' guardado exitosamente en Google Drive."
    except Exception as e:
        return False, f"Error al subir '{filename}' a Google Drive: {e}"


def find_drive_item(service, name, parent_id, is_folder=None):
    """
    Busca un archivo o carpeta por nombre exacto dentro de una carpeta padre en Drive.
    """
    if not service or not parent_id or str(parent_id).startswith('PEGA_AQUÍ'):
        return None

    query_parts = [
        f"'{parent_id}' in parents",
        f"name = '{name}'",
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
            pageSize=10
        ).execute()
        files = results.get('files', [])
        if files:
            return files[0]
        return None
    except Exception as e:
        st.error(f"Error al buscar '{name}' en Google Drive: {e}")
        return None


def download_drive_bytes(service, file_id):
    """
    Descarga el contenido de un archivo de Drive en memoria usando io.BytesIO.
    NO escribe nada en disco local (Zero Local Disk Storage).
    """
    if not service or not file_id:
        return None
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue()
    except Exception as e:
        st.error(f"Error al descargar archivo de Google Drive (ID: {file_id}): {e}")
        return None


def read_drive_excel(service, file_id):
    """Lee un archivo Excel desde Google Drive directamente en un DataFrame en memoria."""
    content = download_drive_bytes(service, file_id)
    if content:
        try:
            return pd.read_excel(io.BytesIO(content))
        except Exception as e:
            st.error(f"Error al procesar archivo Excel desde Drive: {e}")
    return pd.DataFrame()


def read_drive_csv(service, file_id):
    """Lee un archivo CSV desde Google Drive directamente en un DataFrame en memoria."""
    content = download_drive_bytes(service, file_id)
    if not content:
        return pd.DataFrame()
    try:
        return pd.read_csv(io.BytesIO(content), encoding='utf-8-sig')
    except Exception:
        try:
            return pd.read_csv(io.BytesIO(content), encoding='latin-1')
        except Exception as e:
            st.error(f"Error al decodificar CSV desde Drive: {e}")
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
            fields='files(id, name, mimeType)',
            pageSize=100
        ).execute()
        files = results.get('files', [])
        csv_files = [
            f for f in files
            if f.get('name', '').lower().endswith('.csv') and 'credencial' not in f.get('name', '').lower()
        ]
        return csv_files
    except Exception as e:
        st.error(f"Error al listar archivos CSV en Google Drive: {e}")
        return []


@st.cache_data(ttl=120)
def load_docentes_master():
    """
    Carga el archivo maestro docentes.xlsx ubicado en la carpeta raíz de Drive.
    Columnas requeridas: 'usuario_docente', 'password', 'asignatura', 'carpeta_nombre'.
    """
    service = get_drive_service()
    if not service or str(ROOT_FOLDER_ID).startswith('PEGA_AQUÍ'):
        return pd.DataFrame(columns=['usuario_docente', 'password', 'asignatura', 'carpeta_nombre'])

    doc_file = find_drive_item(service, "docentes.xlsx", ROOT_FOLDER_ID, is_folder=False)
    if not doc_file:
        return pd.DataFrame(columns=['usuario_docente', 'password', 'asignatura', 'carpeta_nombre'])

    df = read_drive_excel(service, doc_file['id'])
    if df.empty:
        return pd.DataFrame(columns=['usuario_docente', 'password', 'asignatura', 'carpeta_nombre'])

    df.columns = [str(c).strip() for c in df.columns]
    rename_map = {}
    for col in df.columns:
        cl = col.lower()
        if 'usuario' in cl:
            rename_map[col] = 'usuario_docente'
        elif 'pass' in cl or 'contrase' in cl:
            rename_map[col] = 'password'
        elif 'asig' in cl or 'materia' in cl:
            rename_map[col] = 'asignatura'
        elif 'carpeta' in cl:
            rename_map[col] = 'carpeta_nombre'
    df = df.rename(columns=rename_map)

    for req in ['usuario_docente', 'password', 'asignatura', 'carpeta_nombre']:
        if req not in df.columns:
            df[req] = ''
        else:
            df[req] = df[req].astype(str).str.strip()

    return df[['usuario_docente', 'password', 'asignatura', 'carpeta_nombre']]


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
        df['Usuario'] = df['Usuario'].astype(str).str.strip()
        df['Contraseña'] = df['Contraseña'].astype(str).str.strip()
        df['Nombre del estudiante'] = df['Nombre del estudiante'].astype(str).str.strip()
        return df[['Usuario', 'Contraseña', 'Nombre del estudiante']].drop_duplicates(subset=['Usuario'])
    return pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])


def load_credentials_local_fallback():
    """Fallback local para lectura de credenciales si Drive no está configurado."""
    os.makedirs(DATA_DIR, exist_ok=True)
    excel_path = os.path.join(DATA_DIR, "credenciales.xlsx")
    if os.path.exists(excel_path):
        try:
            df = pd.read_excel(excel_path)
            return normalize_credentials_df(df)
        except Exception:
            pass
    csv_files = glob.glob(os.path.join(DATA_DIR, "*redencial*.csv"))
    if csv_files:
        dfs = []
        for cf in csv_files:
            try:
                tdf = pd.read_csv(cf, encoding='utf-8-sig')
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
            except Exception:
                continue
    if not dfs:
        return pd.DataFrame()
    all_data = pd.concat(dfs, ignore_index=True)
    all_data.columns = [c.strip() for c in all_data.columns]
    if 'Nombre del estudiante' in all_data.columns:
        all_data['Nombre del estudiante'] = all_data['Nombre del estudiante'].astype(str).str.strip()
    if 'Tipo de tarea' in all_data.columns:
        all_data['Tipo de tarea'] = all_data['Tipo de tarea'].astype(str).str.strip()
    all_data['dt_entrega'] = all_data['Fecha de entrega'].apply(parse_khan_date) if 'Fecha de entrega' in all_data.columns else pd.NaT
    all_data['dt_terminacion'] = all_data['Última fecha de terminación'].apply(parse_khan_date) if 'Última fecha de terminación' in all_data.columns else pd.NaT
    all_data['dt_inicio'] = all_data['Fecha de inicio'].apply(parse_khan_date) if 'Fecha de inicio' in all_data.columns else pd.NaT
    return all_data


@st.cache_data(ttl=300)
def load_teacher_credentials(folder_id):
    """
    Carga las credenciales de los estudiantes desde la subcarpeta del docente en Google Drive.
    Busca 'credenciales.xlsx' o archivos que contengan 'credencial' (.xlsx o .csv) en memoria.
    """
    service = get_drive_service()
    if not service or not folder_id or str(folder_id).startswith('PEGA_AQUÍ'):
        return load_credentials_local_fallback()

    # 1. Intentar credenciales.xlsx
    cred_file = find_drive_item(service, "credenciales.xlsx", folder_id, is_folder=False)
    if cred_file:
        df = read_drive_excel(service, cred_file['id'])
        norm_df = normalize_credentials_df(df)
        if not norm_df.empty:
            return norm_df

    # 2. Buscar otros archivos con 'credencial'
    query = f"'{folder_id}' in parents and trashed = false"
    try:
        results = service.files().list(q=query, fields='files(id, name, mimeType)').execute()
        files = results.get('files', [])
        for f in files:
            fname = f.get('name', '').lower()
            if 'credencial' in fname:
                if fname.endswith('.xlsx'):
                    df = read_drive_excel(service, f['id'])
                elif fname.endswith('.csv'):
                    df = read_drive_csv(service, f['id'])
                else:
                    continue
                norm_df = normalize_credentials_df(df)
                if not norm_df.empty:
                    return norm_df
    except Exception as e:
        st.error(f"Error al buscar credenciales en la carpeta de Drive: {e}")

    return pd.DataFrame(columns=['Usuario', 'Contraseña', 'Nombre del estudiante'])


@st.cache_data(ttl=300)
def load_teacher_raw_assignments(folder_id):
    """
    Descarga en memoria todos los CSVs de Khan Academy en la subcarpeta del docente en Google Drive,
    extrae el Grupo de cada archivo, y limpia y parsea fechas de Khan Academy.
    NO guarda nada en disco local.
    """
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
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    all_data = pd.concat(dfs, ignore_index=True)
    all_data.columns = [str(c).strip() for c in all_data.columns]

    if 'Nombre del estudiante' in all_data.columns:
        all_data['Nombre del estudiante'] = all_data['Nombre del estudiante'].astype(str).str.strip()

    if 'Tipo de tarea' in all_data.columns:
        all_data['Tipo de tarea'] = all_data['Tipo de tarea'].astype(str).str.strip()

    if 'Fecha de entrega' in all_data.columns:
        all_data['dt_entrega'] = all_data['Fecha de entrega'].apply(parse_khan_date)
    else:
        all_data['dt_entrega'] = pd.NaT

    if 'Última fecha de terminación' in all_data.columns:
        all_data['dt_terminacion'] = all_data['Última fecha de terminación'].apply(parse_khan_date)
    else:
        all_data['dt_terminacion'] = pd.NaT

    if 'Fecha de inicio' in all_data.columns:
        all_data['dt_inicio'] = all_data['Fecha de inicio'].apply(parse_khan_date)
    else:
        all_data['dt_inicio'] = pd.NaT

    return all_data


def load_teacher_assignments(folder_id, criteria_config=None):
    """
    Carga las asignaciones del docente y les aplica la calificación dinámica según criteria_config.
    """
    raw_df = load_teacher_raw_assignments(folder_id)
    if raw_df.empty:
        return raw_df
    if criteria_config is None:
        unique_types = sorted([t for t in raw_df['Tipo de tarea'].dropna().unique() if t]) if 'Tipo de tarea' in raw_df.columns else []
        criteria_config = load_criteria_config(unique_types)
    return apply_dynamic_grading(raw_df.copy(), criteria_config)




def compute_student_block_grades(assignments_df):
    """
    Calcula la calificación por bloque (Fecha de entrega) para cada estudiante y grupo:
    Block Grade = (Sum(Puntos Ganados) / Sum(Puntos Posibles)) * 10
    Redondeado a 1 decimal.
    Si todas las tareas del bloque son futuras (status == 'Programada' y max_points == 0),
    la calificación del bloque se marca como NaN para no afectar el promedio del estudiante.
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
        parcial=('Parcial', 'first') if 'Parcial' in assignments_df.columns else ('dt_entrega', 'first'),
        all_future=('status', lambda s: (s == 'Programada').all() if len(s) > 0 else False)
    )

    def calc_grade(r):
        if r['max_sum'] > 0:
            return round((r['earned_sum'] / r['max_sum'] * 10.0), 1)
        elif r.get('all_future', False):
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
        criteria_config = load_criteria_config(available_types)

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
    active_tasks = total_tasks - future_tasks
    completed_tasks = active_data['is_completed'].sum()
    late_tasks = active_data['is_late'].sum()
    ontime_tasks = completed_tasks - late_tasks

    # Promedio del estudiante para el filtro activo (excluyendo bloques futuros)
    active_blocks = compute_student_block_grades(active_data)
    valid_blocks = active_blocks['block_grade'].dropna()
    overall_avg = valid_blocks.mean() if not valid_blocks.empty else 0.0

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
        caption_future = f"<div style='font-size:0.75rem; color:#64748b; margin-top:2px;'>({future_tasks} programadas)</div>" if future_tasks > 0 else ""
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
        is_block_all_future = (block_df['status'] == 'Programada').all() if not block_df.empty else False

        if block_max_total > 0:
            block_grade = round((block_earned_total / block_max_total * 10.0), 1)
            grade_str = f"{block_grade:.1f}"
            grade_color = '#16a34a' if block_grade >= 7.0 else '#dc2626'
            progress_val = min(1.0, max(0.0, block_grade / 10.0))
            pts_display = f"<strong>{block_earned_total:.1f} / {block_max_total:.1f}</strong>"
            grade_suffix = "<span style='font-size: 0.95rem; color: #64748b;'> / 10</span>"
        elif is_block_all_future:
            block_grade = None
            grade_str = "Programada"
            grade_color = '#64748b'
            progress_val = 0.0
            pts_display = "<span style='color: #64748b; font-style: italic;'>Pendiente de inicio</span>"
            grade_suffix = ""
        else:
            block_grade = 0.0
            grade_str = "0.0"
            grade_color = '#dc2626'
            progress_val = 0.0
            pts_display = f"<strong>{block_earned_total:.1f} / {block_max_total:.1f}</strong>"
            grade_suffix = "<span style='font-size: 0.95rem; color: #64748b;'> / 10</span>"

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
                        📅 Fecha de Entrega: <strong>{due_date_str}</strong>
                        <span class="badge-parcial">{parcial_tag}</span>
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
            if row['status'] == 'Programada':
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

    # Acordeón de reglas con criterios activos dinámicos
    with st.expander("ℹ️ ¿Cómo se calculan los puntos ponderados y penalizaciones?"):
        st.markdown(render_criteria_explanation(criteria_config))


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

    col1, col2, col3 = st.columns([1, 2.4, 1])
    with col2:
        st.markdown("### Acceso al Portal")
        tab_student, tab_teacher = st.tabs(["🎓 Acceso Estudiantes", "🛡️ Acceso Docentes"])

        # ----------------------------------------------------------------------
        # 1. ACCESO ESTUDIANTES (AISLAMIENTO POR ASIGNATURA / DOCENTE)
        # ----------------------------------------------------------------------
        with tab_student:
            st.caption("Selecciona tu asignatura e ingresa con tu usuario y contraseña de Khan Academy:")

            # Opciones de asignaturas disponibles desde docentes.xlsx
            if not docentes_df.empty and 'asignatura' in docentes_df.columns:
                available_asigs = sorted([a for a in docentes_df['asignatura'].unique() if str(a).strip()])
            else:
                available_asigs = ["Temas Selectos de Matemáticas II"]

            selected_asig = st.selectbox(
                "Asignatura / Materia:",
                options=available_asigs,
                key="student_asig_selector"
            )

            with st.form("student_login_form", clear_on_submit=False):
                username_input = st.text_input("Usuario Khan Academy", placeholder="ej. alboresclementepaulo", key="login_st_user").strip()
                password_input = st.text_input("Contraseña", type="password", placeholder="••••••••", key="login_st_pass").strip()
                submit_st_btn = st.form_submit_button("Ingresar como Estudiante", use_container_width=True, type="primary")

                if submit_st_btn:
                    if not username_input or not password_input:
                        st.error("Por favor completa tu usuario y contraseña.")
                    else:
                        folder_id = None
                        folder_name = ""
                        if not docentes_df.empty:
                            matched_asig = docentes_df[docentes_df['asignatura'] == selected_asig]
                            if not matched_asig.empty:
                                folder_name = matched_asig.iloc[0]['carpeta_nombre']
                                if service and not str(ROOT_FOLDER_ID).startswith('PEGA_AQUÍ'):
                                    t_item = find_drive_item(service, folder_name, ROOT_FOLDER_ID, is_folder=True)
                                    if t_item:
                                        folder_id = t_item['id']
                                    else:
                                        st.error(f"No se localizó la subcarpeta '{folder_name}' en Google Drive para la materia seleccionada.")
                                        return

                        creds_df = load_teacher_credentials(folder_id)
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
                                st.session_state['asignatura'] = selected_asig
                                st.session_state['carpeta_nombre'] = folder_name
                                st.session_state['teacher_folder_id'] = folder_id
                                st.success(f"Bienvenido(a), {student_name}")
                                st.rerun()
                            else:
                                st.error("Usuario o contraseña incorrectos para la asignatura seleccionada.")
                        else:
                            st.error(f"No se encontraron credenciales para la asignatura '{selected_asig}'. Contacta al docente.")

        # ----------------------------------------------------------------------
        # 2. ACCESO DOCENTES (ENRUTAMIENTO MAESTRO)
        # ----------------------------------------------------------------------
        with tab_teacher:
            st.caption("Ingresa con tu usuario y contraseña de docente registrados en docentes.xlsx:")

            with st.form("teacher_login_form", clear_on_submit=False):
                doc_user_input = st.text_input("Usuario Docente", placeholder="ej. docente_tsm o javier_admin", key="login_doc_user").strip()
                doc_pass_input = st.text_input("Contraseña", type="password", placeholder="••••••••", key="login_doc_pass").strip()
                submit_doc_btn = st.form_submit_button("Ingresar al Panel Docente", use_container_width=True, type="primary")

                if submit_doc_btn:
                    if not doc_user_input or not doc_pass_input:
                        st.error("Por favor completa ambos campos.")
                    else:
                        matched_doc = pd.DataFrame()
                        if not docentes_df.empty:
                            matched_doc = docentes_df[
                                (docentes_df['usuario_docente'].str.lower() == doc_user_input.lower()) &
                                (docentes_df['password'] == doc_pass_input)
                            ]

                        if not matched_doc.empty:
                            doc_row = matched_doc.iloc[0]
                            folder_name = doc_row['carpeta_nombre']
                            asig_name = doc_row['asignatura']
                            folder_id = None
                            if service and not str(ROOT_FOLDER_ID).startswith('PEGA_AQUÍ'):
                                t_item = find_drive_item(service, folder_name, ROOT_FOLDER_ID, is_folder=True)
                                if t_item:
                                    folder_id = t_item['id']
                                else:
                                    st.error(f"No se encontró la subcarpeta '{folder_name}' en Google Drive para este docente.")
                                    return

                            st.session_state['logged_in'] = True
                            st.session_state['role'] = 'admin'
                            st.session_state['username'] = doc_row['usuario_docente']
                            st.session_state['student_name'] = f"Prof. {doc_row['usuario_docente']}"
                            st.session_state['asignatura'] = asig_name
                            st.session_state['carpeta_nombre'] = folder_name
                            st.session_state['teacher_folder_id'] = folder_id
                            st.success(f"Bienvenido(a), Prof. {doc_row['usuario_docente']}")
                            st.rerun()

                        elif doc_user_input == ADMIN_USERNAME and doc_pass_input == ADMIN_PASSWORD:
                            st.session_state['logged_in'] = True
                            st.session_state['role'] = 'admin'
                            st.session_state['username'] = ADMIN_USERNAME
                            st.session_state['student_name'] = "Profesor / Administrador General"
                            st.session_state['asignatura'] = "Temas Selectos de Matemáticas II"
                            st.session_state['carpeta_nombre'] = "datos (Local)"
                            st.session_state['teacher_folder_id'] = None
                            st.success("Acceso concedido como Administrador Maestro.")
                            st.rerun()

                        else:
                            st.error("Credenciales de docente no válidas.")

        st.info("💡 **Estudiantes:** Seleccionen su materia y utilicen su cuenta de Khan Academy.\n\n"
                "🛡️ **Docentes:** Inicien sesión con sus credenciales maestras.")


# ==============================================================================
# VISTA: PANEL DE ADMINISTRADOR / DOCENTE
# ==============================================================================
def render_admin():
    teacher_folder_id = st.session_state.get('teacher_folder_id')
    asignatura = st.session_state.get('asignatura', 'Temas Selectos de Matemáticas II')
    carpeta_nombre = st.session_state.get('carpeta_nombre', 'Google Drive')

    header_col1, header_col2 = st.columns([5, 1])
    with header_col1:
        st.markdown(f"""
        <div class="main-header" style="background: linear-gradient(135deg, #0f172a 0%, #334155 100%);">
            <h1>🛡️ Panel Docente - {asignatura}</h1>
            <p>Docente: <strong>{st.session_state.get('username', 'Profesor')}</strong> | Carpeta Drive: <code>{carpeta_nombre}</code> | Sincronización en memoria</p>
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # Cargar datos base crudos aislados de la carpeta del docente
    raw_assignments = load_teacher_raw_assignments(teacher_folder_id)
    all_credentials = load_teacher_credentials(teacher_folder_id)
    saved_parcial_config = load_parciales_config()

    # Detectar dinámicamente los tipos de tarea presentes en los datos
    if not raw_assignments.empty and 'Tipo de tarea' in raw_assignments.columns:
        unique_task_types = sorted([
            t for t in raw_assignments['Tipo de tarea'].dropna().astype(str).str.strip().unique()
            if t
        ])
    else:
        unique_task_types = ['Video', 'Ejercicio', 'Artículo']

    saved_criteria_config = load_criteria_config(unique_task_types)


    # --------------------------------------------------------------------------
    # SECCIÓN 1: CONFIGURACIONES (CRITERIOS, PARCIALES Y CARGA DE ARCHIVOS)
    # --------------------------------------------------------------------------
    with st.expander("⚙️ Configuración de Criterios de Evaluación", expanded=False):
        st.caption("Configura en tiempo real los puntajes a tiempo, tardíos, multiplicación por aciertos y límite de intentos libres para cada tipo de tarea detectado en los datos.")

        current_criteria = {}
        for t_idx, task_type in enumerate(unique_task_types):
            cfg_t = saved_criteria_config.get(task_type, {})
            st.markdown(f"##### 📌 Tipo de Tarea: `{task_type}`")
            c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 2, 1.8, 1.8])
            with c1:
                v_tiempo = st.number_input(
                    "Valor a tiempo",
                    min_value=0.0,
                    value=float(st.session_state.get(f"crit_ot_{task_type}", cfg_t.get('valor_a_tiempo', 1.0))),
                    step=0.5,
                    key=f"crit_ot_{task_type}"
                )
            with c2:
                v_tardio = st.number_input(
                    "Valor tardío",
                    min_value=0.0,
                    value=float(st.session_state.get(f"crit_lt_{task_type}", cfg_t.get('valor_tardio', 0.1))),
                    step=0.05,
                    key=f"crit_lt_{task_type}"
                )
            with c3:
                st.write("")
                st.write("")
                mult = st.checkbox(
                    "Multiplicar por aciertos",
                    value=bool(st.session_state.get(f"crit_mult_{task_type}", cfg_t.get('multiplicar_por_aciertos', False))),
                    key=f"crit_mult_{task_type}",
                    help="Si se activa, el valor base se multiplica por las preguntas correctas. Si no, es un puntaje fijo (ej. videos o lecturas)."
                )
            with c4:
                st.write("")
                st.write("")
                eval_int = st.checkbox(
                    "Evaluar intentos",
                    value=bool(st.session_state.get(f"crit_eval_int_{task_type}", cfg_t.get('evaluar_intentos', False))),
                    key=f"crit_eval_int_{task_type}",
                    help="Si se activa, se penalizan los intentos que excedan el límite configurado."
                )
            with c5:
                max_int = st.number_input(
                    "Máx. intentos libres",
                    min_value=1,
                    max_value=10,
                    value=int(st.session_state.get(f"crit_max_int_{task_type}", cfg_t.get('max_intentos', 3))),
                    step=1,
                    disabled=not eval_int,
                    key=f"crit_max_int_{task_type}",
                    help="Intentos libres permitidos. Cada intento adicional resta 1 acierto. Si es tardía y supera este límite, la nota es 0."
                )

            current_criteria[task_type] = {
                'valor_a_tiempo': v_tiempo,
                'valor_tardio': v_tardio,
                'multiplicar_por_aciertos': mult,
                'evaluar_intentos': eval_int,
                'max_intentos': max_int
            }
            if t_idx < len(unique_task_types) - 1:
                st.divider()

        st.write("")
        b_col1, b_col2, _ = st.columns([1.5, 1.8, 3])
        with b_col1:
            if st.button("💾 Guardar Criterios", type="primary", use_container_width=True, key="save_crit_btn"):
                save_criteria_config(current_criteria)
                st.session_state['active_criteria_config'] = current_criteria
                st.success("✅ Criterios guardados permanentemente en config_criterios.json.")
                st.rerun()
        with b_col2:
            if st.button("🔄 Restablecer Predeterminados", use_container_width=True, key="reset_crit_btn"):
                defaults = get_default_criteria_config(unique_task_types)
                save_criteria_config(defaults)
                for t in unique_task_types:
                    st.session_state[f"crit_ot_{t}"] = defaults[t]['valor_a_tiempo']
                    st.session_state[f"crit_lt_{t}"] = defaults[t]['valor_tardio']
                    st.session_state[f"crit_mult_{t}"] = defaults[t]['multiplicar_por_aciertos']
                    st.session_state[f"crit_eval_int_{t}"] = defaults[t]['evaluar_intentos']
                    st.session_state[f"crit_max_int_{t}"] = defaults[t]['max_intentos']
                st.session_state['active_criteria_config'] = defaults
                st.info("Valores predeterminados restablecidos.")
                st.rerun()

    col_cfg1, col_cfg2 = st.columns(2)

    with col_cfg1:
        with st.expander("📅 Configuración de Parciales (Periodos)", expanded=False):
            st.write("Define las fechas límite de inicio y fin para cada uno de los 3 Parciales del semestre:")
            with st.form("form_parciales"):
                cp1_col1, cp1_col2 = st.columns(2)
                with cp1_col1:
                    p1_s = st.date_input("Inicio Parcial 1", value=saved_parcial_config['Parcial 1']['start'])
                    p2_s = st.date_input("Inicio Parcial 2", value=saved_parcial_config['Parcial 2']['start'])
                    p3_s = st.date_input("Inicio Parcial 3", value=saved_parcial_config['Parcial 3']['start'])
                with cp1_col2:
                    p1_e = st.date_input("Fin Parcial 1", value=saved_parcial_config['Parcial 1']['end'])
                    p2_e = st.date_input("Fin Parcial 2", value=saved_parcial_config['Parcial 2']['end'])
                    p3_e = st.date_input("Fin Parcial 3", value=saved_parcial_config['Parcial 3']['end'])

                save_p_btn = st.form_submit_button("💾 Guardar Fechas de Parciales", type="primary")
                if save_p_btn:
                    new_cfg = {
                        'Parcial 1': {'start': p1_s, 'end': p1_e},
                        'Parcial 2': {'start': p2_s, 'end': p2_e},
                        'Parcial 3': {'start': p3_s, 'end': p3_e}
                    }
                    save_parciales_config(new_cfg)
                    st.session_state['active_parcial_config'] = new_cfg
                    st.cache_data.clear()
                    st.success("✅ Fechas de Parciales guardadas exitosamente.")
                    st.rerun()

    # Configuración de parciales activa (session_state o guardada)
    active_parcial_config = st.session_state.get('active_parcial_config', saved_parcial_config)

    with col_cfg2:
        with st.expander("☁️ Sincronización y Carga en Google Drive", expanded=False):
            st.markdown(f"**Carpeta asignada en Google Drive:** `{carpeta_nombre}`")
            if teacher_folder_id:
                st.success("🟢 Conectado a Google Drive.")
                st.caption("Los archivos se leen y almacenan directamente en la nube sin guardarse en el servidor.")
            else:
                st.info("ℹ️ Sesión en modo local/administrador general.")

            if st.button("🔄 Sincronizar / Refrescar Datos de Drive", use_container_width=True, key="admin_refresh_drive_btn"):
                st.cache_data.clear()
                st.success("✅ Datos sincronizados directamente desde Google Drive.")
                st.rerun()

            st.markdown("---")
            st.markdown("##### 📤 Subir Archivos a Google Drive")
            st.caption("Guarda nuevos archivos directamente en tu carpeta de Google Drive:")
            tab_up_csv, tab_up_cred = st.tabs(["📊 Subir Tareas CSV", "🔑 Subir Credenciales"])

            with tab_up_csv:
                up_csvs = st.file_uploader(
                    "Selecciona CSVs de Khan Academy:",
                    type=["csv"],
                    accept_multiple_files=True,
                    key="drive_csv_uploader"
                )
                if up_csvs:
                    if st.button("☁️ Guardar Tareas en Google Drive", use_container_width=True, key="save_drive_csv_btn"):
                        service = get_drive_service()
                        success_count = 0
                        for f in up_csvs:
                            if service and teacher_folder_id:
                                ok, msg = upload_file_to_drive(service, f.getvalue(), f.name, teacher_folder_id, mime_type='text/csv')
                                if ok:
                                    success_count += 1
                                else:
                                    st.error(msg)
                            else:
                                os.makedirs(DATA_DIR, exist_ok=True)
                                with open(os.path.join(DATA_DIR, f.name), "wb") as out_f:
                                    out_f.write(f.getbuffer())
                                success_count += 1
                        if success_count > 0:
                            st.cache_data.clear()
                            st.success(f"✅ Se guardaron {success_count} archivo(s) en Google Drive.")
                            st.rerun()

            with tab_up_cred:
                up_cred = st.file_uploader(
                    "Archivo de credenciales (.xlsx o .csv):",
                    type=["xlsx", "csv"],
                    accept_multiple_files=False,
                    key="drive_cred_uploader"
                )
                if up_cred:
                    if st.button("☁️ Guardar Credenciales en Google Drive", use_container_width=True, key="save_drive_cred_btn"):
                        service = get_drive_service()
                        file_name = "credenciales.xlsx" if up_cred.name.endswith(".xlsx") else up_cred.name
                        file_bytes = up_cred.getvalue()
                        if service and teacher_folder_id:
                            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if file_name.endswith('.xlsx') else 'text/csv'
                            ok, msg = upload_file_to_drive(service, file_bytes, file_name, teacher_folder_id, mime_type=mime)
                            if ok:
                                st.cache_data.clear()
                                st.success("✅ Credenciales guardadas en Google Drive exitosamente.")
                                st.rerun()
                            else:
                                st.error(msg)
                        else:
                            os.makedirs(DATA_DIR, exist_ok=True)
                            dest = os.path.join(DATA_DIR, "credenciales.xlsx")
                            if up_cred.name.endswith(".xlsx"):
                                with open(dest, "wb") as out_f:
                                    out_f.write(up_cred.getbuffer())
                            else:
                                tdf = pd.read_csv(up_cred, encoding='utf-8-sig')
                                tdf.to_excel(dest, index=False)
                            st.cache_data.clear()
                            st.success("✅ Credenciales guardadas localmente.")
                            st.rerun()

    st.divider()

    # --------------------------------------------------------------------------
    # SECCIÓN 2: MASTER DASHBOARD CON CLASIFICACIÓN DE RENDIMIENTO (ESTATUS)
    # --------------------------------------------------------------------------
    st.markdown("### 📊 Master Dashboard de Calificaciones")
    st.caption("Concentrado de calificaciones por bloques con estatus de desempeño y filtros por Grupo y Parcial.")

    if raw_assignments.empty:
        st.warning("No hay tareas registradas en la carpeta `datos/`.")
        return

    # Criterios activos (en tiempo real desde widgets o guardados)
    active_criteria_config = current_criteria if current_criteria else saved_criteria_config

    # Calificación dinámica en tiempo real según los criterios activos
    all_assignments = apply_dynamic_grading(raw_assignments.copy(), active_criteria_config)

    # CRÍTICO: Asignar Parciales vectorialmente comparando .dt.date contra datetime.date
    assignments_tagged = assign_parciales_vectorized(all_assignments.copy(), active_parcial_config)


    # Grupos disponibles
    available_groups = sorted([g for g in assignments_tagged['Grupo'].dropna().unique() if g])

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
        active_master = assignments_tagged[assignments_tagged['Grupo'].isin(selected_groups)].copy()
    else:
        active_master = assignments_tagged.copy()

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

    # Construir tabla pivote base
    pivot_df = block_summary.pivot(
        index=['Grupo', 'Nombre del estudiante'],
        columns='Fecha de entrega',
        values='block_grade'
    ).reset_index()

    # Columnas de fecha existentes en el pivote
    existing_date_cols = [c for c in date_order if c in pivot_df.columns]

    # Calcular Promedio General del estudiante a través de todos los bloques disponibles (omitiendo bloques futuros)
    numeric_only = pivot_df[existing_date_cols]
    pivot_df['Promedio General'] = numeric_only.mean(axis=1, skipna=True).round(1).fillna(0.0)

    # NUEVO: Crear columna 'Estatus' que clasifica al estudiante según su promedio general
    pivot_df['Estatus'] = pivot_df['Promedio General'].apply(classify_student)

    # Organizar columnas: 'Estatus' al lado del nombre del estudiante
    column_arrangement = ['Grupo', 'Nombre del estudiante', 'Estatus'] + existing_date_cols + ['Promedio General']
    pivot_df = pivot_df[column_arrangement]

    # Búsqueda por nombre si se especificó
    if search_student:
        pivot_df = pivot_df[pivot_df['Nombre del estudiante'].str.contains(search_student, case=False, na=False)]

    # --------------------------------------------------------------------------
    # MÉTRICAS Y RESUMEN RÁPIDO DE LAS 5 CATEGORÍAS DE RENDIMIENTO
    # --------------------------------------------------------------------------
    st.markdown("#### 🎯 Distribución de Rendimiento Académico")
    estatus_counts = pivot_df['Estatus'].value_counts()
    c_exc = int(estatus_counts.get('Excelente', 0))
    c_bien = int(estatus_counts.get('Bien', 0))
    c_reg = int(estatus_counts.get('Regular', 0))
    c_mal = int(estatus_counts.get('Mal', 0))
    c_riesgo = int(estatus_counts.get('En riesgo', 0))
    total_st = len(pivot_df)

    col_e1, col_e2, col_e3, col_e4, col_e5 = st.columns(5)
    with col_e1:
        pct = (c_exc / total_st * 100) if total_st else 0
        st.metric("🌟 Excelente (≥ 9.5)", f"{c_exc}", f"{pct:.0f}% alumnos")
    with col_e2:
        pct = (c_bien / total_st * 100) if total_st else 0
        st.metric("👍 Bien (8.5 - 9.4)", f"{c_bien}", f"{pct:.0f}% alumnos")
    with col_e3:
        pct = (c_reg / total_st * 100) if total_st else 0
        st.metric("👌 Regular (7.0 - 8.4)", f"{c_reg}", f"{pct:.0f}% alumnos")
    with col_e4:
        pct = (c_mal / total_st * 100) if total_st else 0
        st.metric("⚠️ Mal (6.0 - 6.9)", f"{c_mal}", f"{pct:.0f}% alumnos")
    with col_e5:
        pct = (c_riesgo / total_st * 100) if total_st else 0
        st.metric("🚨 En riesgo (< 6.0)", f"{c_riesgo}", f"{pct:.0f}% alumnos")

    st.write("")

    # Formateo de visualización de notas
    display_pivot = pivot_df.copy()
    for col in existing_date_cols:
        display_pivot[col] = display_pivot[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "Programada")
    display_pivot['Promedio General'] = display_pivot['Promedio General'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "0.0")

    # Renderizar la tabla pivote con Estatus inmediatamente después del nombre
    st.dataframe(
        display_pivot,
        use_container_width=True,
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

    # Calcular promedio del estudiante en todos los bloques (omitiendo futuros)
    st_blocks = compute_student_block_grades(student_tasks_data)
    valid_st_blocks = st_blocks['block_grade'].dropna()
    st_avg = valid_st_blocks.mean() if not valid_st_blocks.empty else 0.0
    st_estatus = classify_student(st_avg)

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
    st.markdown("#### 📋 Listado Completo de Actividades del Alumno")
    st.caption("Semáforo de detección rápida: 🟥 **Rojo tenue:** Calificación de 0 puntos (sin entrega o penalizada) | 🟨 **Amarillo tenue:** Actividad realizada con intentos que superan el límite permitido | ⚪ **Gris/Cursiva:** Actividad futura programada.")

    # Ordenar por fecha de entrega y nombre
    all_tasks_sorted = student_tasks_data.sort_values(by=['dt_entrega', 'Nombre de la tarea']).copy()

    # Columnas requeridas: 'Nombre de la tarea', 'Tipo', 'Parcial', 'Fecha de entrega', 'Número de intentos', 'Puntos Obtenidos'
    drill_rows = []
    for _, task_r in all_tasks_sorted.iterrows():
        is_prog = (task_r.get('status') == 'Programada')
        if is_prog:
            pts_display = "Programada"
            attempts_display = "—"
        else:
            pts_display = f"{task_r['earned_points']:.1f}"
            raw_att = task_r.get('Número de intentos')
            attempts_display = str(raw_att) if pd.notna(raw_att) and str(raw_att).strip() not in ['', 'En progreso'] else ("1" if task_r.get('is_completed') else "0")

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
        if status == 'Programada':
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
        use_container_width=True,
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
    with st.expander("👁️ Ver Vista Detallada por Bloques (Vista del Estudiante)", expanded=True):
        render_student_dashboard(selected_student, student_tasks_data, criteria_config=active_criteria_config, is_admin_drilldown=True)


# ==============================================================================
# VISTA: ESTUDIANTE (DASHBOARD PERSONALIZADO)
# ==============================================================================
def render_student():
    student_name = st.session_state.get('student_name', '')
    username = st.session_state.get('username', '')
    asignatura = st.session_state.get('asignatura', 'Temas Selectos de Matemáticas II')
    teacher_folder_id = st.session_state.get('teacher_folder_id')

    # Cargar datos crudos exclusivamente de la carpeta de la asignatura/docente en Drive
    raw_assignments = load_teacher_raw_assignments(teacher_folder_id)
    if not raw_assignments.empty and 'Tipo de tarea' in raw_assignments.columns:
        unique_task_types = sorted([
            t for t in raw_assignments['Tipo de tarea'].dropna().astype(str).str.strip().unique()
            if t
        ])
    else:
        unique_task_types = ['Video', 'Ejercicio', 'Artículo']

    saved_criteria_config = load_criteria_config(unique_task_types)
    all_assignments = apply_dynamic_grading(raw_assignments.copy(), saved_criteria_config)
    active_parcial_config = load_parciales_config()

    # CRÍTICO: Asignar Parciales vectorialmente comparando .dt.date contra datetime.date
    assignments_tagged = assign_parciales_vectorized(all_assignments.copy(), active_parcial_config)

    student_tasks = assignments_tagged[assignments_tagged['Nombre del estudiante'].str.strip() == student_name.strip()]
    student_group = student_tasks['Grupo'].iloc[0] if not student_tasks.empty else ""

    header_col1, header_col2 = st.columns([5, 1])
    with header_col1:
        st.markdown(f"""
        <div class="main-header">
            <h1>🎓 Calificaciones: {student_name}</h1>
            <p>Grupo: <strong>{student_group}</strong> | Usuario: <code>{username}</code> | Asignatura: <strong>{asignatura}</strong></p>
        </div>
        """, unsafe_allow_html=True)
    with header_col2:
        st.write("")
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    if all_assignments.empty:
        st.warning("No hay tareas registradas en el sistema para esta asignatura. Contacta al docente.")
        return

    render_student_dashboard(student_name, student_tasks, criteria_config=saved_criteria_config, is_admin_drilldown=False)



# ==============================================================================
# CONTROLADOR PRINCIPAL
# ==============================================================================
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['username'] = None
        st.session_state['student_name'] = None
        st.session_state['asignatura'] = None
        st.session_state['carpeta_nombre'] = None
        st.session_state['teacher_folder_id'] = None

    if not st.session_state['logged_in']:
        render_login()
    else:
        if st.session_state.get('role') == 'admin':
            render_admin()
        else:
            render_student()



if __name__ == "__main__":
    main()
