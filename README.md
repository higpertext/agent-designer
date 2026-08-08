# agent-designer

`agent-designer` tiene una única responsabilidad: diseñar, crear y validar agentes externos profesionales con higpertext.

No administra agentes existentes, no cambia entre sesiones y no ejecuta sincronizaciones de documentación o gobernanza ajenas a la entrega de un agente nuevo.

## Flujo de entrega

1. Define el dominio único, entradas, salidas, límites y riesgos del agente.
2. Selecciona el mínimo de capabilities verificadas.
3. Genera la base:

   ```bash
   htx task common.agent-builder --profile <perfil> --target <ruta> --description "<objetivo>"
   ```

4. Completa `src/config/profiles/<perfil>.json`, capabilities propias y hooks necesarios.
5. Verifica JSON, referencias, perfil, estado, hooks y el arnés e2e.
6. Si el agente debe ser portable, regístralo y ejecútale `common.agent-bootstrap` para instalar el motor en su propio venv.

## Requisitos

- Python 3.10+
- `higpertext-cli` instalado en el entorno del agente

## Activación

```bash
htx profile load agent_designer --assistant claude
htx task common.session-start --action start --profile agent_designer
```

## Arnés de verificación

El arnés comprueba que el perfil mantenga el alcance único, que solo habilite capacidades de creación/validación, que el hook esté definido y que el motor pueda generar un agente temporal.

```bash
python -m pytest tests/test_agent_designer_harness.py
```

El resultado de una entrega solo es válido cuando las comprobaciones del protocolo del perfil y este arnés terminan correctamente.
