      
# Analizador y Clasificador de Tickets IT con Flask y Ollama

Este proyecto proporciona una interfaz web para analizar y clasificar tickets de soporte técnico exportados desde un sistema de ticketing (en formato `.xlsx` o `.xls`). Utiliza modelos de lenguaje grandes (LLMs) ejecutados localmente a través de Ollama para garantizar la privacidad de los datos, generar resúmenes estructurados y asignar categorías a los tickets, con la opción de añadir contexto personalizado para mejorar la precisión del análisis.

**El Problema:** Analizar cientos de tickets manualmente es tedioso, propenso a errores y consume mucho tiempo.
**La Solución:** Aprovechar la inteligencia artificial local para automatizar la extracción de información clave y la categorización inicial de los tickets.

## Características Principales

*   **Interfaz Web Simple:** Sube tus archivos Excel directamente desde el navegador gracias a Flask.
*   **Procesamiento Local con Ollama:** Utiliza modelos LLM (como Gemma, Llama3, Mistral) que se ejecutan en tu propia máquina. ¡Tus datos nunca salen de tu red!
*   **Análisis Estructurado por IA:**
    *   Genera automáticamente múltiples columnas con información clave extraída de cada ticket:
        *   `Clasificacion_Sugerida_IA`
        *   `Problema_Principal_IA`
        *   `Sintomas_Detectados_IA`
        *   `Acciones_Realizadas_IA`
        *   `Causa_Raiz_Estimada_IA`
        *   `Resumen_General_Conciso_IA`
*   **Contexto Personalizado:** Mejora drásticamente el análisis. Añade información específica de tu entorno (nombres de proyectos, software interno, departamentos, problemas recurrentes) para guiar al modelo LLM.
*   **Procesamiento en Segundo Plano:** Analiza archivos grandes sin bloquear la interfaz web, usando hilos paralelos para acelerar el proceso.
*   **Seguimiento del Progreso:** Observa el estado y el progreso del análisis en tiempo real.
*   **Descarga de Resultados:** Obtén un nuevo archivo Excel con las columnas originales más todas las columnas generadas por la IA.
*   **Limpieza de Datos:** Elimina etiquetas HTML y filtra identificadores comunes (ej. `[ARGONAUTA]`, `[INC####]`, `CRQ#####`) antes del análisis.
*   **Resumen de Análisis Global:** Proporciona un conteo de las categorías sugeridas por la IA y recomendaciones básicas basadas en la frecuencia.
*   **Configuración de Recursos:** Intenta adecuarse a los recursos de CPU disponibles para el procesamiento paralelo.
*   **Limpieza Automática de Archivos:** Sistema básico de limpieza de archivos antiguos en las carpetas `uploads/` y `processed/`.

## Tecnologías Utilizadas

*   **Backend:** Python 3
*   **Framework Web:** Flask
*   **Procesamiento de Datos:** Pandas
*   **LLM Local:** Ollama ([https://ollama.com/](https://ollama.com/))
    *   Modelo Predeterminado: Configurable en `config.py` (ej. `gemma:2b`)
*   **Procesamiento Paralelo:** `concurrent.futures.ThreadPoolExecutor`
*   **Frontend:** HTML, CSS Básico, JavaScript (para subida de archivos y polling de estado)
*   **Parsing HTML (Limpieza):** BeautifulSoup4
*   **Información del Sistema:** Psutil

## Configuración y Uso

### 1. Requisitos Previos

*   **Python 3.8+**
*   **Ollama Instalado:**
    *   Sigue las instrucciones en [https://ollama.com/](https://ollama.com/).
    *   Descarga al menos un modelo LLM compatible. Ejemplos:
        ```bash
        ollama pull gemma:2b
        ollama pull llama3
        ollama pull mistral
        ```
    *   Asegúrate de que el servicio de Ollama esté corriendo (normalmente en `http://localhost:11434`).

### 2. Instalación del Proyecto

a.  **Clona el Repositorio (o descarga los archivos):**
    ```bash
    git clone https://github.com/Dannypatt/flask-ticket-analyzer.git
    cd flask-ticket-analyzer
    ```

b.  **Crea y Activa un Entorno Virtual (Recomendado):**
    ```bash
    python -m venv venv
    # En Linux/macOS:
    source venv/bin/activate
    # En Windows:
    # venv\Scripts\activate
    ```

c.  **Instala las Dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. Configuración (Opcional)

Edita el archivo `config.py` para ajustar:
*   `OLLAMA_BASE_URL`: Si Ollama corre en una URL diferente.
*   `OLLAMA_MODEL`: El modelo LLM por defecto a utilizar.
*   `DEFAULT_COLUMNS_TO_ANALYZE`: Nombres de las columnas en tu Excel que contienen la descripción breve, descripción larga y notas de trabajo.
*   `MAX_WORKERS`: Número máximo de hilos para el procesamiento paralelo (por defecto, usa los cores lógicos de la CPU).
*   `IDENTIFIER_PATTERNS_TO_EXCLUDE`: Patrones de expresiones regulares para identificadores a filtrar.

### 4. Ejecutar la Aplicación

Desde la raíz del proyecto (`flask-ticket-analyzer`), con el entorno virtual activado:
```bash
python app.py

    
