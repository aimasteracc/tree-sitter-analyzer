

# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![Works with Claude Code · Cursor · MCP](https://img.shields.io/badge/works%20with-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**Agentes de IA con inteligencia de código en los que pueden confiar** — estructura correcta entre lenguajes para más de 20 lenguajes, nativo para agentes (MCP + CLI).

TSA indexa tu base de código con tree-sitter y sirve gráficos de llamadas correctos, búsqueda de símbolos y consultas estructurales a agentes de código IA — localmente, sin telemetría.

**¿Por qué es diferente:**
* **La corrección entre lenguajes es nuestra ventaja.** Un índice basado solo en nombres conecta Python `sorted()` con un Swift `func sorted`. TSA no lo hace. ~390× menos conexiones incorrectas en gráficos de llamadas entre lenguajes que las alternativas ([auditoría reproducible](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)).
* **Diseñado nativo para agentes.** 8 herramientas MCP, salida TOON (~mitad del tamaño de JSON en respuestas masivas/tabulares), sobres de veredicto y 13 Skills curadas — diseñado para Claude Code, Cursor y cualquier cliente MCP.
* **Amplio y correctamente clasificado.** 13 lenguajes con indexación completa de gráficos de llamadas (Python · Go · Rust · Java · JS · TS · C · C++ · C# · Swift · Kotlin · Ruby · PHP), 8 más indexados por símbolos o accesibles vía CLI.

> **Prueba:** en HuggingFace `tokenizers` (Rust+Python+JS+TS), un resolutor basado solo en nombres conecta incorrectamente **1,259** bordes de llamada — TSA: **0**. Ejecútalo en tu repositorio en segundos: `uvx --from tree-sitter-analyzer miswire-audit .`

> ¿Actualizando desde v1.x? Consulta [docs/MIGRATION.md](docs/MIGRATION.md).

---

## Inicio rápido

> **Requiere Python 3.10+** (verifica con: `python3 --version`). Instálalo desde [python.org](https://www.python.org/downloads/) si es necesario.

### Instalación automatizada (recomendada)

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

Instala automáticamente `uv` si falta, detecta Claude Desktop / Claude Code / Cursor / VS Code y escribe la entrada MCP. Ejecuta `tree-sitter-analyzer --doctor` para verificar.
Instalación en una línea para **Claude Code**:

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Reinicia tu agente y luego di: *"Ejecuta la herramienta `index` con action=status."*
Equivalente en CLI (sin agente): `tree-sitter-analyzer --codegraph-status`

> **Usuarios de PyPI / uvx — instala las skills:** las 13 `tsa-*` skills vienen empaquetadas en la rueda. Copia una vez con:
> ```bash
> tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
> tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
> ```
> Los usuarios que clonan el repositorio ya las tienen en `.claude/skills/` — no se requiere acción.

[Otros agentes (Cursor, Copilot, Cline, Continue, Claude Desktop, Roo Code) →](#supported-agents)

### Instalación rápida

#### 1. Instalar dependencias

```bash
# uv (required)
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep (required for `search action=content` text search; symbol search uses SQLite FTS5 and needs neither)
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

Consulta **[Agentes Soportados](#supported-agents)**. La mayoría de los clientes requieren esta entrada de servidor MCP:

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

**Observa la ventaja en corrección en tu propio repositorio** — sin instalación, sin CodeGraph (reindexa primero; segundos en un repo pequeño, uno o dos minutos en uno grande):

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

Imprime cuántos bordes de llamada un índice de código basado solo en nombres (el diseño que usan la mayoría de las herramientas) *conectaría incorrectamente* a través de un límite de lenguaje — p. ej., un Python `sorted()` conectado a un Swift `func sorted` — en comparación con cuántos hace TSA (≈0). En [HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md): **1,259 → 0**.

---

## ¿Por qué Tree-sitter Analyzer

* **Eficiente en tokens para salida masiva.** Cada respuesta MCP usa **TOON**, una variante tabular de JSON que reduce las cargas **masivas/tabulares** a aproximadamente la mitad comparado con JSON puro ([invariante medido](tests/unit/mcp/test_output_cost_invariants.py)). Nota: las respuestas pequeñas y cargadas de metadatos de *herramientas de decisión* son actualmente ~iguales o más grandes que JSON con el cableado actual de sobres — rastreado por un invariante strict-xfail y se está corrigiendo en [RFC-0018](rfcs/0018-response-envelope-normalization-and-adaptive-toon.md).
* **Sobres de veredicto.** Cada respuesta lleva `verdict: SAFE | CAUTION | UNSAFE | INFO | REVIEW | WARN | ERROR | NOT_FOUND`, para que los orquestadores bifurquen según los resultados sin volver a preguntar.
* **Clasificación de salud del proyecto (A–F).** Pocas herramientas de intel. de código exponen una calificación de calidad del proyecto completo — TSA clasifica por tamaño / complejidad / cobertura / duplicación / dependencias / estructura / puntos calientes de git en una sola llamada.
* **13 flujos de trabajo curados (Skills).** Subconjuntos de herramientas preconfigurados para "encontrar símbolo", "rastrear cadena de llamadas", "calificar salud", "seguro para editar antes de refactorizar", "revisión de PR", etc.
* **5 capas de seguridad.** `edit action=safe` + `edit action=guard` + DSL de restricciones + `edit action=impact` + sobres de veredicto — diseñado para que los agentes *sepan* antes de tocar.
* **Superset estricto del CLI de CodeGraph, indexación más rápida y un DSL de consulta en una sola llamada** — con una comparación honesta de costos ([abajo](#how-tsa-compares-to-codegraph)).

---

## Características clave

### Inteligencia de código pre-indexada (paridad con CodeGraph + superset)

| Capacidad | Herramienta TSA | Estado |
|---|---|---|
| Búsqueda de símbolos (FTS5 + **clasificado por BM25**) | `search` action=symbol | **avanzado** — resultados ordenados por puntuación de relevancia, no por ruta de archivo |
| Ir-a-definición / encontrar-referencias / jerarquía de llamadas en una llamada | `nav` action=navigate | Punto de entrada PRINCIPAL |
| Obtención masiva de N símbolos relacionados + mapa de relaciones | `structure` action=explore | paridad |
| Radio de impacto a nivel de función + puntuación de riesgo | `nav` action=impact | paridad + puntuación de riesgo |
| Quién-llama-X / qué-lama-X | `nav` action=callers / action=callees | paridad |
| Salud del índice de un vistazo (+ conteo de bordes) | `index` action=status | **avanzado** — informa `total_edges` para señal de densidad de gráfico |
| Caché de gráfico de llamadas pre-construido | `index` action=auto / action=full / action=sync | paridad |
| Pruebas afectadas por un cambio (CLI) | `--affected FILE...` | paridad |

### Exclusivo de Tree-sitter Analyzer

| Capacidad | Herramienta TSA | Nota |
|---|---|---|
| **Búsqueda de símbolos clasificada por BM25** | todas las herramientas de búsqueda | relevance_score en cada resultado (normalizado min-máx: mejor=1.0, peor=0.0); sort(by='confidence') en DSL |
| **Búsqueda semántica (pre-filtrada por BM25)** | `search` action=chain (`semantic()` DSL) | El prefiltro BM25 reduce 40k símbolos a ~400 antes de reordenar por coseno |
| **Clasificación de salud del proyecto A–F** | `health` action=project | 7 dimensiones (tamaño/complejidad/deps/cobertura/duplicación/estructura/punto-caliente-git), poco común entre herramientas de intel. de código |
| **Salida TOON** | cada herramienta, `output_format: "toon"` (predeterminado) | ~50 % de ahorro de tokens en salida masiva/tabular (herramientas de decisión rastreadas por RFC-0018) |
| **Sobres de veredicto** | cada herramienta | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Control de seguridad para editar** | `edit` action=safe / action=guard | rechaza ediciones de alto riesgo antes de que ocurran |
| **DSL de restricciones arquitectónicas** | `edit` action=constraints | "el módulo A no puede importar B" → aplicado |
| **Salud del código (nivel de archivo)** | `health` action=file | detección de bloques/métodos largos/code smells |
| **Jerarquía de clases** | `structure` action=class_tree | árbol de herencia de tipos |
| **Matriz de dependencias** | `health` action=matrix | matriz de acoplamiento de módulos |
| **Código muerto** | `health` action=dead | análisis transicional de inalcanzabilidad |
| **Mapa de calor de complejidad** | `health` action=heatmap | ciclo por función + vista del proyecto |
| **Detección de clones estructurales AST** | `viz` action=similarity | más allá de la similitud de texto |
| **Exportación de gráfico de llamadas Mermaid** | `viz` action=graph | listo para pegar en documentación |
| **Exportación UML Mermaid** | `viz` action=uml | diagramas de clase / paquete / componente / secuencia |
| **Revisión de PR** | `edit` action=pr | AST-diff + clasificación semántica + radio de impacto |
| **agent_summary** | cada respuesta | pista para el siguiente paso integrada en el sobre |
| **Resolutor cruzado de archivos Synapse** | interno | consciente de importaciones, supera la conjetura por regex |
| **Activación temporal** | `nav` action=lineage | frecuencia de modificación git por símbolo |
| **Orientación de archivo en un solo paso** | `project` action=smart | salud + exportaciones + deps + riesgo de edición en una llamada (reemplaza 3-4 llamadas) |
| **Diario de decisiones arquitectónicas** | `project` action=journal | persiste el razonamiento entre sesiones — poco común entre herramientas de intel. de código |

### Skills (13 flujos de trabajo curados)

CodeGraph tiene cero skills. Enviamos 13 bajo `.claude/skills/tsa-*/`:

`tsa-landing`, `tsa-find`, `tsa-graph`, `tsa-structure`, `tsa-deps`, `tsa-index`, `tsa-health-watch`, `tsa-edit-safety`, `tsa-edit-then-verify`, `tsa-constraints`, `tsa-pr-review`, `tsa-refactor-queue`, `tsa-temporal`.

Cada skill envía un subconjunto de `allowed-tools` + receta de procedimiento + esquema de superficie de decisión, para que el agente no tenga que clasificar 8 herramientas en cada pregunta.

### 321 banderas de CLI

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

Instalar el paquete también registra tres utilidades de búsqueda independientes (puntos de entrada delgados sobre el mismo motor, útiles en pipelines de shell):

```bash
list-files <dir>          # fd-style file discovery
search-content <pattern>  # ripgrep-style content search
find-and-grep <pattern>   # two-stage fd + ripgrep
```

Consulta [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md) para la superficie completa.

---

## Cómo se compara TSA con CodeGraph

### Corrección del gráfico de llamadas — TSA resuelve lo que CodeGraph conecta mal

El costo de tokens es un eje; el *primer* trabajo de una herramienta de inteligencia de código es un **gráfico correcto**.

**Cara a cara en este repositorio, índices en vivo de ambas herramientas** (cuenta cada borde de llamada cuyo lenguaje del llamante difiere del del llamado — una conexión incorrecta entre lenguajes por construcción; [reproducible](benchmarks/codegraph_compare/REPORT-v1.21.0.md)):

| herramienta | conexiones incorrectas entre lenguajes | bordes de llamada totales | tasa |
|---|---|---|---|
| CodeGraph | **745** | 38,103 | 1.96 % |
| **Tree-sitter Analyzer** | **6** | 114,160 | **0.005 %** |

**~390× más limpio en corrección entre lenguajes, mientras resuelve 3× más bordes de llamada.** Las conexiones incorrectas de CodeGraph abarcan 19+ pares de lenguajes (python→swift **408**, python→typescript 195, python→ruby 81, …); las 6 de TSA son todas `java→python/php` desde nombres de métodos Java de una sola palabra.

> **No confíes en esta tabla — ejecútalo en tu propio repositorio (sin necesidad de instalar CodeGraph):**
> ```bash
> uvx --from tree-sitter-analyzer miswire-audit .
> ```
> Indexa tu código e imprime cuántos bordes de llamada un resolutor basado solo en nombres (el diseño que usan la mayoría de los índices) *conectaría incorrectamente* a través de un límite de lenguaje versus cuántos hace TSA — con los bordes ofensivos listados (`Python sorted() → Swift func en archivo:línea`). Agrega `--card` para una tarjeta de puntuación compartible.
>
> **Ejecuciones reales:** en [HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md) (Rust+Python+JS+TS) un resolutor basado solo en nombres conectaría incorrectamente **1,259** bordes de llamada (incl. un JS `tokenize()` → def Rust) — TSA: **0**. En un repositorio de un solo lenguaje (`gin`, Go) ambos son **0** — sin falsos positivos. [Más ejemplos →](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md)

En concreto:

| llamada (Python `_resolve_entry_points` / `build_response`) | CodeGraph | TSA |
|---|---|---|
| `sorted()` (builtin de Python) | ❌ llamado = **`tests/golden/corpus_swift.swift` — un Swift `func sorted`** (conectado como llamado de **299** funciones Python en todo el repo) | ✅ `builtin` — sin borde entre lenguajes |
| `fts_search()` / `fts_search_ranked()` | ❌ vinculado al **mock de prueba** (`FallbackCache`) en lugar del método real | ✅ resuelve al método fuente (`_ast_cache_query.py` / `ast_cache.py`) |

El resolutor por lenguaje de TSA controla cada vinculación por **familia de lenguaje** a través de **13 lenguajes** (Python · Java · Go · JS · TS · C · C++ · Rust · C# · Kotlin · Ruby · PHP · Swift) y **degrada definiciones exclusivas de prueba** para llamantes no de prueba, a través de todos sus caminos de resolución. Decirle a un agente que una función Python *llama a un método Swift*, o que una llamada de producción apunta a un mock de prueba, son datos estructurales incorrectos — y es el modo de fallo dominante de un índice basado solo en nombres.

#### Correcto *y* completo — 96.3% de bordes de llamada clasificados

Un gráfico correcto que deja la mayoría de los bordes `unknown` sigue siendo medio gráfico. La cascada de resolución de TSA ahora clasifica **96.3%** de los bordes de llamada (subiendo desde 83.9%), con **cero** conexiones incorrectas entre lenguajes o sombras de prueba — cada ganancia está controlada por el proyecto no poseer ningún símbolo de lenguaje compatible con ese nombre, por lo que la sombra siempre se preserva:

| nivel de resolutor | qué resuelve | fuente |
|---|---|---|
| cascada de vinculación | local / self / import / unique-method / single-global | RFC-0002 |
| nombres de **métodos** stdlib (`write_text`, `strip`, `items`) | métodos `str` / `Path` / `dict` / `re` / `argparse` → `stdlib` | [RFC-0004](rfcs/0004-stdlib-method-resolution.md) |
| métodos de **biblioteca** externa (`raises`, `given`, `MagicMock`) | pytest / hypothesis / mock → `external` | [RFC-0005](rfcs/0005-external-method-resolution.md) |

El ~4% restante `unknown` está dominado por despacho dinámico genuinamente irresoluble (`BaseTool.execute()`), constructores y métodos del proyecto ambigüos con el mismo nombre — el piso de falsos positivos del análisis estático, dejado honesto en lugar de adivinado.

> **Ahora multi-idioma.** La resolución segura entre lenguajes ya no es solo para Python. Un **registro de resolutores** por lenguaje ([RFC-0010](rfcs/0010-resolver-language-registry.md)) le da a cada lenguaje su propia cascada de clasificación con niveles conservadores de stdlib/externo, controlados por familia de lenguaje para que una vinculación no cruce a un lenguaje incompatible. **Gráfico de llamadas activo clasificado (extracción de bordes de llamada + resolutor por lenguaje), 13 lenguajes: Python · Java · Go · JavaScript · TypeScript · C · C++ · Rust · C# · Kotlin · Ruby · PHP · Swift.** Cada uno tiene sus propios niveles conservadores de stdlib/externo y está verificado adversarialmente para nunca vincular a través de un límite de lenguaje. **Swift es notable**: la conexión principal incorrecta de CodeGraph vincula 299 llamantes Python `sorted()` a un Swift `func sorted` — TSA resuelve Swift correctamente *y* rechaza esa vinculación exacta entre lenguajes (verificado en ambas direcciones). Medido en el conjunto activo: **6** bordes entre lenguajes (6 de ~57,000 bordes resueltos, todos nombres genéricos de métodos Java de 1 palabra) — **~390× más limpio que CodeGraph** en corrección entre lenguajes, que conecta **299** llamantes Python `sorted()` a un solo Swift `func sorted` (TSA vincula **0** de 298). Auditoría completa reproducible: [`benchmarks/codegraph_compare/REPORT-v1.21.0.md`](benchmarks/codegraph_compare/REPORT-v1.21.0.md). Agregar un lenguaje es un archivo de resolutor nuevo (RFC-0010) más una pequeña conexión de extracción de llamadas.

> **También tipos de símbolos.** TSA clasifica miembros de clase como `kind=method` (20,348 filas de métodos en este repo) — `search action=symbol kind=method` los devuelve; paridad con CodeGraph, no un stub. La carga `index status` descompone símbolos por tipo y lenguaje y bordes por tipo (`edges_by_kind` — un desglose que CodeGraph no muestra).

### Dónde TSA lidera

- **Velocidad de construcción del índice.** Eliminar un paso redundante de actualización de bordes post-índice redujo un índice django en frío (~2 950 archivos) de **181 s → 97 s (−46 %)**; la ganancia crece con el tamaño del repo. La re-indexación de archivos sin cambios es una búsqueda de hash de contenido.
- **Superset estricto del CLI.** Cada herramienta MCP tiene un equivalente CLI (el CLI de CodeGraph es más delgado); los predeterminados *comportamentales* (clasificación, límites, truncamiento) se mantienen en sincronía entre las dos superficies. El formato de salida es la única divergencia intencional — MCP predetermina TOON (eficiente en tokens para agentes), el CLI a JSON (amigable para humanos/`jq`).
- **Expresividad en una sola llamada.** Un DSL de cadena estilo jQuery — `search('X').callees(depth=2).explore(include_code=true).answer(compact=true)` — devuelve el subgrafo completo de un flujo + fuente en una sola llamada, con `true`/`false` estilo JS para que los agentes lo escriban naturalmente.
- **La salida es estructurada + consciente de tokens.** TOON predeterminado para MCP (~mitad del tamaño de JSON en salida masiva/tabular; conexión de herramientas de decisión corregida en RFC-0018), pistas de truncamiento por llamada, despriorización consistente de archivos de prueba en cada camino de clasificación.
- **Amplitud.** Puntuación de salud, control de seguridad para editar / impacto de cambios, 13 Skills curadas y amplia cobertura de lenguajes.

### Sobre el costo de tokens — y un benchmark que corregimos

> **Corrección (2026-06).** Una versión anterior de esta sección afirmaba que TSA superaba a CodeGraph en costo de tokens de agente (una tabla de "−11 % mediana"). Ese benchmark tenía un error en el arnés: el servidor MCP del brazo TSA se iniciaba sin una raíz de proyecto explícita y analizaba *el propio código fuente de tree-sitter-analyzer* en lugar del repo objetivo, por lo que sus números carecían de sentido. El error está corregido (el arnés ahora pasa `--project-root`), la afirmación inflada se retira y la imagen honesta está abajo.

El costo de tokens fue el único eje donde CodeGraph lideraba. La divulgación progresiva de [RFC-0006](rfcs/0006-context-progressive-disclosure.md) cierra la mayoría de la brecha en la fuente: `nav context` ahora devuelve un **predeterminado ajustado** — puntos de entrada + una lista compacta `related_symbols` + bloques de código — y mueve el gráfico plano de nodos/bordes detrás de un opt-in `include_graph=true`. Medido en este repo (4 consultas representativas, TOON):

| carga de contexto | caracteres |
|---|---|
| TSA predeterminado, antes de RFC-0006 | ~13,900 |
| **TSA predeterminado, después (ajustado)** | **~6,600 (−53%)** |
| TSA `include_graph=true` (completo, opt-in) | ~13,900 |
| Línea base CodeGraph | ~4,400 |

La llamada de contexto dominante pasó de **~2.9× la carga de CodeGraph a ~1.5×**.

Para contexto, el costo `$` por tarea medido **antes** de RFC-0006 (arnés corregido — Claude Sonnet, gin + django, brazos MCP, sin errores):

| brazo | costo mediano (pre-RFC-0006) | llamadas de herramienta | lecturas de archivo |
|---|---|---|---|
| CodeGraph MCP | **~$0.27** | 7 | 2 |
| Tree-sitter Analyzer MCP | ~$0.44 | 7 | 1 |
| no-MCP (grep/read) | ~$0.34 | 14 | 7 |

Un re-benchmark completo `$` por tarea es la siguiente medición (comando de arnés abajo). Informamos el proxy de carga directamente en lugar de repetir la tabla vieja como si RFC-0006 no hubiera salido.

### Push reactivo + desglose por tipo de borde — dos cosas que CodeGraph no puede hacer

CodeGraph (y la mayoría de los indexadores de un solo disparo) solo responde por sondeo: preguntas, responde con una instantánea, y vuelves a preguntar para saber si algo cambió. TSA expone dos capacidades que cierran ese ciclo:

- **Push reactivo / suscripción ([RFC-0001](rfcs/0001-reactive-push.md), implementado).** `search action=subscribe` registra un selector Hyphae y devuelve un URI de recurso MCP `tsa://hyphae/{selector}`. Cuando el código observado cambia, el servidor emite una notificación de recurso actualizado — el agente vuelve a leer el recurso en lugar de sondear. `search action=unsubscribe` lo cancela. CodeGraph no tiene canal push ni de suscripción.
- **`edges_by_kind` en `index action=status`.** Status devuelve un conteo por tipo de borde (llamadas / extiende / implementa / importa …), no solo un `total_edges` — para que un agente pueda leer la forma del gráfico (cuánto pesa en llamadas vs herencia un repo) antes de profundizar. CodeGraph solo muestra un total plano.

Reproduce las correcciones en cualquier repositorio que ambas herramientas hayan indexado:

```bash
# CodeGraph: emits the cross-language / test-shadow callee
#   (e.g. `sorted` → corpus_swift.swift, `fts_search` → test mock)
# TSA after the resolver fix: language-correct, source-preferring
tree-sitter-analyzer --callees _resolve_entry_points --format json
```

> Reproduce los números de costo: `uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos gin,django`. Los sobres crudos + la corrección del arnés viven en ese directorio.

---

## Cómo funciona

```
Source code → tree-sitter parse → SQLite + FTS5 index (.ast-cache/index.db)
                                         ↓
        nav (navigate) / structure (explore) / nav (callers) / ...
                                         ↓
                            TOON-encoded envelope
                            (compact for tabular output;
                             verdict + agent_summary + data)
                                         ↓
                              MCP client / CLI consumer
```

El índice se construye perezosamente en la primera consulta, se actualiza ante cambios de archivo mediante una diferencia de hash de contenido (`index` action=sync). Las 8 herramientas leen del mismo `.ast-cache/`, por lo que una consulta y su seguimiento comparten trabajo.

---

## Agentes soportados

<details>
<summary><b>📘 Claude Code</b> (recomendada)</summary>

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

Verifica: `claude mcp list`. Las 13 `tsa-*` skills se auto-descubren desde `.claude/skills/`.

**Usuarios de PyPI / uvx** — instala las skills empaquetadas una vez con:
```bash
tree-sitter-analyzer --install-skills              # into ./.claude/skills/ (this project)
tree-sitter-analyzer --install-skills-global       # into ~/.claude/skills/ (all projects)
```
Los usuarios que clonan el repositorio ya las tienen — no se requiere acción.
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

Todos leen el mismo esquema `mcpServers` que Claude Desktop. Cursor: **Configuración → MCP**. Cline: panel MCP → Editar configuración. Continue: `~/.continue/config.json` bajo `experimental.modelContextProtocolServers`. Roo Code: panel MCP → Editar configuración MCP.
</details>

<details>
<summary><b>🐳 Docker</b> (sin Python / uv local)</summary>

El repositorio envía un [`Dockerfile`](Dockerfile) que construye el servidor MCP (transporte stdio) desde el código fuente, para que la imagen siempre coincida con el código comprometido.

```bash
# Build once
docker build -t tree-sitter-analyzer-mcp .

# Run against the current repo (server speaks MCP over stdio; -i keeps stdin open)
docker run --rm -i --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work tree-sitter-analyzer-mcp
```

`--user "$(id -u):$(id -g)"` ejecuta como tu UID/GID de host, para que `.ast-cache/`, el diario de decisiones y cualquier escritura de `edit` bajo el repo montado sean tuyos, no de root.

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

> ⚠️ `TREE_SITTER_PROJECT_ROOT` debe ser **absoluto**. El servidor aplica un límite de seguridad contra escapes mediante `SecurityValidator`.

---

## Lenguajes soportados

22 plugins de lenguajes; 13 completamente conectados en el indexador (símbolo completo + gráfico de llamadas) + 2 indexados por símbolos (conexión de gráfico de llamadas pendiente) + 5 (datos/markup) accesibles vía el camino CLI de un solo archivo + 2 andamios (plugin existe, conexión del indexador pendiente). bash y scala se graduaron en v1.22.0; el parche del 2026-05-24 desbloqueó Swift / Kotlin / Ruby / PHP / C# que habían sido omitidos en silencio durante meses.

| Nivel | Lenguajes |
|---|---|
| **Índice completo + símbolo + gráfico de llamadas** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **Índice completo + símbolos (conexión de gráfico de llamadas pendiente)** | Bash · Scala |
| **Análisis de archivo único (CLI)** | HTML · CSS · Markdown · SQL · YAML |
| **Andamio (plugin existe, conexión del indexador pendiente)** | JSON · Lua |

CodeGraph soporta un conjunto similar. **Dart, Vue, Svelte, Lua** aún no se han lanzado — backlog aspiracional, sin fecha comprometida.

---

## Configuración

Casi nada. Los valores predeterminados están diseñados para que puedas conectarlo a tu agente y olvidarlo:

* **Formato de salida**: TOON. Anula por llamada con `output_format: "json"`.
* **Raíz del proyecto**: `TREE_SITTER_PROJECT_ROOT` (var de entorno, MCP) o `--project-root` (CLI).
* **Ubicación de caché**: `<project>/.ast-cache/`. Seguro para eliminar — se reconstruye automáticamente.
* **Opcional**: `TREE_SITTER_OUTPUT_PATH` para destino de escritura de salida grande.

---

## Calidad y Pruebas

| Métrica | Valor |
|---|---|
| Pruebas pasadas | Suite de pruebas integral ✅ |
| Cobertura | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| Seguridad de tipos | 100 % mypy |
| Plataformas | macOS · Linux · Windows |
| Controles pre-commit | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # suite completa
uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # ciclo local rápido
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # modo un trabajador para menor carga de CPU
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # modo balanceado de dos trabajadores
uv run pytest --lf --maxfail=1                  # ejecutar solo pruebas fallidas de la última ejecución
uv run python check_quality.py --new-code-only  # control de calidad
```

---

## Solución de problemas

| Síntoma | Solución |
|---|---|
| `unsupported language` en `.swift / .kt / .rb / .php / .cs` | Actualiza a ≥ 1.12.x — la brecha de 5 lenguajes se parcheó en el commit `50e99a8f`. Los módulos gramaticales para lenguajes controlados por extras no vienen empaquetados en la instalación base; ejecuta `pip install "tree-sitter-analyzer[swift]"` (o `kotlin`, `ruby`, `php`, `csharp`) para agregarlos. |
| El servidor MCP no aparece en el cliente | `TREE_SITTER_PROJECT_ROOT` debe ser una **ruta absoluta** (p. ej. `$(pwd)` o `/home/user/project`); una ruta relativa hace que el servidor resuelva contra el directorio incorrecto. Reinicia el cliente después de editar. Ejecuta `tree-sitter-analyzer --doctor` para verificar. |
| `database is locked` | Detén cualquier otro proceso que tenga `.ast-cache/index.db`; si persiste, `rm -rf .ast-cache && tree-sitter-analyzer --full-index`. |
| Primera llamada lenta | La primera llamada construye el índice. Las llamadas posteriores son subsegundos. Ejecuta `--full-index` por adelantado para amortizar. |
| El agente elige la herramienta incorrecta | Usa una `tsa-*` skill (`/tsa-graph`, `/tsa-find`, ...) — cada skill restringe el conjunto de herramientas visible a un flujo de trabajo. |

---

## Desarrollo

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
uv run pytest -q
```

Consulta **[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)** para la guía de desarrollo.

---

## Contribuciones y Licencia

* ⭐ Una estrella en GitHub ayuda a mostrar esta herramienta a otros usuarios de agentes IA.
* 💖 [Patrocinador](https://github.com/sponsors/aimasteracc) — apoya el desarrollo continuo de MCP / Skills.
* Patrocinador principal: **[@o93](https://github.com/o93)**.
* Licencia MIT — ver [LICENSE](LICENSE).
* Historial de lanzamientos: [CHANGELOG.md](CHANGELOG.md).
