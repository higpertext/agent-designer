# 🚨 Reporte de Diagnóstico y Remediación de Pipeline — Build #{{build_id}}

**Fecha del Diagnóstico**: `{{timestamp}}`
**Organización y Proyecto**: `{{organization_url}}` / `{{project_name}}`
**Pipeline / Build ID**: `{{build_id}}`
**Estado del Pipeline**: ❌ **FALLIDO**

---

## 🔍 1. Contexto del Fallo y Tarea Afectada
- **Paso / Tarea Fallida**: `{{failed_task_name}}`
- **¿Qué intentaba hacer la tarea?**: {{task_purpose}}
- **Duración antes del fallo**: {{duration}}

---

## ⚠️ 2. Traza del Error y Variables Faltantes
### Error Capturado de Azure DevOps:
```text
{{error_log_snippet}}
```

### Análisis de Variables y Entorno:
{{variables_analysis}}

---

## 📚 3. Historial en la Base de Conocimiento (Wiki)
{{wiki_knowledge_context}}

---

## 💡 4. Causa Raíz Identificada y Solución
### Causa Raíz:
{{root_cause_analysis}}

### Pasos Exactos de Remediación:
{{remediation_steps}}

---
*Generado automáticamente por el motor higpertext AI CI/CD Pipeline Doctor.*
