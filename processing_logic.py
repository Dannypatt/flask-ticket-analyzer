# processing_logic.py
import pandas as pd
import time
import re
import os
from bs4 import BeautifulSoup
import ollama
import logging
import traceback
import concurrent.futures
import threading
from typing import Optional, Tuple, List, Dict, Any, Callable

# --- Constantes ---
LLM_MODEL_GEMMA: str = 'gemma3'
REQUIRED_COLUMNS: List[str] = [
    'Number', 'Priority', 'State', 'Assigned to', 'Short description',
    'Task type', 'Subcategory', 'Closed', 'Created', 'Assignment group',
    'Work notes list', 'Work notes', 'Description'
]
MAX_RETRIES: int = 3
RETRY_DELAY: int = 5
MAX_WORKERS: int = 4

EMPTY_TEXT_MARKER: str = "TEXTO_VACIO"
PROCESSING_ERROR_MARKER: str = "ERROR_PROCESAMIENTO_INTERNO"
OLLAMA_ERROR_PREFIX: str = "ERROR_OLLAMA_"
UNEXPECTED_ERROR_PREFIX: str = "ERROR_INESPERADO_"
LENGTH_MISMATCH_MARKER: str = "ERROR_LONGITUD_RESULTADOS"
CANCELLED_MARKER: str = "OPERACION_CANCELADA"

# --- PROMPT MODIFICADO ---
PROMPT_GEMMA_SUMMARY: str = """
Eres un asistente experto en análisis de tickets de IT. Resume el siguiente ticket de forma concisa para análisis de tendencias futuras. Enfócate en:
- Puntos clave técnicos del problema o solicitud.
- Posible causa raíz si es identificable.
- Acciones técnicas realizadas si se mencionan.
Formato de salida: Lista de viñetas (- Punto 1). Sé breve y directo.
Ticket:
{ticket_text}
Resumen conciso:
"""

# --- PROMPT DE CLASIFICACIÓN MODIFICADO ---
PROMPT_GEMMA_CLASSIFICATION: str = """
Eres un analista de soporte IT experimentado. Tu tarea es clasificar el siguiente ticket en UNA categoría principal concisa que describa el área o tipo de problema/solicitud. Sé lo más específico posible.

**Contexto Adicional Proporcionado (si aplica):**
{user_context}

Considera este contexto al elegir la categoría. Usa categorías comunes de IT y las específicas del contexto si son relevantes.
Algunos ejemplos generales (puedes usar otras más específicas si encajan mejor):
Gestión de Cuentas, Problema Hardware (PC/Laptop), Problema Hardware (Impresora), Problema Hardware (Otro), Problema Software (Aplicación X), Problema Software (Office), Problema Software (Sistema Operativo), Solicitud Software, Red/Conectividad, Correo Electrónico, Seguridad, Acceso VPN, Impresión, Consulta General, Capacitación, Otros.

**Ticket a Clasificar:**
{ticket_text}

**Categoría Principal:**
"""
# --- FIN PROMPT MODIFICADO ---


