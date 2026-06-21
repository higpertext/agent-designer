# 📄 Reporte de Incidente Postmortem (SRE Standard)

**ID de Incidente**: `INC-{{incident_id}}`
**Fecha y Hora**: `{{date_time}}`
**Severidad**: `{{severity}}` (P1/P2/P3/P4)
**Autor**: Agente higpertext SRE / `{{author}}`

---

## 📋 1. Resumen Ejecutivo
Un breve resumen de qué ocurrió, cuánto tiempo duró y cuál fue el impacto global para los usuarios y la organización.

- **Inicio del Impacto**: `{{start_time}}`
- **Mitigación del Incidente**: `{{mitigation_time}}`
- **Duración Total (MTTR)**: `{{mttr_duration}}`

---

## 🔍 2. Causa Raíz (Root Cause Analysis - Los 5 Porqués)
1. **¿Por qué falló el servicio?** `{{why_1}}`
2. **¿Por qué ocurrió eso?** `{{why_2}}`
3. **¿Por qué se permitió esa condición?** `{{why_3}}`
4. **¿Por qué no se detectó antes?** `{{why_4}}`
5. **¿Por qué fallaron las defensas?** `{{why_5}}`

---

## 🛠️ 3. Acciones de Mitigación y Remediación (Action Items)
| Tarea | Responsable | Prioridad | Estado | Enlace PR / Ticket |
|---|---|---|---|---|
| Añadir validación de rate limit en API | Equipo SRE | Alta | Pendiente | `#` |
| Actualizar el SLO de latencia en sre_slos.json | Agente higpertext | Media | En Progreso | `#` |

---
*Generado automáticamente por el motor higpertext Engine SRE.*
