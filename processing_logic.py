# processing_logic.py
import pandas as pd
import requests
import json
import re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import time
import os
from datetime import datetime, timedelta

from config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    IDENTIFIER_PATTERNS_TO_EXCLUDE, UPLOAD_FOLDER, PROCESSED_FOLDER, MAX_FILE_AGE_SECONDS,
    MAX_WORKERS
)

# --- Helper para Limpieza de Texto ---
def clean_html_and_identifiers(text):
    if not isinstance(text, str):
        return ""
    soup = BeautifulSoup(text, "html.parser")
    cleaned_text = soup.get_text(separator=" ")
    for pattern in IDENTIFIER_PATTERNS_TO_EXCLUDE:
        cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text

# --- Interacción con Ollama ---
def call_ollama(prompt_text, model_name=OLLAMA_MODEL, task_type="general", expect_json=False):
    full_url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt_text,
        "stream": False,
        "options": {
            "temperature": 0.3,
        }
    }
    if expect_json:
        payload["format"] = "json"

    response_text_for_error = ""
    try:
        response = requests.post(full_url, json=payload, timeout=180) # 3 minutos timeout
        response_text_for_error = response.text
        response.raise_for_status()
        response_json = response.json()
        raw_llm_response = response_json.get("response", "").strip()

        if expect_json:
            try:
                json_match = re.search(r'\{.*\}', raw_llm_response, re.DOTALL)
                if json_match:
                    parsed_json = json.loads(json_match.group(0))
                    return parsed_json
                else: # Intentar parsear directamente si no hay un bloque JSON claro
                    return json.loads(raw_llm_response)
            except json.JSONDecodeError as je:
                print(f"Error decodificando JSON de Ollama ({task_type}): {je}. Respuesta: {raw_llm_response[:500]}")
                return {"error_parsing_json": f"JSONDecodeError: {str(je)}", "raw_response": raw_llm_response}
        else:
            return raw_llm_response

    except requests.exceptions.RequestException as e:
        print(f"Error llamando a Ollama ({task_type}): {e}. Respuesta: {response_text_for_error[:500]}")
        error_message = f"ERROR_OLLAMA: No se pudo conectar o procesar la solicitud con Ollama. {str(e)}"
        if "model not found" in str(e).lower() or ("no such file or directory" in response_text_for_error.lower() if response_text_for_error else False):
             error_message = f"ERROR_OLLAMA: Modelo '{model_name}' no encontrado."
        return {"error_ollama": error_message} if expect_json else error_message
    except Exception as e:
        print(f"Error inesperado en call_ollama ({task_type}): {e}")
        return {"error_unexpected": str(e)} if expect_json else f"ERROR_OLLAMA: Error inesperado. {str(e)}"


