# app.py
import os
import uuid
import threading
import logging
from flask import Flask, request, render_template, send_from_directory, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from typing import Dict # Asegúrate que está importado
from processing_logic import process_excel_file, check_model_exists, LLM_MODEL_GEMMA

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'xlsx'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.secret_key = os.urandom(24)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

tasks_status: Dict[str, Dict] = {}
tasks_lock = threading.Lock()
cancel_events: Dict[str, threading.Event] = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET'])
def index():
    model_ok, model_name = check_model_exists(LLM_MODEL_GEMMA)
    if not model_ok:
        flash(f"ADVERTENCIA: Modelo '{LLM_MODEL_GEMMA}' no encontrado. El procesamiento fallará.", "warning")
    default_model_name = model_name or LLM_MODEL_GEMMA
    return render_template('index.html', default_model=default_model_name)

@app.route('/upload', methods=['POST'])
def upload_and_process():
    if 'excel_file' not in request.files:
        flash('No se encontró parte del archivo', 'error')
        return redirect(url_for('index'))
    file = request.files['excel_file']
    # --- NUEVO: Obtener contexto del formulario ---
    user_context = request.form.get('user_context', '').strip() # .strip() para quitar espacios extra
    # ----------------------------------------------
    if file.filename == '':
        flash('Ningún archivo seleccionado', 'error')
        return redirect(url_for('index'))

    if file and allowed_file(file.filename):
        model_ok, actual_model = check_model_exists(LLM_MODEL_GEMMA)
        if not model_ok or not actual_model:
             flash(f"ERROR CRÍTICO: Modelo '{LLM_MODEL_GEMMA}' no encontrado o inválido.", "error")
             return redirect(url_for('index'))

        original_filename = secure_filename(file.filename)
        ext = os.path.splitext(original_filename)[1]
        unique_id = str(uuid.uuid4())
        input_filename = f"{unique_id}_input{ext}"
        output_filename = f"{unique_id}_processed{ext}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
        output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)

        try:
            file.save(input_path)
            logging.info(f"Archivo subido: {input_path}")
            if user_context:
                 logging.info(f"Contexto proporcionado: '{user_context[:100]}...'") # Loguear inicio del contexto

            task_id = unique_id
            cancel_event = threading.Event()
            with tasks_lock:
                tasks_status[task_id] = {"status": "queued", "progress": 0, "total": 0, "error": None, "result_file": None}
                cancel_events[task_id] = cancel_event

            # --- MODIFICACIÓN: Pasar user_context a los args del hilo ---
            thread = threading.Thread(
                target=process_excel_file,
                args=(input_path, output_path, actual_model, user_context, task_id, tasks_status, cancel_event), # <-- Añadido user_context
                name=f"TaskThread_{task_id}",
                daemon=True
            )
            # ------------------------------------------------------------
            thread.start()
            logging.info(f"Tarea {task_id} iniciada para {original_filename}")
            return redirect(url_for('processing_page', task_id=task_id))

        except Exception as e:
            logging.error(f"Error al guardar o iniciar tarea: {e}", exc_info=True)
            flash(f"Error al iniciar procesamiento: {e}", "error")
            return redirect(url_for('index'))
    else:
        flash('Tipo de archivo no permitido (.xlsx)', 'error')
        return redirect(url_for('index'))

@app.route('/processing/<task_id>')
def processing_page(task_id):
    return render_template('processing.html', task_id=task_id)

@app.route('/status/<task_id>')
def task_status(task_id):
    with tasks_lock:
        status = tasks_status.get(task_id, {"status": "not_found", "error": "Tarea no encontrada"})
    return jsonify(status)

@app.route('/download/<filename>')
def download_file(filename):
    safe_path = os.path.abspath(app.config['PROCESSED_FOLDER'])
    requested_path = os.path.abspath(os.path.join(safe_path, filename))
    if not requested_path.startswith(safe_path): return "Acceso denegado", 403
    if not os.path.exists(requested_path): return "Archivo no encontrado", 404
    logging.info(f"Descargando: {filename}")
    try: return send_from_directory(app.config['PROCESSED_FOLDER'], filename, as_attachment=True)
    except Exception as e: logging.error(f"Error descarga {filename}: {e}", exc_info=True); return "Error descarga", 500

# --- Punto de Entrada (Sin cambios) ---
if __name__ == '__main__':
    print("Iniciando servidor Flask...")
    app.run(host='0.0.0.0', port=5000, debug=False) # debug=False recomendado