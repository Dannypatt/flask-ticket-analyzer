# app.py
from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import uuid
import threading
import requests
from processing_logic import process_excel_file, clean_old_files
from config import (
    UPLOAD_FOLDER, PROCESSED_FOLDER, OLLAMA_MODEL, DEFAULT_COLUMNS_TO_ANALYZE,
    OLLAMA_BASE_URL
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

tasks_status = {}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

@app.route('/', methods=['GET'])
def index():
    clean_old_files()
    ollama_status = "No disponible"
    ollama_models_available = []
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10) # Aumentado un poco el timeout para la comprobación
        if response.status_code == 200:
            ollama_status = "Disponible"
            models_data = response.json().get("models", [])
            ollama_models_available = sorted([model['name'] for model in models_data])
        else:
            ollama_status = f"Error: {response.status_code} - {response.text[:200]}"
    except requests.exceptions.RequestException as e:
        ollama_status = f"No se pudo conectar a Ollama en {OLLAMA_BASE_URL}. Asegúrate que esté ejecutándose. Detalle: {str(e)[:200]}"

    return render_template('index.html',
                           ollama_model_default=OLLAMA_MODEL,
                           default_cols=DEFAULT_COLUMNS_TO_ANALYZE,
                           ollama_status=ollama_status,
                           ollama_models=ollama_models_available)


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo."}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No se seleccionó ningún archivo."}), 400

    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        original_filename = file.filename
        temp_filename_base = str(uuid.uuid4())
        _, extension = os.path.splitext(original_filename)
        temp_filename = temp_filename_base + extension
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(filepath)

        task_id = str(uuid.uuid4())
        tasks_status[task_id] = {
            "status": "uploaded",
            "message": "Archivo subido, listo para analizar.",
            "original_filename": original_filename, 
            "temp_filename_base": temp_filename_base,
            "filepath_on_server": filepath,
            "processed_filepath_on_server": None,
            "progress_current": 0,
            "progress_total": 1,
            "analysis_summary": None
        }
        return jsonify({
            "message": "Archivo subido exitosamente.",
            "task_id": task_id,
            "filename": original_filename
        }), 200
    else:
        return jsonify({"error": "Formato de archivo no soportado. Por favor, suba un .xlsx o .xls."}), 400


def analysis_thread_target(task_id, filepath_on_server, temp_filename_base, custom_context, selected_columns, ollama_model_to_use):
    def update_progress_local(current, total, message, status_override=None):
        task_data = tasks_status.get(task_id, {})
        task_data["progress_current"] = current
        task_data["progress_total"] = total
        task_data["message"] = message
        if status_override:
             task_data["status"] = status_override
        elif current == total and total > 0:
            task_data["status"] = "completed"
        else:
            task_data["status"] = "processing"
        tasks_status[task_id] = task_data

    try:
        update_progress_local(0, 1, "Hilo de análisis iniciado, preparando...", "processing")
        
        processed_filepath_from_logic, analysis_summary_for_ui = process_excel_file(
            filepath_on_server,
            temp_filename_base,
            custom_context,
            selected_columns,
            ollama_model_to_use,
            update_progress_local
        )
        
        tasks_status[task_id]["analysis_summary"] = analysis_summary_for_ui
        if processed_filepath_from_logic:
            tasks_status[task_id]["processed_filepath_on_server"] = processed_filepath_from_logic
            if tasks_status[task_id]["status"] != "error":
                update_progress_local(tasks_status[task_id]["progress_total"], tasks_status[task_id]["progress_total"], "Análisis finalizado. Resultados listos.", "completed")
        else:
            if tasks_status[task_id]["status"] != "error":
                 update_progress_local(tasks_status[task_id]["progress_current"], tasks_status[task_id]["progress_total"], "El análisis falló al generar el archivo de salida. Revise logs.", "error")
    except Exception as e:
        print(f"Error CRÍTICO en el hilo de análisis para task_id {task_id}: {e}")
        update_progress_local(
            tasks_status.get(task_id, {}).get("progress_current", 0),
            tasks_status.get(task_id, {}).get("progress_total", 1),
            f"Error crítico no manejado en el hilo: {str(e)}", 
            "error"
        )
        if tasks_status.get(task_id):
            tasks_status[task_id]["analysis_summary"] = {"error": f"Error crítico en hilo: {str(e)}"}


@app.route('/analyze/<task_id>', methods=['POST'])
def analyze_tickets_route(task_id):
    if task_id not in tasks_status:
        return jsonify({"error": "ID de tarea no válido."}), 404
    
    task_info = tasks_status[task_id]

    if task_info["status"] == "processing":
         return jsonify({"message": "El análisis ya está en progreso para esta tarea.", "task_id": task_id}), 409

    custom_context = request.form.get('custom_context', '')
    desc_col = request.form.get('description_column', DEFAULT_COLUMNS_TO_ANALYZE['description_column'])
    short_desc_col = request.form.get('short_description_column', DEFAULT_COLUMNS_TO_ANALYZE['short_description_column'])
    work_notes_col = request.form.get('work_notes_column', DEFAULT_COLUMNS_TO_ANALYZE.get('work_notes_column', "Work notes"))
    
    ollama_model_selected = request.form.get('ollama_model_select', OLLAMA_MODEL)

    selected_columns = {
        "description_column": desc_col,
        "short_description_column": short_desc_col,
        "work_notes_column": work_notes_col
    }

    filepath_on_server = task_info["filepath_on_server"]
    temp_filename_base = task_info["temp_filename_base"]

    task_info["status"] = "queued"
    task_info["message"] = "Análisis en cola..."
    task_info["progress_current"] = 0
    task_info["progress_total"] = 1 
    task_info["processed_filepath_on_server"] = None
    task_info["analysis_summary"] = None
    tasks_status[task_id] = task_info

    thread = threading.Thread(target=analysis_thread_target, args=(
        task_id,
        filepath_on_server,
        temp_filename_base,
        custom_context,
        selected_columns,
        ollama_model_selected
    ))
    thread.daemon = True
    thread.start()

    return jsonify({"message": "Análisis iniciado.", "task_id": task_id}), 202

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    if task_id not in tasks_status:
        return jsonify({"error": "ID de tarea no válido."}), 404
    return jsonify(tasks_status[task_id])

@app.route('/download/<task_id>', methods=['GET'])
def download_processed_file(task_id):
    task_info = tasks_status.get(task_id)
    if not task_info or task_info["status"] != "completed":
        return jsonify({"error": "El archivo no está listo o la tarea no fue completada exitosamente."}), 404

    processed_filepath_on_server = task_info.get("processed_filepath_on_server")
    if not processed_filepath_on_server or not os.path.exists(processed_filepath_on_server):
        return jsonify({"error": "Archivo procesado no encontrado en el sistema."}), 404

    original_filename = task_info.get("original_filename", "descarga.xlsx")
    base_orig, ext_orig = os.path.splitext(original_filename)
    download_filename = f"{base_orig}_analizado{ext_orig}"

    return send_from_directory(
        directory=os.path.dirname(processed_filepath_on_server),
        path=os.path.basename(processed_filepath_on_server),
        as_attachment=True,
        download_name=download_filename
    )

if __name__ == '__main__':
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        response.raise_for_status()
        print(f"Ollama parece estar respondiendo en {OLLAMA_BASE_URL}")
    except requests.exceptions.RequestException as e:
        print(f"ADVERTENCIA: No se pudo conectar a Ollama en {OLLAMA_BASE_URL} o la respuesta fue un error. Detalle: {str(e)[:200]}")
    
    app.run(debug=True, host='0.0.0.0', port=5001)