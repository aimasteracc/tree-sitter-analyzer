# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)** | **Español**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![Works with Claude Code · Cursor · MCP](https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**Inteligencia de código en la que los agentes de IA pueden confiar** — estructura correcta entre lenguajes según el [inventario de lenguajes soportados](#lenguajes-soportados), nativo para agentes (MCP + CLI).

TSA indexa tu base de código con tree-sitter y sirve gráficos de llamadas correctos, búsqueda de símbolos y consultas estructurales a agentes de código IA — localmente, sin telemetría.

**Por qué es diferente:**
* **La corrección entre lenguajes es la ventaja.** Las puertas por familia de lenguaje impiden vinculaciones cruzadas basadas solo en el nombre.
* **Diseñado nativo para agentes.** 8 herramientas MCP con salida JSON estructurada y sobres de veredicto, más acceso por CLI y flujos de trabajo curados.
* **Amplio y correctamente clasificado.** El [inventario de profundidad de soporte generado](#lenguajes-soportados) distingue la evidencia de pipeline del comportamiento entre archivos aún no verificado.

> ¿Actualizando desde v1.x? Consulta [docs/MIGRATION.md](docs/MIGRATION.md).

### Límites del sistema nervioso (Pulse / TQL / Semantic Query)

Los selectores temporales de TQL comparan marcas de tiempo de modificación, no
recuentos de modificación. La acción `tql_schema` documenta la ventana y el
valor por defecto compartido para `:hot` y `:recently_modified` sin
calificar. Las consultas de profundidad conservan la identidad exacta de la
definición y fallan explícitamente cuando se superan los límites de
recorrido.

Las solicitudes de Pulse devuelven contexto vinculado a una instantánea. Las
lecturas SQL para identidad, relaciones, contexto de importación inversa y
el enriquecimiento LSP en caché opcional comparten un punto de guardado
(*savepoint*) sin terminar una transacción propiedad del llamador. Esto no
es un round-trip de SQL ni una garantía de latencia.

El contexto de importación inversa de Python en Pulse usa el resolutor de
módulos existente; esto no es una afirmación de resolución completa de
módulos entre lenguajes. El contexto de comentarios requiere un índice
reconstruido con extracción de comentarios. Los índices antiguos y los
lenguajes sin extracción de comentarios devuelven `COMMENTS_NOT_INDEXED`, en
lugar de un éxito vacío; omite explícitamente el contexto de comentarios con
el ajuste documentado `max_comments` cuando no se necesita. Las
proyecciones de mensajes de commit heredadas que faltan pasan a `pending`
para actualización perezosa; se conserva la activación `disabled`. Los
estados de activación NULL heredados también pasan a pending, sin borrar
mensajes o conteos antiguos. Los ciclos de indexación en caché habilitados
continúan con actualización de activación acotada. Pulse expone la
activación no disponible como `null`, mientras que las consultas temporales
rechazan evidencia de activación incompleta. La actualización lee historial
real de Git mediante lotes acotados; las lecturas de mensajes fallidas
conservan el trabajo pendiente en lugar de reclamar finalización.

Las consultas semánticas requieren un modelo de embedding almacenado
conocido y una dimensión consistente. Modelos mixtos o desconocidos son
errores, sin resolución alternativa de proveedor. Las pruebas offline usan
dobles de modelo; no certifican la calidad de un proveedor en vivo.

Los lotes de Pulse conservan las entradas exitosas pero reportan fallo si
un objetivo falla. TQL trata los índices faltantes o ilegibles como
errores, distintos de un índice listo sin coincidencias. La validación de
solicitudes públicas rechaza tipos y límites inválidos antes de abrir el
índice o invocar un proveedor de embeddings.

---

## Primeros pasos

> **Requiere Python 3.10+** (verifica con: `python3 --version`). Instálalo desde [python.org](https://www.python.org/downloads/) si es necesario.

### Instalación automatizada (recomendada)

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

Instala automáticamente `uv` si falta, detecta Claude Desktop / Claude Code / Cursor / VS Code, y escribe la entrada MCP. Ejecuta `tree-sitter-analyzer --doctor` para verificar.

> **Confianza en el arranque (bootstrap):** por comodidad, el comando anterior descarga y ejecuta el instalador oficial de `uv` cuando `uv` falta o está desactualizado. Ese instalador es mutable y **no está vinculado a un contenido fijo**; TSA avisa antes de descargarlo a un archivo temporal por TLS y realiza una comprobación estricta de versión tras la instalación. Para evitar este arranque no verificado, instala `uv >= 0.11.0` manualmente primero, o usa la opción segura de exclusión (que termina con instrucciones de instalación manual cuando se necesita el arranque):
> ```bash
> curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh \
>   | TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1 bash
> ```

Comando de instalación para **Claude Code**:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Reinicia tu agente y luego di: *"Ejecuta la herramienta `index` con action=status."*
Equivalente en CLI (sin agente): `tree-sitter-analyzer --codegraph-status`

> **Usuarios de PyPI / uvx — instala las skills:** las skills `tsa-*` vienen empaquetadas en la wheel. Cópialas una vez con:
> ```bash
> tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
> tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
> ```
> Los usuarios que clonan el repositorio ya las tienen bajo `.claude/skills/` — no se requiere ninguna acción.

[Otros agentes (Cursor, Copilot, Cline, Continue, Claude Desktop, Roo Code) →](#supported-agents)

### Instalación rápida

#### 1. Instalar dependencias

```bash
# uv (required). This official convenience installer is mutable/not content-bound;
# see https://docs.astral.sh/uv/ for alternative manual installation methods.
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (required for `search action=batch` multi-query text search; symbol search uses SQLite FTS5 and needs neither)
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

#### 2. Instalar Tree-sitter Analyzer

```bash
# Standalone install (persistent CLI command):
uv tool install "tree-sitter-analyzer[all,mcp]"
# — or skip installing entirely: the MCP entry below runs via uvx on demand.
# Inside a uv-managed Python project, use: uv add "tree-sitter-analyzer[all,mcp]"
```

#### 3. Conéctalo a tu agente

Consulta **[Agentes soportados](#supported-agents)**. La mayoría de los clientes necesitan esta entrada de servidor MCP:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```

Tras reiniciar: *"Ejecuta la herramienta `index` con action=status."*
Equivalente en CLI (sin agente): `tree-sitter-analyzer --codegraph-status`

**Comprueba la ventaja de corrección en tu propio repositorio** — sin instalación, sin CodeGraph (primero reindexa):

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

Reporta posibles colisiones de nombres entre lenguajes para que puedas inspeccionar el comportamiento del resolutor en tu propio repositorio. Los resultados son diagnósticos, no una afirmación de benchmark competitivo.

---

## Por qué Tree-sitter Analyzer

* **Salida estructurada.** Las respuestas MCP usan sobres JSON estándar; el comportamiento del payload está protegido por pruebas de contrato de respuesta.
* **Sobres de veredicto.** Cada respuesta lleva `verdict: SAFE | CAUTION | UNSAFE | INFO | REVIEW | WARN | ERROR | NOT_FOUND`, para que los orquestadores bifurquen según los resultados sin volver a preguntar.
* **Clasificación de salud del proyecto (A–F).** TSA clasifica proyectos según tamaño, complejidad, cobertura, duplicación, dependencias, estructura y puntos calientes de git.
* **Flujos de trabajo curados (Skills).** Subconjuntos de herramientas preconfigurados para "encontrar símbolo", "rastrear cadena de llamadas", "evaluar salud", "seguro para editar antes de refactorizar", "revisión de PR", etc.
* **Seguridad por capas.** `edit action=safe` + `edit action=guard` + DSL de restricciones + `edit action=impact` + sobres de veredicto — diseñado para que los agentes *sepan* antes de tocar.
* **Paridad CLI/MCP y un DSL de consulta unificado.** Las mismas primitivas de análisis están disponibles tanto para agentes como para usuarios de shell.

---

## Características clave

### Inteligencia de código pre-indexada (paridad con CodeGraph + superset)

| Capacidad | Herramienta TSA | Estado |
|---|---|---|
| Búsqueda de símbolos (FTS5 + **clasificado por BM25**) | `search` action=symbol | **ventaja** — resultados ordenados por puntuación de relevancia, no por ruta de archivo |
| Ir-a-definición / buscar-referencias / jerarquía de llamadas en una sola solicitud combinada | `nav` action=navigate | punto de entrada PRINCIPAL |
| Obtención masiva de N símbolos relacionados + mapa de relaciones | `structure` action=explore | paridad |
| Radio de impacto a nivel de función + puntuación de riesgo | `nav` action=impact | paridad + puntuación de riesgo |
| Quién-llama-a-X / a-qué-llama-X | `nav` action=callers / action=callees | paridad |
| Salud del índice de un vistazo (+ conteo de bordes) | `index` action=status | **ventaja** — informa `total_edges` como señal de densidad del gráfico |
| Caché de gráfico de llamadas pre-construido | `index` action=auto / action=full / action=sync | paridad |
| Pruebas afectadas por un cambio (CLI) | `--affected FILE...` | paridad |

### Exclusivo de Tree-sitter Analyzer

| Capacidad | Herramienta TSA | Nota |
|---|---|---|
| **Búsqueda de símbolos clasificada por BM25** | todas las herramientas de búsqueda | relevance_score normalizado min-máx en cada resultado; sort(by='confidence') en el DSL |
| **Búsqueda semántica (pre-filtrada por BM25)** | `search` action=chain (`semantic()` DSL) | pre-filtro léxico antes de reordenar por coseno |
| **Clasificación de salud del proyecto A–F** | `health` action=project | combina tamaño, complejidad, dependencias, cobertura, duplicación, estructura y puntos calientes de git |
| **Salida JSON** | cada herramienta, `output_format: "json"` (predeterminado) | sobres de respuesta estructurados estándar |
| **Sobres de veredicto** | cada herramienta | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Control de seguridad para editar** | `edit` action=safe / action=guard | rechaza ediciones de alto riesgo antes de que ocurran |
| **DSL de restricciones arquitectónicas** | `edit` action=constraints | "el módulo A no puede importar B" → aplicado |
| **Salud del código (nivel de archivo)** | `health` action=file | detección de bloques/métodos largos/code smells |
| **Jerarquía de clases** | `structure` action=class_tree | árbol de herencia de tipos |
| **Matriz de dependencias** | `health` action=matrix | matriz de acoplamiento de módulos |
| **Código muerto** | `health` action=dead | análisis transitivo de inalcanzabilidad |
| **Mapa de calor de complejidad** | `health` action=heatmap | complejidad ciclomática por función + vista de proyecto |
| **Detección de clones estructurales AST** | `viz` action=similarity | más allá de la similitud textual |
| **Exportación de gráfico de llamadas Mermaid** | `viz` action=graph | listo para pegar en documentación |
| **Exportación UML Mermaid** | `viz` action=uml | diagramas de clase / paquete / componente / secuencia |
| **Revisión de PR** | `edit` action=pr | AST-diff + clasificación semántica + radio de impacto |
| **agent_summary** | cada respuesta | pista del siguiente paso incluida en el sobre |
| **Resolutor Synapse entre archivos** | interno | consciente de importaciones, supera la conjetura por regex |
| **Activación temporal** | `nav` action=lineage | frecuencia de modificación git por símbolo |
| **Orientación de archivo** | `project` action=smart | salud + exportaciones + deps + riesgo de edición en una respuesta combinada |
| **Diario de decisiones arquitectónicas** | `project` action=journal | persiste el razonamiento entre sesiones — poco común entre herramientas de inteligencia de código |

### Skills

TSA envía flujos de trabajo curados bajo `.claude/skills/tsa-*/`:

`tsa-landing`, `tsa-find`, `tsa-graph`, `tsa-structure`, `tsa-deps`, `tsa-index`, `tsa-health-watch`, `tsa-edit-safety`, `tsa-edit-then-verify`, `tsa-constraints`, `tsa-pr-review`, `tsa-refactor-queue`, `tsa-temporal`.

Cada skill incluye un subconjunto de `allowed-tools` + receta de procedimiento + esquema de superficie de decisión, para que el agente no tenga que clasificar entre 8 herramientas en cada pregunta.

### 356 banderas de CLI

Superset de la superficie CLI de CodeGraph. Destacados:

```bash
tree-sitter-analyzer --table full <file>          # method/signature/complexity table
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # A-F grade across the project
# Note: --callers / --callees require the call-graph index — run --full-index first
tree-sitter-analyzer --full-index                 # build call-graph index (run once)
tree-sitter-analyzer --callers <symbol>           # who-calls
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + risk
tree-sitter-analyzer --affected <file...>         # tests transitively affected
tree-sitter-analyzer --dead-code                  # transitive unreachable
tree-sitter-analyzer --check-constraints          # architectural rules
tree-sitter-analyzer --safe-to-edit <file>        # refuse if risky
tree-sitter-analyzer --uml class                  # Mermaid UML class diagram
```

El paquete conserva la utilidad independiente para listar archivos:

```bash
list-files <dir>          # fd-style file discovery
```

`search-content` y `find-and-grep` se han eliminado en develop. Consulta la
[guía de migración](docs/MIGRATION.md) y el [`mapa de CLI`](docs/CODEMAPS/cli.md).

---

## Gobernanza de afirmaciones cuantitativas

Las cifras públicas de benchmark, rendimiento o comparación competitiva solo se emiten desde el
registro con procedencia verificada en
[`benchmarks/codegraph_compare/claim_registry.json`](benchmarks/codegraph_compare/claim_registry.json).
La evidencia de nivel E4 debe vincular nombres y versiones exactos de las herramientas,
mediciones, corpus, fecha/versión de benchmark, y un digest del artefacto. La evidencia por
debajo de E4 permanece interna y no puede emitir texto público. Consulta el [manual del benchmark](benchmarks/codegraph_compare/README.md).

<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->
<!-- END GENERATED QUANTITATIVE CLAIMS -->

La ausencia de un elemento generado significa que actualmente no hay ninguna
afirmación pública cuantitativa autorizada. Las descripciones cualitativas
anteriores son capacidades del producto delimitadas, no afirmaciones de
superioridad medida.

---

## Cómo funciona

```
Source code → tree-sitter parse → SQLite + FTS5 index (.ast-cache/index.db)
                                         ↓
        nav (navigate) / structure (explore) / nav (callers) / ...
                                         ↓
                            JSON response envelope
                            (verdict + agent_summary + data)
                                         ↓
                              MCP client / CLI consumer
```

Las 8 herramientas MCP exponen consultas indexadas y análisis directo del código fuente.
Construye el índice AST explícitamente antes de las consultas indexadas de símbolos/contexto con
`tree-sitter-analyzer --ast-cache --ast-cache-mode index --format json`. Actualízalo
tras cambios en el código fuente con `index` action=sync. Las consultas indexadas reutilizan
datos AST en caché; el precalentamiento automático es específico de cada herramienta.

---

## Agentes soportados

<details>
<summary><b>📘 Claude Code</b> (recomendado)</summary>

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Verifica: `claude mcp list`. Las skills `tsa-*` empaquetadas se auto-descubren desde `.claude/skills/`.

**Usuarios de PyPI / uvx** — instala las skills empaquetadas una vez con:
```bash
tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
```
Los usuarios que clonan el repositorio ya las tienen — no se requiere ninguna acción.
</details>

<details>
<summary><b>📗 Claude Desktop</b></summary>

Edita `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`, Linux: `~/.config/Claude/`):

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project" }
    }
  }
}
```
</details>

<details>
<summary><b>📙 GitHub Copilot (VS Code)</b></summary>

Crea `.vscode/mcp.json` (nota: `servers`, no `mcpServers`):

```json
{
  "servers": {
    "tree-sitter-analyzer": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}" }
    }
  }
}
```
</details>

<details>
<summary><b>🖱 Cursor / Cline / Continue / Roo Code</b></summary>

Todos leen el mismo esquema `mcpServers` que Claude Desktop. Cursor: **Settings → MCP**. Cline: panel MCP → Edit settings. Continue: `~/.continue/config.json` bajo `experimental.modelContextProtocolServers`. Roo Code: panel MCP → Edit MCP Settings.
</details>

<details>
<summary><b>🐳 Docker</b> (sin Python / uv local)</summary>

El repositorio incluye un [`Dockerfile`](Dockerfile) que construye el servidor MCP (transporte stdio) desde el código fuente, para que la imagen siempre coincida con el código confirmado (committed).

```bash
# Build once
docker build -t tree-sitter-analyzer-mcp .