# --- Lógica de Análisis de Ticket Individual ---
def analyze_single_ticket(ticket_content, custom_context, ollama_model):
    expected_keys = [
        "Clasificacion_Sugerida_IA",
        "Problema_Principal_IA",
        "Sintomas_Detectados_IA",
        "Acciones_Realizadas_IA",
        "Causa_Raiz_Estimada_IA",
        "Resumen_General_Conciso_IA"
    ]
    default_values = {key: "No generado por IA" for key in expected_keys}
    default_values["Error_Analisis_IA"] = None

    structured_summary_prompt = (
        f"Eres un asistente experto en análisis de tickets de TI. Analiza el siguiente ticket y proporciona la información en un formato JSON estructurado. "
        f"El objeto JSON debe tener las siguientes claves EXACTAS:\n"
        f"- \"Clasificacion_Sugerida_IA\": Una categoría concisa para el ticket (ej: 'Problema de Software', 'Fallo de Hardware', 'Solicitud de Acceso').\n"
        f"- \"Problema_Principal_IA\": Descripción breve del problema central del ticket.\n"
        f"- \"Sintomas_Detectados_IA\": Síntomas o efectos observables del problema.\n"
        f"- \"Acciones_Realizadas_IA\": Cualquier acción ya tomada por el usuario o soporte mencionada en el ticket.\n"
        f"- \"Causa_Raiz_Estimada_IA\": Una estimación breve de la posible causa raíz, si se puede inferir.\n"
        f"- \"Resumen_General_Conciso_IA\": Un resumen técnico muy breve (1-2 frases) del ticket en general.\n"
        f"Si alguna información no está presente o no se puede inferir del ticket, usa el valor string \"No aplica\" o \"No especificado\" para esa clave.\n"
        f"Contexto Adicional del Entorno: {custom_context if custom_context else 'Ninguno'}\n"
        f"Ticket:\n\"\"\"\n{ticket_content}\n\"\"\"\n"
        f"Respuesta JSON:"
    )

    llm_response = call_ollama(structured_summary_prompt, ollama_model, task_type="structured_summary", expect_json=True)

    if isinstance(llm_response, dict):
        if "error_ollama" in llm_response or "error_unexpected" in llm_response or "error_parsing_json" in llm_response:
            error_val = llm_response.get("error_ollama") or \
                        llm_response.get("error_unexpected") or \
                        llm_response.get("error_parsing_json") or \
                        "Error desconocido en la respuesta de Ollama"
            analysis_result = default_values.copy()
            analysis_result["Error_Analisis_IA"] = str(error_val)
            if "raw_response" in llm_response and analysis_result.get("Resumen_General_Conciso_IA") == "No generado por IA":
                 analysis_result["Resumen_General_Conciso_IA"] = f"Respuesta cruda (error JSON): {llm_response['raw_response'][:200]}"
            return analysis_result
        else:
            analysis_result = {}
            for key in expected_keys:
                analysis_result[key] = llm_response.get(key, default_values[key])
            analysis_result["Error_Analisis_IA"] = None
            return analysis_result
    else:
        analysis_result = default_values.copy()
        analysis_result["Error_Analisis_IA"] = f"Respuesta inesperada de Ollama (no es dict): {str(llm_response)[:200]}"
        return analysis_result


