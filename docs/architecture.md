# Arquitectura operativa

## Recepción y backpressure

FastAPI valida el cuerpo con `JobCreate`, crea un UUID, persiste `QUEUED` y usa `put_nowait` sobre una
`asyncio.Queue` acotada. La respuesta no espera al modelo. Cuando la cola está llena, el trabajo queda
en `FAILED` y la API devuelve `503`.

## Persistencia

`RedisJobRepository` guarda contratos JSON en hashes `agent-job:{job_id}` y renueva su TTL con cada
transición. Este registro sirve al polling de clientes y conserva errores del background worker.

`AsyncRedisSaver` mantiene el estado interno de LangGraph. La configuración
`configurable.thread_id = job_id` vincula los checkpoints con el trabajo y permite reanudar el mismo
grafo después de una pausa o reinicio.

## Human-in-the-loop

El analista marca `requires_approval` para prioridad P1 o riesgo mayor o igual a 75. Tras validar la
evidencia, el supervisor dirige el flujo al nodo `approval`. El nodo llama `interrupt()` con un
payload serializable y el worker publica `WAITING_APPROVAL`.

El endpoint de aprobación valida que el trabajo esté esperando, lo vuelve a encolar y el worker
invoca `Command(resume=decision)` con el mismo `thread_id`. Una aprobación retorna al supervisor; un
rechazo salta a `END` y conserva el motivo.

## Observabilidad

`phoenix.otel.register` configura un exportador OTLP/HTTP. Cada ejecución del worker crea el span raíz
`agent_job.execute`, mientras OpenInference instrumenta LangChain para producir spans de los modelos
y componentes internos. El contexto contiene el identificador del trabajo, el worker y la condición
de reanudación.

## Fallos

La frontera del worker captura excepciones no controladas y persiste `FAILED`, tipo de excepción,
mensaje y hora de finalización. El worker siempre libera la posición de la cola mediante
`task_done()`. La cancelación durante el apagado se propaga y los clientes Redis se cierran de forma
explícita en el lifespan de FastAPI.
