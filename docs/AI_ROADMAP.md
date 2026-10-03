# Profyle + Claude: análisis y hoja de ruta

## 1. Punto de partida

Profyle instrumenta cada petición HTTP (FastAPI, Flask, Django) con VizTracer, guarda la
traza en SQLite y la muestra en Perfetto. Es útil, pero el desarrollador sigue teniendo que
*leer* un flamegraph de miles de frames para encontrar el problema.

Estado del intento previo de IA (rama de trabajo local, nunca publicado):

| Problema | Impacto |
|---|---|
| API key de Google escrita en `agent.py` | Credencial filtrada; **hay que revocarla** |
| La herramienta del agente ejecutaba **SQL arbitrario** (incluido `DELETE`/`DROP`) | Un prompt podía borrar la base de datos |
| El agente de LangChain/Gemini (eliminado) hacía `SELECT data` de la traza completa | Una sola petición son ~100k–200k eventos (decenas de MB): no cabe en ningún contexto |
| `store_trace` ya no llamaba al repositorio | No se guardaba ninguna traza; los 11 tests fallaban |
| Tablas normalizadas con SQL inválido (coma final, `FOREIGN KEY` antes de las columnas) | Rompían el repositorio en cuanto se llamaban |
| CORS `*` en el servidor local | Cualquier web podía leer las trazas (con código fuente) desde `localhost` |

## 2. Tesis: dónde está el valor diferencial

El cuello de botella no es el modelo, es el **contexto**. Un LLM no puede leer una traza
cruda. Y no tiene sentido construir otro chat: Claude ya es la interfaz. El valor
diferencial está en darle a Claude las trazas y cerrar el ciclo:

```
petición lenta → traza → digest compacto → Claude Code (que ya tiene el repo abierto)
      ↑                                                     ↓
  compare_traces  ←  el usuario repite la petición  ←  cambio de código
```

Ninguna herramienta de profiling de Python hace hoy de puente entre la traza y un agente de
código. Profyle ya tiene la parte difícil (captura automática por middleware, con
argumentos, valores de retorno y el código fuente embebido en la traza).

## 3. Lo implementado en este prototipo

### 3.1 Digest de trazas (`profyle/application/analysis/digest.py`)
Reconstruye el árbol de llamadas por hilo a partir de los eventos `X` de VizTracer y
produce, en ~4 KB (frente a 66 MB de JSON en la traza de prueba):

- **Ruta crítica por hilo**, plegando los frames de librería que solo dejan pasar el
  tiempo (middlewares, routers). Importante en FastAPI: los endpoints síncronos corren
  en otro hilo, así que hay una ruta por cada hilo con ≥5 % del tiempo.
- **Top de tiempo propio** (dónde se gasta realmente CPU o espera), con origen
  `user / stdlib / third_party / builtin`.
- **Tu código por tiempo inclusivo**: lo único que el desarrollador puede cambiar.
- **Llamadas repetidas desde el mismo llamador** (candidatas a N+1 o bucles calientes),
  con argumentos de ejemplo (`i=0 | i=1 | i=2` delata un N+1 al instante).
- **Tiempo de espera de I/O** estimado (sleep, sockets, drivers de BD, clientes HTTP).
- `get_call_details`: llamadores, llamados y las invocaciones más lentas con sus
  argumentos y valores de retorno.
- `get_function_source`: el código *tal y como era* cuando se grabó la traza (sale del
  `file_info` de VizTracer).
- `compare_digests`: deltas antes/después para verificar un arreglo.

Determinista, sin LLM, testeado (`tests/unit/application/analysis`).

### 3.2 Servidor MCP (`profyle mcp`)
`claude mcp add profyle -- profyle mcp`

Seis herramientas de solo lectura (`read_only_hint`) más `replay_request`. Es la pieza
de mayor valor: Claude Code combina las trazas con el repositorio, edita el código y
verifica con `compare_traces`. Probado de extremo a extremo con un cliente MCP real sobre
stdio.

### 3.3 Replay (`profyle replay`, `replay_request`)
Cada traza guarda la petición que la produjo: método, ruta, cabeceras, cuerpo de hasta
64 KB y el status de la respuesta. Así Claude puede repetirla después de un cambio y
comparar sin pedirle nada al usuario.
- **Credenciales redactadas por defecto** (`Authorization`, `Cookie`, API keys, CSRF);
  se pueden pasar al repetir o guardar con `PROFYLE_CAPTURE_SECRETS=true`.
