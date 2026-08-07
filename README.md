# agent-designer

Agente higpertext especializado en **diseñar y construir otros agentes**. Es, por ahora,
el único perfil que se está exponiendo a usuarios: en vez de asumir que alguien ya conoce
higpertext, este agente los acompaña desde "qué necesito" hasta un agente externo
funcionando con su propio perfil, capabilities y contrato técnico.

> **Estado**: este directorio es un checkout de trabajo. Está planeado migrarlo a su
> propio repositorio dedicado — la estructura de abajo se mantiene estable a través de
> esa migración, solo cambia el remoto de git.

---

## Qué hace

Dos responsabilidades, no una:

1. **Experto en la herramienta** — conoce a fondo el flujo de higpertext: scaffolding
   (`common.agent-builder`), definición de perfil, creación de capabilities con
   contrato técnico, hooks, registro/sync (`common.agent-sync`) y arranque
   (`profile load`). Ver el detalle paso a paso en
   [`src/config/profiles/agent_designer.json`](src/config/profiles/agent_designer.json)
   (campo `system_prompt`).
2. **Experto en levantar requerimientos** — antes de generar cualquier scaffolding,
   su trabajo es entender qué necesita la persona: qué problema resuelve el agente que
   quiere, qué dominio cubre, qué debe y no debe poder hacer. Un agente mal levantado
   (demasiado amplio, con capabilities de más) viola el principio de mínimo privilegio
   que el propio `agent_designer` exige a los agentes que ayuda a crear.

## Requisitos

- Python 3.10+
- El motor `higpertext-cli` instalado (ver siguiente sección)

## Replicar este agente

```bash
git clone <url-del-repo> agent-designer
cd agent-designer

# El motor no viaja con este repo — se instala en un venv propio del agente
python -m venv .venv
source .venv/bin/activate
pip install higpertext-cli

# Genera la integración nativa para tu asistente (CLAUDE.md, .claude/rules/, hooks)
htx profile load agent_designer --assistant claude
```

`htx profile load` lee `src/config/profiles/agent_designer.json` y compila todo lo
demás en `.higpertext/` (estado generado, no se edita a mano — ver `.gitignore`).

> ⚠️ **Nota de portabilidad**: `.higpertext/config/environment.json` en este checkout
> apunta al intérprete Python del checkout de desarrollo original
> (`python_executable`), no a un venv local. Si clonas este repo en otra máquina,
> `htx profile load` lo regenera automáticamente apuntando a tu propio `.venv` — no
> reutilices el `environment.json` de otro checkout.

## Uso

```bash
htx task common.session-start --action start --profile agent_designer
```

Esto monta los skills (`agent-design-standards`, `higpertext-guide`, `best-practices`,
`agent-builder-guide`, `capability-validator`) y el subagente `architect` que el perfil
declara en `session_skills` / `session_subagents`.

A partir de ahí, describe el agente que necesitas — el flujo completo (scaffolding →
perfil → capabilities → hooks → registro → activación) está documentado paso a paso
dentro del `system_prompt` del perfil.

## Estructura

```
agent-designer/
├── src/
│   ├── config/profiles/
│   │   └── agent_designer.json      ← perfil principal (el único disponible hoy)
│   ├── templates/
│   │   ├── skills/                  ← skills que se montan en sesión
│   │   │   ├── agent-design-standards/
│   │   │   └── best-practices/
│   │   └── subagents/
│   │       └── architect.json       ← subagente DDD/Clean Architecture
│   └── workflows/
│       ├── docs-update.json         ← regenera catálogos de docs y registra en memoria
│       └── guidelines-sync.json     ← sincroniza lineamientos de gobernanza externos
├── .claude/, .gemini/, .agent/      ← hooks nativos por asistente (generados, no editar)
└── .higpertext/                     ← estado compilado del motor (generado, no editar)
```

Los directorios de hooks nativos y `.higpertext/` se regeneran con `htx profile load` /
`htx agent init` — no se editan directamente.

## Workflows disponibles

| Workflow | Qué hace |
|---|---|
| `workflow.docs-update` | Escanea capabilities y perfiles, regenera el catálogo de docs y deja registro en memoria. `htx workflow run docs-update` |
| `workflow.guidelines-sync` | Descarga lineamientos de gobernanza desde una fuente git/local y actualiza el contrato central. `htx workflow run guidelines-sync --source <url-o-path>` |

Ambos requieren el perfil `global` del motor (siempre disponible, no es exclusivo de
este agente).
