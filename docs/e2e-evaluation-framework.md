# Marco reutilizable de evaluación E2E

Este marco valida un agente en tres capas: contrato estático, ciclo de vida del motor y comportamiento conversacional real. Puede copiarse a otro agente cambiando los casos, artefactos esperados y reglas de aceptación.

## Principios

- Las pruebas deterministas no requieren red ni un asistente autenticado.
- Las pruebas conversacionales son explícitas: nunca se ejecutan en CI por accidente.
- Cada ejecución produce evidencia: prompt, salida, código de retorno, errores y veredicto.
- Una respuesta del LLM no equivale a éxito: el arnés valida también los archivos y el estado que esa respuesta afirma haber creado.

## Capa 1: contrato estático

Verifica el perfil, capabilities, reglas, hooks, contratos JSON y límites de alcance.

```bash
python -m pytest -p no:cacheprovider tests/test_agent_designer_harness.py
htx profile validate agent_designer --source .
```

Para otro escenario, sustituye `EXPECTED_CAPABILITIES`, las reglas de alcance y el archivo de hook en su arnés.

## Capa 2: ciclo de vida del agente

Verifica el motor sin usar un LLM:

1. Ejecutar `htx agent init` en un directorio temporal.
2. Confirmar el perfil inicial, `htx.py`, `.higpertext/config/environment.json`, `hooks_config.json` y `semantic_graph.md`.
3. Comprobar fallos contractuales, por ejemplo un perfil reservado con código distinto de cero.
4. Ejecutar `htx task agent_designer.verify-delivery --target <agente> --profile <perfil>` y archivar `.higpertext/reports/agent_delivery.json`.
5. Para distribución portable: registrar el agente, ejecutar `common.agent-bootstrap` y verificar que los hooks apunten al `.venv` del agente.

El arnés de este agente cubre los pasos 1–3. El motor mantiene además su suite de ciclo de vida en `higpertext-cli/tests/e2e/test_e2e_agent_lifecycle.py`.

## Capa 3: conversación real con Claude

Requisitos:

- CLI `claude` instalado y autenticado.
- Workspace temporal inicializado y con el perfil cargado.
- Aceptación consciente de que se enviarán prompts a Claude.

Preparar el workspace:

```bash
WORKSPACE=$(mktemp -d /tmp/agent-designer-claude-XXXXXX)
htx init --assistant claude --target "$WORKSPACE"
htx profile load agent_designer --source . --target "$WORKSPACE" --assistant claude
```

Ejecutar los casos:

```bash
python tests/e2e/run_claude_e2e.py \
  --workspace "$WORKSPACE" \
  --output "$WORKSPACE/claude-e2e-report.json"
```

El ejecutor usa exactamente `claude -p "<prompt>"`, captura stdout, stderr y código de salida, y escribe un reporte JSON. Devuelve código `1` si un caso falla.

## Diseño de casos

Los casos se declaran en `tests/e2e/claude_cases.json`:

```json
{
  "id": "nombre_estable",
  "prompt": "Solicitud completa enviada al agente.",
  "response_contains_any": ["señal esperada", "alternativa aceptable"]
}
```

Usa casos que comprueben tanto éxito como rechazo seguro:

- responsabilidad única;
- petición ambigua que debe producir preguntas;
- intento de usar capability inexistente;
- perfil reservado;
- solicitud de agente con hook;
- solicitud portable que exija bootstrap;
- agente excesivamente amplio que deba acotarse.

Las señales textuales son una primera barrera. Para casos que crean archivos, añade al ejecutor una sección `expected_files` y valida su existencia después de cada respuesta. Para respuestas complejas, conserva el reporte y realiza evaluación humana o un juez LLM separado, nunca el mismo agente bajo prueba.

## Criterio de aceptación

Un escenario queda aprobado solo cuando:

1. perfil y contratos validan;
2. las pruebas deterministas pasan;
3. los artefactos de ciclo de vida existen y son coherentes;
4. cada caso de Claude termina con código cero y satisface su criterio;
5. el reporte JSON queda archivado fuera de los artefactos generados del agente.
6. el reporte de entrega del agente tiene `passed: true`; si `HIGPERTEXT_DELIVERY_TARGET` está definido, el hook `Stop` también debe permitir el cierre.

## Limpieza

El workspace temporal contiene configuraciones y posibles archivos creados durante la conversación. Tras archivar el reporte:

```bash
rm -rf "$WORKSPACE"
```

Usa siempre una ruta temporal explícita; no ejecutes limpieza recursiva sobre un directorio de trabajo real.