- **Solo hosts locales** (`PROFYLE_REPLAY_ALLOW_REMOTE=true` para cambiarlo).
- **POST/PUT/PATCH/DELETE** solo con permiso explícito (`allow_unsafe_method`).
- Espera a que se guarde la traza nueva, devuelve sus ids y la mediana, y **avisa si el
  status cambia** (un "arreglo" que devuelve 500 no es un arreglo).

Al probarlo con uvicorn real apareció un fallo de fondo: en Python < 3.12, VizTracer solo
engancha los hilos creados mientras traza. Los endpoints síncronos de FastAPI corren en
un pool de hilos reutilizado, así que **a partir de la segunda petición su código era
invisible**. Se corrige activando el tracing en el hilo del pool mientras dura la
petición (`middleware/threadpool.py`); en 3.12+ no hace falta (`sys.monitoring`).

### 3.4 Plugin de Claude Code (`claude-plugin/`)
`claude plugin marketplace add vpcarlos/profyle` y
`claude plugin install profyle@profyle`.

Incluye el servidor MCP y la skill `fix-slow-endpoint`, que Claude invoca solo cuando el
usuario menciona un endpoint lento. Recorre seis pasos: encontrar las trazas, tomar una
línea base templada (evitando el warm-up de la primera petición), diagnosticar, arreglar
sin cambiar la respuesta, verificar con replay + `compare_traces` y reportar.

**Prueba real** (Claude Code en modo headless con el plugin, contra una app FastAPI con
un N+1; prompt: *"GET /orders is slow, can you fix it?"*). Sin intervención humana:
skill → `list_traces` → `replay_request` ×3 (línea base) → `analyze_trace` → lectura
del código → batch query → `replay_request` ×3 → `compare_traces`.
**240 ms → 22–38 ms**, status 200 sin cambios, 12 turnos y unos 0,19 USD.

### 3.6 Mejoras de experiencia tras la primera prueba real
- **Base de datos sin configurar**: `<proyecto>/.profyle/profile.db`. La app, la CLI, el
  MCP y el plugin la encuentran solos (raíz del proyecto por `pyproject.toml`, `.git`,
  etc.). La carpeta se ignora en git por sí misma (`.profyle/.gitignore` con `*`).
  `PROFYLE_DB` sigue funcionando para elegir otra ruta.
- **Verificación del cuerpo de la respuesta**: se guarda una huella, no el cuerpo, con
  dos niveles: hash del cuerpo canónico y, para JSON, hash de la estructura (claves,
  tipos, longitudes de listas). Replay y `compare_traces` dicen *identical*, *same
  structure, values differ* o *DIFFERENT*, y detectan valores que varían entre
  ejecuciones (timestamps, ids).
- **`doctor`** (CLI y herramienta MCP, primer paso de la skill): qué base de datos se lee,
  si hay trazas y peticiones grabadas, si la app responde, y trazas en la ubicación
  antigua.
- El trabajo de grabar la petición y la respuesta se hace **después** de parar el tracer,
  para que Profyle no aparezca en la traza que mide (Claude lo detectó en la segunda
  prueba).

**Segunda prueba real**, sin ninguna variable de entorno y con una sola traza (en frío):
skill → `doctor` (Ready) → `list_traces` → `replay_request` ×3 (560 ms en frío → 245 ms en
caliente) → `analyze_trace` → edición → `replay_request` ×3 → `compare_traces`.
**245 ms → 33 ms, status 200 y cuerpo idéntico**, verificado y reportado por Claude.
12 turnos y unos 0,20 USD.

### 3.5 Otros
- `profyle analyze <id>`: digest por stdout, para usar con `| claude -p "..."` o en CI.
- Base de datos por proyecto: ver 3.6.
- El SDK de MCP es un extra opcional (`profyle[mcp]`): el middleware sigue siendo
  ligero.
- Arreglado el guardado de trazas, el `TemplateResponse` con Starlette reciente, y
  eliminado CORS `*`.
- Eliminado el chat del visor (agente LangChain/Gemini, endpoint `/chat` y su UI): el
  análisis se hace desde Claude a través del MCP.

## 4. Hoja de ruta propuesta (por impacto/esfuerzo)

### Fase 1: hecho
1. **Digest precalculado**: columnas `digest` y `headline` en SQLite (migración
   automática), con versión para regenerarlos si cambia el análisis. Se calculan en el
   lado lector, nunca en la petición de la app: el servidor MCP los genera en segundo
   plano y cualquier análisis los guarda. `list_traces`, `slowest_endpoints` (sobre la
   traza típica, no la más lenta, que suele ser la fría) y la lista web muestran el
   hallazgo principal; `analyze_trace` pasa de segundos a ~8 ms.
