# config.py
import psutil

# --- Ollama Configuration ---
OLLAMA_BASE_URL = "http://localhost:11434"  # Asegúrate que Ollama esté corriendo aquí
OLLAMA_MODEL = "gemma3"  # Modelo por defecto, puedes cambiarlo (e.g., "llama3", "mistral")
# OLLAMA_MODEL = "mistral:latest"
# OLLAMA_MODEL = "llama3:latest"

# --- Processing Configuration ---
# Columnas principales a considerar para el análisis. El usuario podrá seleccionar en la UI.
DEFAULT_COLUMNS_TO_ANALYZE = {
    "description_column": "Description",
    "short_description_column": "Short description",
    "work_notes_column": "Work notes"
}
# Categorías predefinidas para clasificación. Usadas si no hay contexto o la generación dinámica falla.
DEFAULT_CATEGORIES = [
    "Problema Hardware",
    "Problema Software",
    "Gestión de Cuentas",
    "Solicitud de Software",
    "Problema de Red",
    "Problema de Aplicación Interna",
    "Consulta General",
    "Seguridad Informática",
    "Otro"
]

# --- System Configuration ---
# Usar todos los cores lógicos disponibles para el ThreadPoolExecutor
MAX_WORKERS = psutil.cpu_count(logical=True)
# MAX_WORKERS = 2 # Para pruebas

# --- File Management ---
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
MAX_FILE_AGE_SECONDS = 24 * 60 * 60  # 1 día para limpieza de archivos antiguos

# --- HTML Cleaning & Identifier Filtering ---
# Regex para identificadores a excluir del análisis
IDENTIFIER_PATTERNS_TO_EXCLUDE = [
    r"\[ARGONAUTA.*?\]",
    r"\[INC\d+\]",
    r"CRQ\d+"
]