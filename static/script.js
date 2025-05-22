// static/script.js
document.addEventListener('DOMContentLoaded', function() {
    console.log("SCRIPT.JS: DOM completamente cargado y procesado.");

    const uploadForm = document.getElementById('uploadForm');
    const uploadButton = document.getElementById('uploadButton'); 
    const analyzeButton = document.getElementById('analyzeButton');
    const fileInput = document.getElementById('file');

    const progressArea = document.getElementById('progressArea');
    const progressBarContainer = document.querySelector('.progress-bar-container');
    const progressBar = document.getElementById('progressBar');
    const statusMessage = document.getElementById('statusMessage');
    const downloadLink = document.getElementById('downloadLink');
    const analysisSummaryDiv = document.getElementById('analysisSummary');

    const ollamaModelSelect = document.getElementById('ollama_model_select');
    const ollamaModelCustomInput = document.getElementById('ollama_model_custom');

    let currentTaskId = null;
    let pollInterval = null;

    if (!uploadForm) console.error("SCRIPT.JS: Elemento uploadForm NO encontrado.");
    if (!uploadButton) console.error("SCRIPT.JS: Elemento uploadButton NO encontrado.");
    if (!analyzeButton) console.error("SCRIPT.JS: Elemento analyzeButton NO encontrado.");
    if (!fileInput) console.error("SCRIPT.JS: Elemento fileInput NO encontrado.");
    if (!statusMessage) console.error("SCRIPT.JS: Elemento statusMessage NO encontrado.");


    if (uploadForm) {
        console.log("SCRIPT.JS: Adjuntando event listener a uploadForm.");
        uploadForm.addEventListener('submit', async function(event) {
            event.preventDefault(); 
            console.log("SCRIPT.JS: Evento 'submit' de uploadForm CAPTURADO y PREVENIDO.");
            
            if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
            currentTaskId = null;
            if(progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }
            if (statusMessage) statusMessage.textContent = '';
            if (downloadLink) downloadLink.innerHTML = '';
            if (analysisSummaryDiv) analysisSummaryDiv.innerHTML = '';
            if (analyzeButton) { analyzeButton.style.display = 'none'; analyzeButton.disabled = true; }
            if (uploadButton) { uploadButton.style.display = 'inline-block';}

            const formData = new FormData();
            if (!fileInput.files || fileInput.files.length === 0) {
                if (statusMessage) {
                    statusMessage.textContent = 'Por favor, selecciona un archivo primero.';
                    statusMessage.className = 'status-message error';
                }
                console.warn("SCRIPT.JS: No se seleccionó archivo para subir.");
                if (uploadButton) {
                    uploadButton.disabled = false;
                    uploadButton.textContent = '1. Subir Archivo';
                }
                return; 
            }
            const fileToUpload = fileInput.files[0]; 
            formData.append('file', fileToUpload);
            console.log("SCRIPT.JS: Archivo añadido a FormData:", fileToUpload.name);

            if (uploadButton) {
                uploadButton.disabled = true;
                uploadButton.textContent = 'Subiendo...';
            }
            if(progressArea) progressArea.style.display = 'block';
            if(progressBarContainer) progressBarContainer.style.display = 'block';
            if(statusMessage) {
                statusMessage.textContent = 'Subiendo archivo...';
                statusMessage.className = 'status-message info';
            }
            console.log("SCRIPT.JS: Intentando subir archivo:", fileToUpload.name);

            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                console.log("SCRIPT.JS: Respuesta de /upload - Status:", response.status);
                const data = await response.json();
                console.log("SCRIPT.JS: Respuesta de /upload - Data:", data);

                if (response.ok) {
                    currentTaskId = data.task_id;
                    if(statusMessage) statusMessage.textContent = `Archivo "${data.filename}" subido. Listo para analizar.`;
                    if(uploadButton) uploadButton.style.display = 'none'; 
                    if(analyzeButton) {
                        analyzeButton.style.display = 'inline-block'; 
                        analyzeButton.disabled = false;
                    }
                } else {
                    if(statusMessage) {
                        statusMessage.textContent = `Error al subir: ${data.error || 'Error desconocido del servidor'}`;
                        statusMessage.className = 'status-message error';
                    }
                    if(uploadButton) { 
                        uploadButton.disabled = false;
                        uploadButton.textContent = '1. Subir Archivo';
                    }
                    if(progressArea) progressArea.style.display = 'block';
                }
            } catch (error) {
                console.error('SCRIPT.JS: Error en fetch /upload:', error);
                if(statusMessage) {
                    statusMessage.textContent = 'Error de red o al procesar la subida del archivo.';
                    statusMessage.className = 'status-message error';
                }
                if(uploadButton) { 
                    uploadButton.disabled = false;
                    uploadButton.textContent = '1. Subir Archivo';
                }
                if(progressArea) progressArea.style.display = 'block';
            }
        });
    } else {
        console.error("SCRIPT.JS: No se pudo adjuntar el event listener a uploadForm porque el FORMULARIO no se encontró.");
    }

    if (analyzeButton) {
        analyzeButton.addEventListener('click', async function() {
            console.log("SCRIPT.JS: Botón 'Analizar Tickets' clickeado.");
            if (!currentTaskId) {
                if(statusMessage) {
                    statusMessage.textContent = 'Error: No hay tarea activa para analizar.';
                    statusMessage.className = 'status-message error';
                }
                return;
            }

            analyzeButton.disabled = true;
            analyzeButton.textContent = 'Analizando...';
            if(statusMessage) {
                statusMessage.textContent = 'Iniciando análisis...';
                statusMessage.className = 'status-message info';
            }
            if(downloadLink) downloadLink.innerHTML = '';
            if(analysisSummaryDiv) analysisSummaryDiv.innerHTML = '';
            if(progressBar) {
                progressBar.style.width = '0%';
                progressBar.textContent = '0%';
            }

            const analysisFormData = new FormData();
            analysisFormData.append('custom_context', document.getElementById('custom_context').value);
            analysisFormData.append('description_column', document.getElementById('description_column').value);
            analysisFormData.append('short_description_column', document.getElementById('short_description_column').value);
            analysisFormData.append('work_notes_column', document.getElementById('work_notes_column').value);
            
            let selectedModel = ollamaModelSelect.value;
            if (selectedModel === "otro_modelo_personalizado") {
                selectedModel = ollamaModelCustomInput.value.trim();
                if (!selectedModel) {
                    if(statusMessage){
                        statusMessage.textContent = 'Error: Debes especificar un nombre para "Otro modelo".';
                        statusMessage.className = 'status-message error';
                    }
                    if(analyzeButton){
                        analyzeButton.disabled = false;
                        analyzeButton.textContent = '2. Analizar Tickets';
                    }
                    return;
                }
            }
            analysisFormData.append('ollama_model_select', selectedModel);
            console.log("SCRIPT.JS: Enviando para análisis con modelo:", selectedModel);

            try {
                const response = await fetch(`/analyze/${currentTaskId}`, {
                    method: 'POST',
                    body: analysisFormData
                });
                const data = await response.json();
                console.log("SCRIPT.JS: Respuesta de /analyze - Data:", data);

                if (response.ok || response.status === 202) { 
                    if(statusMessage) statusMessage.textContent = data.message || 'Análisis iniciado. Esperando progreso...';
                    if (pollInterval) clearInterval(pollInterval); 
                    pollInterval = setInterval(() => pollStatus(currentTaskId), 2000); 
                } else {
                    if(statusMessage) {
                        statusMessage.textContent = `Error al iniciar análisis: ${data.error || 'Error desconocido del servidor'}`;
                        statusMessage.className = 'status-message error';
                    }
                    if(analyzeButton) {
                        analyzeButton.disabled = false;
                        analyzeButton.textContent = '2. Analizar Tickets';
                    }
                }
            } catch (error) {
                console.error('SCRIPT.JS: Error en fetch /analyze:', error);
                if(statusMessage) {
                    statusMessage.textContent = 'Error de red al iniciar el análisis.';
                    statusMessage.className = 'status-message error';
                }
                if(analyzeButton) {
                    analyzeButton.disabled = false;
                    analyzeButton.textContent = '2. Analizar Tickets';
                }
            }
        });
    } else {
         console.error("SCRIPT.JS: No se pudo adjuntar el event listener a analyzeButton porque el BOTÓN no se encontró.");
    }

    async function pollStatus(taskId) {
        try {
            const response = await fetch(`/status/${taskId}`);
            const data = await response.json();

            if (!response.ok) {
                console.error('SCRIPT.JS: Error al obtener estado (API /status):', data.error);
                if(statusMessage) {
                    statusMessage.textContent = `Error al obtener estado: ${data.error || 'Respuesta no OK del servidor'}`;
                    statusMessage.className = 'status-message error';
                }
                return;
            }
            
            if(statusMessage) statusMessage.textContent = data.message || "Procesando...";
            let progress = 0;
            if (data.progress_total > 0) {
                progress = (data.progress_current / data.progress_total) * 100;
            }
            if(progressBar) {
                progressBar.style.width = `${progress}%`;
                progressBar.textContent = `${Math.round(progress)}%`;
            }

            if (data.status === 'completed') {
                if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
                if(progressBar) { progressBar.style.width = '100%'; progressBar.textContent = '100%'; }
                if(statusMessage) { statusMessage.textContent = data.message || 'Análisis completado.'; statusMessage.className = 'status-message info'; }
                if(downloadLink) downloadLink.innerHTML = `<a href="/download/${taskId}" class="button" style="background-color: #28a745; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Descargar Resultados</a>`;
                
                if(uploadButton) { uploadButton.style.display = 'inline-block'; uploadButton.disabled = false; uploadButton.textContent = '1. Subir Otro Archivo'; }
                if(analyzeButton) { analyzeButton.textContent = '2. Analizar de Nuevo'; analyzeButton.disabled = false; }
                if(fileInput) fileInput.value = ''; 
                
                displayAnalysisSummary(data.analysis_summary);

            } else if (data.status === 'error') {
                if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
                if(statusMessage) { statusMessage.textContent = `Error: ${data.message || 'Fallo en el análisis.'}`; statusMessage.className = 'status-message error'; }
                
                if(uploadButton) { uploadButton.style.display = 'inline-block'; uploadButton.disabled = false; uploadButton.textContent = '1. Subir Otro Archivo'; }
                if(analyzeButton) { analyzeButton.textContent = '2. Intentar Análisis de Nuevo'; analyzeButton.disabled = false; }
                
                displayAnalysisSummary(data.analysis_summary);
            } else { 
                 if(statusMessage) statusMessage.className = 'status-message info';
            }

        } catch (error) {
            console.error('SCRIPT.JS: Error de red en pollStatus:', error);
            if(statusMessage) {
                statusMessage.textContent = 'Error de red al obtener estado. Reintentando...';
                statusMessage.className = 'status-message error';
            }
        }
    }
    
    function displayAnalysisSummary(summary) {
        if (!analysisSummaryDiv) return;
        analysisSummaryDiv.innerHTML = '';
        if (!summary) {
            analysisSummaryDiv.innerHTML = '<p>No hay resumen de análisis disponible.</p>';
            return;
        }
        let html = '<h3>Resumen del Análisis Global:</h3>';
        if (summary.error) { 
            html += `<p class="error">Error en el análisis: ${summary.error}</p>`;
        }
        if (summary.error_saving_file) {
            html += `<p class="error">Error al guardar el archivo de resultados: ${summary.error_saving_file}</p>`;
        }
        html += `<p><strong>Total de tickets analizados:</strong> ${summary.total_tickets !== undefined ? summary.total_tickets : 'N/A'}</p>`;
        html += `<p><strong>Modelo LLM utilizado:</strong> ${summary.ollama_model_used || 'No especificado'}</p>`;
        html += `<p><strong>Contexto personalizado proporcionado:</strong> ${summary.custom_context_provided ? 'Sí' : 'No'}</p>`;
        
        if (summary.columns_generated_by_ia && summary.columns_generated_by_ia.length > 0) {
            html += `<p><strong>Columnas generadas por IA en el Excel:</strong> ${summary.columns_generated_by_ia.join(', ')}</p>`;
        }

        if (summary.category_counts && Object.keys(summary.category_counts).length > 0) {
            html += `<h4>Distribución de "Clasificacion_Sugerida_IA":</h4><ul>`;
            for (const category in summary.category_counts) {
                html += `<li>${category}: ${summary.category_counts[category]}</li>`;
            }
            html += '</ul>';
        } else if (summary.total_tickets > 0) {
            html += '<p>No se generaron estadísticas de categorías (o todas fueron "Error al clasificar" o similares).</p>';
        }
        if (summary.recommendations && summary.recommendations.length > 0) {
            html += '<h4>Recomendaciones/Observaciones:</h4><ul>';
            summary.recommendations.forEach(rec => {
                html += `<li>${rec}</li>`;
            });
            html += '</ul>';
        } else if (summary.total_tickets > 0) {
             html += '<p>No hay recomendaciones automáticas generadas.</p>';
        }
        analysisSummaryDiv.innerHTML = html;
    }

    if (ollamaModelSelect) {
        ollamaModelSelect.addEventListener('change', function() {
            if (this.value === "otro_modelo_personalizado") {
                if(ollamaModelCustomInput) ollamaModelCustomInput.style.display = 'block';
            } else {
                if(ollamaModelCustomInput) {
                    ollamaModelCustomInput.style.display = 'none';
                    ollamaModelCustomInput.value = '';
                }
            }
        });
        if (ollamaModelSelect.value === "otro_modelo_personalizado") {
            if(ollamaModelCustomInput) ollamaModelCustomInput.style.display = 'block';
        } else {
            if(ollamaModelCustomInput) ollamaModelCustomInput.style.display = 'none';
        }
    } else {
        console.error("SCRIPT.JS: Elemento ollamaModelSelect NO encontrado.");
    }
    console.log("SCRIPT.JS: Script completamente cargado y listeners (potencialmente) adjuntados.");
});