2. **Django bajo ASGI**: medido con uvicorn. Las vistas síncronas ya se trazaban; las
   **vistas async no se trazaban nunca** (el middleware corre en un hilo y la vista en
   el del event loop), y `sync_to_async(thread_sensitive=False)` solo la primera vez. Se
   arregla en los puentes de asgiref (`async_to_sync`/`sync_to_async`), igual que con
   anyio para FastAPI. De paso apareció y se arregló un fallo que afectaba también a
   FastAPI: varias funciones síncronas de una misma petición en el mismo hilo del pool
   (p. ej. varias dependencias) solo se trazaban la primera vez. Hay que usar
   `pause()`/`resume()` de VizTracer en el mismo frame; `sys.setprofile(None)`
   desbalancea su pila.

**Pendiente de investigar**: en las primeras ~30 ejecuciones de los tests hubo 2 caídas
del intérprete (fatal error) al terminar el proceso; no se reprodujo en ~355 ejecuciones
posteriores (incluidas 100 en paralelo). Sospecha: hilos todavía enganchados a un tracer
durante el apagado. No se ha podido aislar.

### Fase 2: detectores deterministas (sin LLM, baratos y fiables)
4. **N+1 de SQL real**: los argumentos de `cursor.execute` ya se graban; normalizar el
   SQL (`WHERE id = ?`) y agrupar. Igual para SQLAlchemy, Django ORM, `httpx`/`requests`.
5. **Bloqueo del event loop**: llamadas síncronas de I/O (`time.sleep`, `requests`,
   drivers síncronos) en el hilo del loop de asyncio.
6. **Candidatos a caché**: misma función, mismos argumentos y mismo valor de retorno N
   veces en una petición (VizTracer ya graba `func_args` y `return_value`).
7. **Anotaciones en Perfetto**: inyectar los hallazgos como eventos instantáneos en la
   traza para verlos marcados en la línea de tiempo.

### Fase 3: equipos y CI
8. **Plugin de pytest (`--profyle`)** que trace los tests de integración y compare con
   una línea base por endpoint; una GitHub Action que comente el PR con la regresión y
   el diagnóstico de Claude. Para informes nocturnos, Batch API (50 % más barato).
9. **Modo "solo peticiones lentas"**: guardar la traza solo si la petición supera X ms
   (hoy `min_duration` filtra *funciones*, no peticiones), y muestreo 1/N para
   staging.

### Transversal: privacidad
10. **Redacción antes de enviar al modelo**: los argumentos y valores de retorno pueden
    contener tokens o datos personales. Añadir una capa de redacción (patrones de
    secretos, emails, cabeceras `Authorization`) en `toolkit` y un modo
    `PROFYLE_AI_SEND_VALUES=false`.

## 5. Notas de investigación sobre VizTracer

- Formato: Chrome Trace Event JSON. `traceEvents` con `ph: "X"` (completo: `ts`, `dur` en
  µs), `M` (metadatos de proceso/hilo), eventos async; `file_info.files[path] =
  [source, nlines]` y `file_info.functions[name] = [path, line]`. El nombre sigue el
  patrón `qualname (path:line)`; los builtins no llevan ruta.
- Overhead: ~1 µs por llamada; inflacionaría funciones con muchísimas llamadas (por
  ejemplo un generador con 200k iteraciones). El digest lo advierte.
- Límites: el buffer circular por defecto es de 1M entradas (`tracer_entries`); en
  peticiones largas se pierden eventos antiguos (`viztracer_metadata.overflow`). Conviene
  mostrarlo en el digest y exponer `tracer_entries` en el middleware.
- Las opciones `log_sparse`, `include_files`/`exclude_files` y `max_stack_depth`
  permiten reducir el ruido de frameworks en origen.

## 6. Cómo medir si aporta valor

- **Tiempo hasta el diagnóstico** con y sin Claude sobre un conjunto de endpoints con
  problemas sembrados (N+1, `sleep` en async, bucle caliente, falta de caché).
- **Exactitud**: % de casos donde la causa raíz y el `file:line` son correctos.
- **Mejora verificada**: % de arreglos propuestos que reducen p95 en `compare_traces`.
- **Coste por diagnóstico** (tokens): el digest debería mantenerlo en céntimos.