# Run against the current repo (server speaks MCP over stdio; -i keeps stdin open)
docker run --rm -i --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work tree-sitter-analyzer-mcp
```

`--user "$(id -u):$(id -g)"` ejecuta con tu UID/GID de host, para que `.ast-cache/`, el diario de decisiones y cualquier escritura de `edit` bajo el repositorio montado te pertenezcan a ti, no a root.

Configuración del cliente MCP (la raíz del proyecto dentro del contenedor es el punto de montaje `/work`):

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--user", "1000:1000",
        "-v", "/absolute/path/to/your/project:/work",
        "-w", "/work",
        "-e", "TREE_SITTER_PROJECT_ROOT=/work",
        "tree-sitter-analyzer-mcp"
      ]
    }
  }
}
```
</details>

> ⚠️ `TREE_SITTER_PROJECT_ROOT` debe ser **absoluto**. El servidor aplica un límite de seguridad contra escapes de ruta mediante `SecurityValidator`.

---

## Lenguajes soportados

<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->
Generado a partir de los registros en tiempo de ejecución; consulta [`docs/CODEMAPS/languages.md`](docs/CODEMAPS/languages.md) para la matriz de capacidades completa. **22 plugins**: 13 registrados en el pipeline, 3 admitidos por el índice, 0 solo con despacho de llamadas, 5 de datos/markup, 1 de andamiaje (scaffold). `pipeline_registered` es evidencia de registro, no prueba positiva de vinculación entre archivos.
`pipeline_registered`: C, C++, C#, Go, Java, JavaScript, Kotlin, PHP, Python, Ruby, Rust, Swift, TypeScript | `index_admitted`: Bash, Lua, Scala | `call_dispatch_only`:  | `data_markup`: CSS, HTML, Markdown, SQL, YAML | `scaffold`: JSON
<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->

