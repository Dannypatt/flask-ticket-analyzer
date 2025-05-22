# config.py
import psutil

# --- Ollama Configuration ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma:2b"  # Modelo por defecto, puedes cambiarlo

# --- Processing Configuration ---
DEFAULT_COLUMNS_TO_ANALYZE = {
    "description_column": "Description",
    "short_description_column": "Short description",
    "work_notes_column": "Work notes"
}
# DEFAULT_CATEGORIES ya no se usa activamente para la clasificación principal,
# ya que ahora la IA sugiere la clasificación en una columna dedicada.
# Podría mantenerse por si se quisiera reintroducir alguna lógica de fallback muy específica.
DEFAULT_CATEGORIES = [
    "Problema Hardware", "Problema Software", "Gestión de Cuentas",
    "Solicitud de Software", "Problema de Red", "Otro"
]


# --- System Configuration ---
MAX_WORKERS = psutil.cpu_count(logical=True)
# MAX_WORKERS = 1 # Reduce para pruebas si Ollama se satura

# --- File Management ---
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
MAX_FILE_AGE_SECONDS = 24 * 60 * 60  # 1 día

# --- HTML Cleaning & Identifier Filtering ---
IDENTIFIER_PATTERNS_TO_EXCLUDE = [
    r"\[ARGONAUTA.*?\]",
    r"\[INC\d+\]",
    r"CRQ\d+"
]