# --- Procesamiento del Archivo Excel ---
def process_excel_file(filepath, original_filename_base, custom_context, selected_columns, ollama_model, update_progress_callback):
    try:
        df = pd.read_excel(filepath)
    except Exception as e:
        msg = f"Error al leer el archivo Excel: {e}"
        update_progress_callback(0, 0, msg, "error")
        return None, {"error": msg}

    num_tickets = len(df)
    if num_tickets == 0:
        update_progress_callback(0, 0, "El archivo Excel está vacío.", "completed")
        return filepath, {"message": "Archivo vacío", "total_tickets": 0}

    analysis_results_list = []
    processed_count = 0
    
    desc_col = selected_columns.get('description_column')
    short_desc_col = selected_columns.get('short_description_column')
    work_notes_col = selected_columns.get('work_notes_column')

    actual_cols_to_use_for_content = []
    if desc_col and desc_col in df.columns: actual_cols_to_use_for_content.append(desc_col)
    if short_desc_col and short_desc_col in df.columns: actual_cols_to_use_for_content.append(short_desc_col)
    if work_notes_col and work_notes_col in df.columns: actual_cols_to_use_for_content.append(work_notes_col)
    
    if not actual_cols_to_use_for_content:
        msg = (f"Error: Ninguna de las columnas de texto especificadas ({desc_col}, {short_desc_col}, {work_notes_col}) "
               f"se encontraron en el archivo Excel o no se proporcionaron. Columnas disponibles: {', '.join(df.columns)}")
        update_progress_callback(0, num_tickets, msg, "error")
        return None, {"error": msg}

    update_progress_callback(0, num_tickets, "Iniciando análisis de tickets...", "processing")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for index, row in df.iterrows():
            ticket_parts = []
            if short_desc_col and short_desc_col in df.columns and pd.notna(row.get(short_desc_col)):
                ticket_parts.append(f"Descripción breve: {clean_html_and_identifiers(str(row[short_desc_col]))}")
            if desc_col and desc_col in df.columns and pd.notna(row.get(desc_col)):
                ticket_parts.append(f"Descripción completa: {clean_html_and_identifiers(str(row[desc_col]))}")
            if work_notes_col and work_notes_col in df.columns and pd.notna(row.get(work_notes_col)):
                ticket_parts.append(f"Notas de trabajo: {clean_html_and_identifiers(str(row[work_notes_col]))}")

            full_ticket_content = " || ".join(ticket_parts)
            if not full_ticket_content.strip():
                full_ticket_content = "Contenido del ticket no disponible o vacío en columnas seleccionadas."
            
            futures.append(executor.submit(analyze_single_ticket, full_ticket_content, custom_context, ollama_model))

        for i, future in enumerate(futures):
            try:
                single_ticket_analysis = future.result()
                analysis_results_list.append(single_ticket_analysis)
            except Exception as e:
                print(f"Error procesando ticket {i} en el futuro: {e}")
                error_result = {
                    "Clasificacion_Sugerida_IA": "Error Futuro", "Problema_Principal_IA": "Error Futuro",
                    "Sintomas_Detectados_IA": "Error Futuro", "Acciones_Realizadas_IA": "Error Futuro",
                    "Causa_Raiz_Estimada_IA": "Error Futuro", "Resumen_General_Conciso_IA": "Error Futuro",
                    "Error_Analisis_IA": f"Error en ThreadPoolExecutor: {str(e)}"
                }
                analysis_results_list.append(error_result)
            processed_count += 1
            update_progress_callback(processed_count, num_tickets, f"Procesando ticket {processed_count}/{num_tickets}", "processing")

    df_analysis_results = pd.DataFrame(analysis_results_list)

    for col in df_analysis_results.columns:
        if col not in df.columns:
             df[col] = df_analysis_results[col]
        else:
            df[f"GenIA_{col}"] = df_analysis_results[col]
    
    category_counts = {}
    recommendations = []
    new_classification_col_name = "Clasificacion_Sugerida_IA"
    if new_classification_col_name in df.columns:
        valid_classifications = df[new_classification_col_name].dropna()
        if not valid_classifications.empty:
            category_counts = valid_classifications.value_counts().to_dict()
            for category, count in category_counts.items():
                if count > (num_tickets * 0.1) and category not in ["Otro", "Error Futuro", "No generado por IA", "No aplica", "No especificado"]:
                    recommendations.append(
                        f"La categoría '{category}' (sugerida por IA) aparece {count} veces ({count/num_tickets*100:.1f}%). "
                        f"Considerar revisar patrones para este tipo."
                    )
        if not recommendations and num_tickets > 0 and not valid_classifications.empty:
            recommendations.append("No se detectaron patrones de alta frecuencia en las categorías sugeridas por IA (>10% del total).")
        elif valid_classifications.empty and num_tickets > 0:
            recommendations.append(f"La columna '{new_classification_col_name}' no contiene clasificaciones válidas para analizar patrones.")

    elif num_tickets > 0 :
         recommendations.append(f"No se pudo generar la columna '{new_classification_col_name}' para el análisis de patrones.")
    
    if num_tickets == 0:
        recommendations.append("No hay tickets para analizar patrones.")
            
    analysis_summary_for_ui = {
        "total_tickets": num_tickets,
        "category_counts": category_counts,
        "recommendations": recommendations,
        "ollama_model_used": ollama_model,
        "custom_context_provided": bool(custom_context),
        "columns_generated_by_ia": list(df_analysis_results.columns)
    }

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    ext = os.path.splitext(filepath)[1]
    processed_filename = f"{original_filename_base}_analizado{ext}"
    processed_filepath = os.path.join(PROCESSED_FOLDER, processed_filename)
    
    try:
        df.to_excel(processed_filepath, index=False)
        update_progress_callback(num_tickets, num_tickets, "Análisis completado. Puede descargar el archivo.", "completed")
    except Exception as e:
        msg = f"Error al guardar el archivo procesado: {e}"
        update_progress_callback(num_tickets, num_tickets, msg, "error")
        analysis_summary_for_ui["error_saving_file"] = str(e)
        return None, analysis_summary_for_ui

    return processed_filepath, analysis_summary_for_ui


# --- Limpieza de Archivos Antiguos ---
def clean_old_files():
    now = datetime.now()
    cutoff = now - timedelta(seconds=MAX_FILE_AGE_SECONDS)
    for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER]:
        if not os.path.exists(folder):
            continue
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if os.path.isfile(filepath):
                try:
                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_mod_time < cutoff:
                        os.remove(filepath)
                        print(f"Archivo antiguo eliminado: {filepath}")
                except Exception as e:
                    print(f"Error procesando para eliminar archivo {filepath}: {e}")