## Configuración

Casi nada. Los valores predeterminados están diseñados para que puedas conectarlo a tu agente y olvidarte:

* **Formato de salida**: JSON. El parámetro `output_format: "json"` se conserva por explicitud.
* **Raíz del proyecto**: `TREE_SITTER_PROJECT_ROOT` (variable de entorno, MCP) o `--project-root` (CLI).
* **Ubicación de la caché**: `<project>/.ast-cache/`. Segura de eliminar — se reconstruye automáticamente.
* **Opcional**: `TREE_SITTER_OUTPUT_PATH` como destino de escritura para salidas grandes.

### Alcance de la evidencia de instantáneas por plataforma

El análisis de archivos ordinario, la creación/actualización del índice, y las consultas
heredadas respaldadas por índice son independientes del acceso certificado a instantáneas
(snapshots). Sus rutas operativas existentes en Windows no requieren el nuevo núcleo
privado de instantáneas WAL. Pueden crear o actualizar la caché; el acceso certificado de
solo lectura tiene un contrato separado.

La implementación de instantáneas añade **captura de evidencia de base de datos/WAL privada
exclusiva de POSIX**, que requiere operaciones relativas a descriptores, `O_NOFOLLOW`, un
directorio temporal externo seguro, y comprobaciones exitosas de origen/manifiesto/proyección.
**No** aporta paridad de instantáneas de solo lectura en Windows ni extiende la puerta de
calificación existente para consumidores explícitos con `access_mode="read_existing"`.