# --- Funciones Auxiliares (clean_text, safe_get, call_ollama_with_retry, check_model_exists) ---
# (Sin cambios respecto a la versión anterior completa y corregida, las incluyo por completitud)
def clean_text(text: Optional[Any]) -> str:
    if not isinstance(text, str): return ""
    text = re.sub(r'\[ARGONAUTA\].*?\n', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[INC\w*\]', '', text, flags=re.IGNORECASE)
    try:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text(separator="\n")
    except Exception as e:
        logging.warning(f"BeautifulSoup falló al parsear texto: {e}. Continuando con texto semi-limpio.")
    text = re.sub(r'\s*\n\s*', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def safe_get(dct: Dict, *keys: str) -> Optional[Any]:
    for key in keys:
        try: dct = dct[key]
        except (KeyError, TypeError, IndexError): return None
    return dct

def call_ollama_with_retry(
    model_name: str, prompt: str, cancel_event: Optional[threading.Event] = None,
    max_retries: int = MAX_RETRIES, delay: int = RETRY_DELAY ) -> str:
    retries = 0
    while retries < max_retries:
        if cancel_event and cancel_event.is_set(): return CANCELLED_MARKER
        try:
            response = ollama.chat(model=model_name, messages=[{'role': 'user', 'content': prompt}])
            content = safe_get(response, 'message', 'content')
            if content is None: raise ValueError("Respuesta Ollama sin 'message.content'")
            if not isinstance(content, str): raise ValueError("Respuesta Ollama no es string")
            return content.strip()
        except (ollama.ResponseError, ConnectionError, TimeoutError, ValueError) as e:
            retries += 1
            logging.warning(f"Ollama ({model_name}) Intento {retries}/{max_retries}: {e}")
            if cancel_event and cancel_event.is_set(): return CANCELLED_MARKER
            if retries < max_retries: time.sleep(delay)
            else: return f"{OLLAMA_ERROR_PREFIX}{model_name.replace(':', '_').upper()}"
        except Exception as e:
             retries += 1
             logging.warning(f"Error inesperado Ollama ({model_name}) Intento {retries}/{max_retries}: {e}\n{traceback.format_exc()}")
             if cancel_event and cancel_event.is_set(): return CANCELLED_MARKER
             if retries < max_retries: time.sleep(delay)
             else: return f"{UNEXPECTED_ERROR_PREFIX}{model_name.replace(':', '_').upper()}"
    return f"{UNEXPECTED_ERROR_PREFIX}FALLO_REINTENTOS"

def check_model_exists(model_base_name: str) -> Tuple[bool, Optional[str]]:
    try:
        models_info = ollama.list()
        available_models: List[str] = []
        models_list = []
        if isinstance(models_info, dict) and 'models' in models_info: models_list = models_info['models']
        elif hasattr(models_info, 'models'): models_list = models_info.models
        if isinstance(models_list, list):
             for m in models_list:
                model_name_attr = None
                if isinstance(m, dict) and 'name' in m: model_name_attr = m['name']
                elif isinstance(m, dict) and 'model' in m: model_name_attr = m['model']
                elif hasattr(m, 'model'): model_name_attr = m.model
                elif hasattr(m, 'name'): model_name_attr = m.name
                if model_name_attr and isinstance(model_name_attr, str): available_models.append(model_name_attr)
                else: logging.warning(f"Elemento de modelo inesperado o sin nombre en lista Ollama: {m}")
        else:
            logging.error(f"Respuesta inesperada de ollama.list(): {models_info}")
            return False, None
        for full_name in available_models:
            if full_name == model_base_name or full_name.startswith(model_base_name + ':'):
                logging.info(f"Modelo '{model_base_name}' encontrado como '{full_name}' en Ollama.")
                return True, full_name
        logging.warning(f"Modelo base '{model_base_name}' no encontrado. Disponibles: {available_models}")
        return False, None
    except Exception as e:
        logging.error(f"Error al verificar modelos Ollama: {e}", exc_info=True)
        return False, None

# --- Lógica Principal de Procesamiento ---

# --- MODIFICACIÓN: Añadir user_context ---
def process_single_ticket(
    ticket_data: Any,
    model_name: str,
    user_context: str, # <-- Nuevo parámetro
    cancel_event: threading.Event
    ) -> Tuple[int, str, str]:
    """Procesa un ticket individual, AHORA incluyendo contexto."""
    original_index: int = ticket_data.Index
    ticket_number: str = str(getattr(ticket_data, 'Number', f'Fila_{original_index + 1}'))

    if cancel_event.is_set(): return original_index, CANCELLED_MARKER, CANCELLED_MARKER

    try:
        short_desc = str(getattr(ticket_data, 'Short_description', getattr(ticket_data, 'Short description','')))
        description = str(getattr(ticket_data, 'Description', ''))
        work_notes = str(getattr(ticket_data, 'Work_notes', getattr(ticket_data, 'Work notes','')))

        combined_text = f"Título: {short_desc}\n\nDescripción:\n{description}\n\nNotas de trabajo:\n{work_notes}"
        cleaned_text = clean_text(combined_text)

        if not cleaned_text.strip():
            logging.warning(f"T:{ticket_number} (Índice:{original_index}) - Texto vacío.")
            return original_index, EMPTY_TEXT_MARKER, EMPTY_TEXT_MARKER

        if cancel_event.is_set(): return original_index, CANCELLED_MARKER, CANCELLED_MARKER

        # --- 1. Generar Resumen (sin cambios) ---
        summary_prompt = PROMPT_GEMMA_SUMMARY.format(ticket_text=cleaned_text)
        gemma_summary = call_ollama_with_retry(model_name, summary_prompt, cancel_event)

        if cancel_event.is_set(): return original_index, CANCELLED_MARKER, CANCELLED_MARKER # Re-check

        # --- 2. Generar Clasificación (CON CONTEXTO) ---
        # Preparar contexto para el prompt (si está vacío, poner algo neutral)
        context_for_prompt = user_context if user_context and user_context.strip() else "Ninguno proporcionado."

        # --- MODIFICACIÓN: Formatear prompt de clasificación con contexto ---
        classification_prompt = PROMPT_GEMMA_CLASSIFICATION.format(
            ticket_text=cleaned_text,
            user_context=context_for_prompt # <-- Pasar el contexto
        )
        gemma_classification = call_ollama_with_retry(model_name, classification_prompt, cancel_event)

        # Limpieza de clasificación (sin cambios)
        if not gemma_classification.startswith("ERROR_") and gemma_classification != CANCELLED_MARKER:
             gemma_classification = gemma_classification.lstrip("-* ").strip()

        return original_index, gemma_summary, gemma_classification

    except Exception as e:
        logging.error(f"Error inesperado procesando T:{ticket_number} (Índice: {original_index}): {e}\n{traceback.format_exc()}")
        return original_index, PROCESSING_ERROR_MARKER, PROCESSING_ERROR_MARKER

# --- MODIFICACIÓN: Añadir user_context ---
def process_excel_file(
    input_path: str,
    output_path: str,
    model_name: str,
    user_context: str, # <-- Nuevo parámetro
    task_id: str,
    status_dict: Dict[str, Dict],
    cancel_event: threading.Event
    ) -> None:
    """Función principal del worker: lee, procesa (CON CONTEXTO), guarda y actualiza estado."""
    df: Optional[pd.DataFrame] = None
    summaries_map: Dict[int, str] = {}
    classifications_map: Dict[int, str] = {}
    processed_count: int = 0
    total_tickets: int = 0
    summary_errors: int = 0
    classification_errors: int = 0
    start_time: float = time.time()

    def update_status(status: str, progress: int, error_msg: Optional[str] = None, result_file: Optional[str] = None) -> None:
        status_dict[task_id] = {
            "status": status, "progress": progress, "total": total_tickets,
            "error": error_msg, "result_file": result_file,
            "summary_errors": summary_errors, "classification_errors": classification_errors,
            "time_elapsed": time.time() - start_time
        }
        logging.info(f"Task {task_id} Status Update: {status_dict[task_id]}")

    try:
        update_status("reading", progress=0)
        logging.info(f"Task {task_id}: Leyendo {input_path}")
        try: df = pd.read_excel(input_path, engine='openpyxl')
        except FileNotFoundError: raise ValueError(f"Archivo no encontrado: {input_path}")
        except Exception as e: raise ValueError(f"Error al leer Excel: {e}")

        df.columns = [col.strip() for col in df.columns]
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols: raise ValueError(f"Columnas faltantes: {', '.join(missing_cols)}")
        total_tickets = len(df)
        if total_tickets == 0: raise ValueError("Archivo Excel vacío.")

        logging.info(f"Task {task_id}: {total_tickets} tickets. Modelo: {model_name}. Contexto: '{user_context[:50]}...'")
        update_status("processing", progress=0)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix=f'Task_{task_id}_Worker') as executor:
            futures: Dict[concurrent.futures.Future, int] = {
                # --- MODIFICACIÓN: Pasar user_context a process_single_ticket ---
                executor.submit(process_single_ticket, tr, model_name, user_context, cancel_event): tr.Index
                for tr in df.itertuples(index=True, name='TicketRow')
            }

            for future in concurrent.futures.as_completed(futures):
                if cancel_event.is_set():
                    logging.warning(f"Task {task_id}: Cancelación detectada en as_completed.")
                    break
                original_index = futures[future]
                try:
                    idx, summary_res, classification_res = future.result()
                    summaries_map[original_index] = summary_res
                    classifications_map[original_index] = classification_res

                    if str(summary_res).startswith((OLLAMA_ERROR_PREFIX, UNEXPECTED_ERROR_PREFIX)) or summary_res == PROCESSING_ERROR_MARKER: summary_errors += 1
                    if str(classification_res).startswith((OLLAMA_ERROR_PREFIX, UNEXPECTED_ERROR_PREFIX)) or classification_res == PROCESSING_ERROR_MARKER: classification_errors += 1

                    processed_count += 1
                    if processed_count % 5 == 0 or processed_count == total_tickets:
                         update_status("processing", progress=processed_count)

                except concurrent.futures.CancelledError:
                     logging.warning(f"Task {task_id}: Futuro cancelado idx {original_index}")
                     summaries_map[original_index] = CANCELLED_MARKER
                     classifications_map[original_index] = CANCELLED_MARKER
                except Exception as exc:
                    processed_count += 1
                    logging.error(f"Task {task_id}: Error futuro idx {original_index}: {exc}", exc_info=True)
                    summaries_map[original_index] = f"ERROR_FUTURO: {exc}"
                    classifications_map[original_index] = f"ERROR_FUTURO: {exc}"
                    summary_errors += 1; classification_errors += 1
                    update_status("processing", progress=processed_count)

        if cancel_event.is_set():
            update_status("cancelled", progress=processed_count)
            logging.info(f"Task {task_id}: Proceso cancelado post-pool.")
            return

        update_status("saving", progress=processed_count)
        logging.info(f"Task {task_id}: Guardando resultados...")
        if df is None: raise RuntimeError("DataFrame no disponible.")

        ordered_summaries = [summaries_map.get(i, LENGTH_MISMATCH_MARKER) for i in df.index]
        ordered_classifications = [classifications_map.get(i, LENGTH_MISMATCH_MARKER) for i in df.index]

        if len(ordered_summaries)!= total_tickets or len(ordered_classifications)!= total_tickets:
             logging.error(f"Task {task_id}: Discrepancia longitud final!")

        model_name_base = model_name.split(':')[0].capitalize()
        df[f"Resumen_{model_name_base}"] = ordered_summaries
        df[f"Clasificacion_{model_name_base}"] = ordered_classifications

        try: df.to_excel(output_path, index=False, engine='openpyxl')
        except Exception as e: raise IOError(f"Error al guardar Excel {output_path}: {e}")
        logging.info(f"Task {task_id}: Archivo guardado en {output_path}")

        result_filename = os.path.basename(output_path)
        update_status("completed", progress=processed_count, result_file=result_filename)
        logging.info(f"Task {task_id}: Proceso completado.")

    except (ValueError, IOError, RuntimeError) as ve:
        logging.error(f"Task {task_id}: Error: {ve}")
        update_status("error", progress=processed_count, error_msg=str(ve))
    except Exception as e:
        logging.error(f"Task {task_id}: Error GRAVE inesperado: {e}\n{traceback.format_exc()}")
        update_status("error", progress=processed_count, error_msg=f"Error interno. Task ID: {task_id}")