La certificación de instantáneas en Windows ya no estaba disponible en la línea base de
develop (`SECURE_FD_SNAPSHOT_UNSUPPORTED`). Sigue sin estar disponible en esta implementación
(`WAL_PRIVATE_SNAPSHOT_UNSUPPORTED`, `completeness="unknown"`, sin token de instantánea). Esto
no es una afirmación de que el índice físico esté vacío ni de que las consultas ordinarias
estén deshabilitadas. No se ha realizado la calificación nativa de Windows para la nueva ruta
de captura; una prueba local de capacidad no la sustituye.

El estado `certified_at` por archivo no reemplaza la autoridad completa de instantáneas. El
historial persistente `partial_at` **no está implementado ni incluido en este PR**. Una
proyección incompleta o no verificable no puede autorizar a un consumidor certificado.

---

## Calidad y pruebas

| Métrica | Valor |
|---|---|
| Pruebas superadas | Suite de pruebas integral ✅ |
| Cobertura | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| Seguridad de tipos | mypy |
| Plataformas | macOS · Linux · Windows para operaciones ordinarias; la evidencia de instantáneas tiene el alcance más limitado descrito arriba |
| Puertas de pre-commit | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # bounded local quick gate
uv run pytest tests/ -q --timeout=120 -m "not e2e and not network and not benchmark"  # comprehensive local suite
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1                  # quick gate, one worker (lower CPU load)
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1                  # quick gate, two workers (balanced)
uv run pytest --lf --maxfail=1                  # rerun only failed tests from last run
uv run python check_quality.py --new-code-only  # quality gate
```

---

## Solución de problemas

| Síntoma | Solución |
|---|---|
| `unsupported language` en `.swift / .kt / .rb / .php / .cs` | Actualiza a una versión soportada actual — la brecha del lenguaje faltante se corrigió en el commit `50e99a8f`. Los módulos de gramática para lenguajes controlados por extras no vienen empaquetados en la instalación base; ejecuta `pip install "tree-sitter-analyzer[swift]"` (o `kotlin`, `ruby`, `php`, `csharp`) para añadirlos. |
| El servidor MCP no aparece en el cliente | `TREE_SITTER_PROJECT_ROOT` debe ser una **ruta absoluta** (p. ej. `$(pwd)` o `/home/user/project`); una ruta relativa hace que el servidor resuelva contra el directorio incorrecto. Reinicia el cliente después de editar. Ejecuta `tree-sitter-analyzer --doctor` para verificar. |
| `database is locked` | Detén cualquier otro proceso que tenga abierto `.ast-cache/index.db`; si persiste, `rm -rf .ast-cache && tree-sitter-analyzer --full-index`. |
| Primera llamada lenta o índice faltante | Algunas herramientas precalientan el índice automáticamente. Ejecuta `--full-index` de antemano antes de las consultas indexadas. |
| El agente elige la herramienta equivocada | Usa una skill `tsa-*` (`/tsa-graph`, `/tsa-find`, ...) — cada skill restringe el conjunto de herramientas visible a su flujo de trabajo dedicado. |

---

## Desarrollo

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
uv run pytest -q                                # quick gate (bounded)
```

Consulta **[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)** para la guía de desarrollo.

---

## Contribuciones y licencia

* ⭐ Una estrella en GitHub ayuda a que esta herramienta llegue a otros usuarios de agentes de IA.
* 💖 [Patrocinador](https://github.com/sponsors/aimasteracc) — apoya el desarrollo continuo de MCP / Skills.
* Patrocinador principal: **[@o93](https://github.com/o93)**.
* Con licencia MIT — consulta [LICENSE](LICENSE).
* Historial de versiones: [CHANGELOG.md](CHANGELOG.md).
