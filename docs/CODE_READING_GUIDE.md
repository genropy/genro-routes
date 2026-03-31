# genro-routes — Guida alla Lettura del Codice

**Version**: 0.16.0
**Status**: 🔴 DA REVISIONARE — Documento non ancora approvato

Questa guida accompagna chi legge il codice sorgente per la prima volta.
Per ogni modulo spiega **cosa fa**, **come funziona** e soprattutto
**perché è fatto così** quando il pattern non è ovvio.

> **Ordine di lettura consigliato**: segui la numerazione dei capitoli.
> Ogni capitolo presuppone la comprensione dei precedenti.

---

## Indice

1. [La grande idea](#1-la-grande-idea)
2. [Mappa dei file](#2-mappa-dei-file)
3. [Il decoratore `@route` — markers, non mutazioni](#3-il-decoratore-route--markers-non-mutazioni)
4. [RouterInterface — il contratto minimo](#4-routerinterface--il-contratto-minimo)
5. [BaseRouter — il cuore del routing](#5-baserouter--il-cuore-del-routing)
6. [RouterNode — il wrapper callable](#6-routernode--il-wrapper-callable)
7. [RoutingClass — il mixin che collega tutto](#7-routingclass--il-mixin-che-collega-tutto)
8. [Router — BaseRouter + plugin pipeline](#8-router--baserouter--plugin-pipeline)
9. [Il sistema di plugin](#9-il-sistema-di-plugin)
10. [I plugin built-in](#10-i-plugin-built-in)
11. [Eccezioni](#11-eccezioni)
12. [Pattern non standard — riepilogo ragionato](#12-pattern-non-standard--riepilogo-ragionato)
13. [Glossario rapido](#13-glossario-rapido)

---

## 1. La grande idea

genro-routes è un **motore di routing agnostico rispetto al trasporto**.

In Flask/FastAPI/Django le route sono legate a HTTP: verbi, URL pattern,
status code. Qui le route sono **operazioni con nome** (`list_orders`,
`create_user`) registrate su **istanze di oggetti**. Il protocollo
(HTTP, WebSocket, MCP, Telegram, CLI) è un adattatore separato che vive
in un altro pacchetto (es. `genro-asgi`).

```
┌──────────────────────────────┐     ┌────────────────────────┐
│  genro-routes                │     │  Transport adapter     │
│  - registra handler          │     │  (genro-asgi, ecc.)    │
│  - organizza in gerarchie    │     │  - mappa HTTP → node() │
│  - applica plugin            │     │  - gestisce I/O        │
│  - espone introspezione      │     │  - serializza risposte │
└──────────────────────────────┘     └────────────────────────┘
```

Conseguenza fondamentale: **i router vivono sulle istanze, non come
singleton globali**. Ogni `MyService()` crea i propri router con i
propri plugin. Nessuno stato condiviso.

---

## 2. Mappa dei file

```
src/genro_routes/
├── __init__.py              ← API pubblica + auto-import dei plugin
├── exceptions.py            ← 4 eccezioni (NotFound, NotAuthorized, ecc.)
├── core/
│   ├── __init__.py          ← re-export aggregator
│   ├── router_interface.py  ← ABC con 2 metodi: node() e nodes()
│   ├── decorators.py        ← @route — puro marker, zero side-effect
│   ├── context.py           ← RoutingContext — container estensibile con parent chain
│   ├── base_router.py       ← 977 righe — cuore: binding, risoluzione, introspezione
│   ├── router_node.py       ← wrapper callable restituito da node()
│   ├── router.py            ← estende BaseRouter con plugin e middleware
│   └── routing.py           ← RoutingClass mixin + _RoutingProxy
└── plugins/
    ├── __init__.py           ← solo docstring, nessun import
    ├── _base_plugin.py       ← MethodEntry + BasePlugin + _wrap_configure
    ├── logging.py            ← LoggingPlugin — timing e logging
    ├── pydantic.py           ← PydanticPlugin — validazione input + response schema
    ├── auth.py               ← AuthPlugin — RBAC con tag-matching
    ├── env.py                ← EnvPlugin + CapabilitiesSet — feature flags dinamici
    ├── openapi.py            ← OpenAPIPlugin + OpenAPITranslator
    └── channel.py            ← ChannelPlugin — filtraggio per canale di trasporto
```

**Dimensioni**: ~4.300 righe totali di codice sorgente.

---

## 3. Il decoratore `@route` — markers, non mutazioni

**File**: `core/decorators.py` (88 righe)

```python
@route("api")
def list_orders(self):
    ...

@route("api", name="detail", auth="admin")
def handle_detail(self, order_id: int):
    ...
```

### Cosa fa

Appende un dizionario nella lista `func._route_decorator_kw`.
Non tocca nessun router. Non importa nessun modulo pesante.
Restituisce la funzione **identica**.

### Perché è sorprendente

In Flask `@app.route("/path")` muta immediatamente il router globale.
Qui il decoratore viene eseguito a **tempo di definizione della classe**
(import time), quando l'istanza del router non esiste ancora.

### Perché è fatto così

Il router è instance-scoped. La classe `MyService` può essere istanziata
N volte, ognuna con il proprio router. Il decoratore deve essere
condiviso a livello di classe (via MRO), quindi non può parlare con
nessuna istanza specifica. La soluzione: annota la funzione e lascia
che il router scopra i marker più tardi (lazy binding).

### Dettagli da notare

- **Stackabile**: più `@route` sulla stessa funzione creano marker
  multipli → la funzione viene registrata su più router.
- **`router=None`**: significa "usa il default_router", che funziona
  solo se la classe ha esattamente un router.
- **`**kwargs`** extra (es. `auth="admin"`, `logging_before=False`)
  finiscono nel payload e vengono poi smistati ai plugin.

---

## 4. RouterInterface — il contratto minimo

**File**: `core/router_interface.py` (83 righe)

ABC con due soli metodi astratti:

| Metodo | Scopo |
|--------|-------|
| `node(path, **kwargs)` | Risolvi un path → RouterNode callable |
| `nodes(basepath, lazy, mode, pattern, forbidden, **kwargs)` | Introspezione: restituisci l'albero di entry e child router |

Qualsiasi oggetto che implementa questa interfaccia può essere usato
dove serve un router (duck typing). Questo permette a pacchetti esterni
come `genro-asgi` di creare oggetti router-compatibili senza dipendere
dall'implementazione di BaseRouter.

---

## 5. BaseRouter — il cuore del routing

**File**: `core/base_router.py` (977 righe)

Questa è la classe più importante. Implementa tutto il routing senza
alcuna logica di plugin. Router (sottoclasse) aggiunge solo plugin e
middleware.

### 5.1 Costruttore e slot

```python
__slots__ = (
    "instance",        # owner: l'istanza di RoutingClass
    "name",            # nome del router (es. "api")
    "prefix",          # prefisso da strippare (es. "handle_")
    "description",     # descrizione human-readable
    "default_entry",   # fallback entry (default: "index")
    "__entries_raw",   # dict nome → MethodEntry (⚠️ name-mangled!)
    "_children",       # dict alias → child router
    "_get_defaults",   # kwargs di default per get_kwargs
    "_is_branch",      # se True, non accetta handler diretti
    "_bound",          # flag lazy binding
)
```

**⚠️ Pattern: name mangling di `__entries_raw`**

L'attributo `__entries_raw` (doppio underscore) subisce il name mangling
di Python → diventa `_BaseRouter__entries_raw`. Questo è intenzionale:
protegge l'attributo dall'accesso accidentale da parte dei consumer.
In `router.py` vedrai l'accesso esplicito:

```python
for entry in self._BaseRouter__entries_raw.values():
```

Questo è necessario quando Router vuole accedere ai dati grezzi senza
triggerare il lazy binding (la property `_entries` chiamerebbe `_bind()`).

### 5.2 Lazy binding

```python
@property
def _entries(self):
    if not self._bound:
        self._bind()
    return self.__entries_raw
```

La prima volta che qualcuno accede a `_entries` (via `node()`, `nodes()`,
o qualsiasi operazione), viene chiamato `_bind()` che esegue `add_entry("*")`.

`add_entry("*")` scatena `_register_marked()`, che:

1. Cammina la MRO di `type(self.instance)` (classe derivata prima)
2. Per ogni classe nella MRO, scansiona `__dict__` cercando funzioni
   con l'attributo `_route_decorator_kw`
3. Per ogni marker il cui `name` corrisponde a questo router, registra
   la funzione come entry

**Perché lazy**: l'ordine di creazione dei router e dei plugin nel
`__init__` non importa. Plugin possono essere aggiunti dopo la creazione
del router. Tutto si risolve al primo uso.

### 5.3 Registrazione degli handler

`add_entry(target)` accetta:

| Tipo di target | Comportamento |
|----------------|--------------|
| `"*"`, `"_all_"`, `"__all__"` | Scopri tutti i `@route` marker (wildcard) |
| Stringa con virgole `"a,b,c"` | Registra ogni nome come entry separato |
| Stringa semplice `"my_method"` | Cerca `getattr(self.instance, "my_method")` |
| Callable | Registra direttamente come entry |
| Lista/tupla/set | Itera e registra ognuno |

**Smistamento delle opzioni plugin**: le keyword con `_` vengono
analizzate. Se la parte prima dell'underscore è un nome di plugin noto,
la keyword viene raggruppata come opzione plugin. Es:

```python
@route("api", auth_rule="admin", logging_before=False, meta_category="users")
```

Diventa:
- `plugin_options = {"auth": {"rule": "admin"}, "logging": {"before": False}}`
- `core_options = {"meta": {"category": "users"}}`

**Shorthand**: se la keyword **senza underscore** è un nome di plugin
noto e quel plugin dichiara `plugin_default_param`, viene mappata al
parametro di default. Così `auth="admin"` equivale a `auth_rule="admin"`.

### 5.4 Risoluzione dei path — `_find_candidate_node(path)`

Questo è l'algoritmo di routing. Non usa regex, non usa URL pattern.

```
Path: "orders/create"
         │       │
         │       └─ cerca in entries del child router
         └─ cerca in _children del router corrente
```

Algoritmo step by step:

1. Se il path è vuoto → ritorna il `default_entry` del router
2. Splitta per `/` → `["orders", "create"]`
3. Per ogni segmento:
   - Se è una entry → **trovata**, i segmenti rimanenti diventano `partial`
   - Se è un child router → **naviga** nel child e continua
4. Se la navigazione si esaurisce senza entry → usa il `default_entry`
   dell'ultimo router raggiunto, con i segmenti rimasti come `partial`

I segmenti `partial` vengono poi mappati ai parametri posizionali
dell'handler tramite ispezione della signature (vedi RouterNode).

**Esempio**:
```
router.node("users/get_user/42")
→ naviga nel child "users"
→ trova entry "get_user"
→ partial = ["42"]
→ "42" viene mappato al primo parametro posizionale di get_user()
```

### 5.5 Introspezione — `nodes()`

`nodes()` costruisce un dizionario annidato dell'intero albero di routing.
Supporta:

| Parametro | Effetto |
|-----------|---------|
| `basepath="child/grand"` | Naviga e restituisce solo quel sottoalbero |
| `lazy=True` | I child router restano come riferimenti (non espansi) |
| `mode="openapi"` | Output in formato OpenAPI flat |
| `mode="h_openapi"` | Output in formato OpenAPI gerarchico |
| `pattern="^get_"` | Filtra entry per regex |
| `forbidden=True` | Include entry bloccate con il motivo |
| `**kwargs` | Filtri plugin (es. `auth_tags="admin"`) |

### 5.6 Hook per sottoclassi

BaseRouter definisce 4 hook no-op che Router sovrascrive:

| Hook | Quando è chiamato | Cosa fa Router |
|------|-------------------|----------------|
| `_wrap_handler(entry, call_next)` | Rebuild dei handler | Costruisce la pipeline middleware |
| `_after_entry_registered(entry)` | Dopo la registrazione | Applica plugin config e `on_decore` |
| `_on_attached_to_parent(parent)` | Dopo attach_instance | Eredita i plugin dal parent |
| `_describe_entry_extra(entry, desc)` | Durante nodes() | Aggiunge info plugin per introspezione |

---

## 6. RouterNode — il wrapper callable

**File**: `core/router_node.py` (233 righe)

RouterNode è ciò che `router.node("path")` restituisce. È un oggetto
**callable**: `node()()` invoca l'handler.

### Cosa fa

1. Riceve il router, il nome dell'entry (opzionale) e i segmenti `partial`
2. Risolve l'entry (dal nome o dal `default_entry`)
3. Mappa i segmenti partial ai parametri posizionali dell'handler
   (`_assign_partial`)
4. Quando viene chiamato (`__call__`), mergia i partial con gli args
   espliciti e invoca `entry.handler`

### Mapping path → parametri (`_assign_partial`)

```python
# Handler: def get_user(self, user_id, detail=None): ...
# Path:    "get_user/42/full"
# partial: ["42", "full"]
# → partial_kwargs = {"user_id": "42", "detail": "full"}
```

L'ispezione avviene via `inspect.signature`. Se ci sono segmenti extra
e la funzione non ha `*args`, il nodo è invalido (NotFound).

### Precedenza path > kwargs

```python
filtered_kwargs = {k: v for k, v in kwargs.items() if k not in self._partial_kwargs}
```

I valori estratti dal path **vincono** su quelli passati come keyword.

### Exception mapping

Ogni RouterNode ha un dizionario `_exceptions` che mappa codici errore
a classi di eccezione. Il chiamante può personalizzarle:

```python
node = router.node("action", errors={"not_found": MyHTTPNotFound})
```

Se il nodo ha `error` settato, `__call__` lancia l'eccezione mappata.

---

## 7. RoutingClass — il mixin che collega tutto

**File**: `core/routing.py` (572 righe)

Questo mixin è il ponte tra le classi utente e i router. Chi usa
genro-routes eredita da `RoutingClass`.

### 7.1 `__slots__` — isolamento dello stato

```python
__slots__ = (
    "__routing_proxy__",
    "__genro_routes_router_registry__",
    "_routing_parent",
    "_context",
    "_capabilities",
)
```

Tutti gli attributi del framework sono in slot dedicati → non inquinano
il namespace dell'utente. `__routing_proxy__` e
`__genro_routes_router_registry__` hanno nomi volutamente lunghi per
evitare collisioni.

### 7.2 `__setattr__` — auto-detach dei child ⚠️

```python
def __setattr__(self, name, value):
    current = self._get_current_routing_attr(name)
    if current is not None:
        self._auto_detach_child(current)
    object.__setattr__(self, name, value)
```

**Questo è un side-effect importante**: ogni assegnamento di attributo
su un RoutingClass passa per questa logica. Se l'attributo precedente
era un child RoutingClass collegato a questo parent, viene automaticamente
staccato da tutti i router.

**Perché**: evita memory leak e router orfani. Se fai
`parent.child = AltroChild()`, il vecchio child viene rimosso dalla
gerarchia senza bisogno di chiamare `detach_instance()` manualmente.

**Nota**: `object.__setattr__` è usato in diversi punti del codice
per *bypassare* questo `__setattr__` custom quando non si vuole il
controllo di auto-detach (es. durante l'inizializzazione interna).

### 7.3 `_register_router(router)` — registrazione automatica

Quando crei `Router(self, name="api")`, il costruttore di BaseRouter
chiama `self.instance._register_router(self)`. Il router si
auto-registra nel registry dell'owner.

### 7.4 `routing` property — il proxy

```python
@property
def routing(self):
    proxy = getattr(self, "__routing_proxy__", None)
    if proxy is None:
        proxy = _RoutingProxy(self)
        setattr(self, "__routing_proxy__", proxy)
    return proxy
```

Restituisce un `_RoutingProxy` cached. Il proxy raggruppa tutte le
operazioni di management senza inquinare il namespace della classe:

| Metodo del proxy | Scopo |
|------------------|-------|
| `get_router(name)` | Lookup di un router per nome |
| `configure(target, **opts)` | Configurazione plugin via target syntax |
| `attach_instance(child)` | Collega un child RoutingClass |
| `configure("?")` | Introspezione: descrive tutti i router |

**Target syntax per configure**: `"router:plugin/selector"`

```python
svc.routing.configure("api:logging/_all_", before=False)
svc.routing.configure("api:auth/admin_*", rule="admin")
```

Il selettore supporta glob pattern (`fnmatchcase`).

### 7.5 `context` property — ContextVar per-task

Il context (`RoutingContext`) viene settato dall'adapter (ASGI, ecc.)
e memorizzato in una `ContextVar` a livello modulo. Tutte le istanze
RoutingClass nello stesso task condividono lo stesso context:

```python
from contextvars import ContextVar

_context_var: ContextVar[RoutingContext | None] = ContextVar(
    "routing_context", default=None
)

@property
def context(self):
    return _context_var.get()

@context.setter
def context(self, value):
    _context_var.set(value)
```

La stratificazione (server → app → request) è gestita dal parent chain
dentro `RoutingContext`, non da `RoutingClass`:

```python
server_ctx = RoutingContext()
server_ctx.server = server

app_ctx = RoutingContext(parent=server_ctx)
app_ctx.app = app

ctx = RoutingContext(parent=app_ctx)
ctx.db = db_connection

svc.context = ctx
# svc.context.db → locale
# svc.context.server → risale il parent chain fino a server_ctx
```

---

## 8. Router — BaseRouter + plugin pipeline

**File**: `core/router.py` (549 righe)

Router estende BaseRouter aggiungendo:

- Registry globale dei plugin (`_PLUGIN_REGISTRY` — unico stato globale)
- Istanze plugin per-router
- Pipeline middleware
- Ereditarietà plugin nelle gerarchie

### 8.1 Registry globale

```python
_PLUGIN_REGISTRY: dict[str, type[BasePlugin]] = {}
```

I plugin si auto-registrano alla fine del loro modulo:

```python
# In auth.py, ultima riga:
Router.register_plugin(AuthPlugin)
```

L'import avviene in `__init__.py`:

```python
for _plugin in ("logging", "pydantic", "auth", "env", "openapi", "channel"):
    import_module(f"{__name__}.plugins.{_plugin}")
```

### 8.2 `plug(name)` — attaccare un plugin

```python
self.api = Router(self, name="api").plug("logging").plug("auth")
```

`plug()` è chainable (restituisce `self`). Crea una `_PluginSpec`,
istanzia il plugin, e lo aggiunge alle strutture interne.

### 8.3 `__getattr__` — accesso fluente ai plugin

```python
def __getattr__(self, name):
    plugin = self._plugins_by_name.get(name)
    if plugin is None:
        raise AttributeError(...)
    return plugin
```

Questo permette `router.logging.configure(before=False)`. I plugin
diventano attributi virtuali del router.

### 8.4 Pipeline middleware — `_wrap_handler`

```python
wrapped = call_next  # = entry.func (il metodo originale)
for plugin in reversed(self._plugins):
    plugin_call = plugin.wrap_handler(self, entry, wrapped)
    wrapped = self._create_wrapper(plugin, entry, plugin_call, wrapped)
```

L'ultimo plugin attaccato è il più vicino all'handler reale. Il primo
è il più esterno (primo a eseguire, ultimo a completare).

**Il wrapper controlla `is_plugin_enabled` a runtime**: se il plugin
è disabilitato, salta direttamente al `next_handler`. Questo consente
di abilitare/disabilitare plugin **senza ricostruire la catena**.

### 8.5 Ereditarietà plugin — `_on_attached_to_parent`

Quando un child router viene attaccato a un parent:

1. Per ogni plugin del parent **non presente** nel child: viene creata
   una nuova istanza e aggiunta al child
2. Per ogni plugin del parent **già presente** nel child: viene
   chiamato `on_attached_to_parent(parent_plugin)` per decidere
   come gestire l'ereditarietà

La lista `_plugin_children` traccia i child per la propagazione
delle modifiche di configurazione.

### 8.6 `is_plugin_enabled` — cascata a 5 livelli

Ordine di risoluzione (primo trovato vince):

1. **entry locals** (runtime override via `set_plugin_enabled`)
2. **entry config** (statico via `configure(_target=handler)`)
3. **global locals** (runtime override via `set_plugin_enabled("_all_")`)
4. **global config** (statico via `configure()`)
5. **default**: `True`

La separazione config/locals permette override runtime che possono
essere impostati e rimossi indipendentemente dalla configurazione statica.

---

## 9. Il sistema di plugin

**File**: `plugins/_base_plugin.py` (380 righe)

### 9.1 `MethodEntry` — la scheda di un handler

```python
@dataclass
class MethodEntry:
    name: str                        # nome logico (es. "list_orders")
    func: Callable                   # il bound method originale
    router: Any                      # il router che lo contiene
    plugins: list[str]               # nomi dei plugin applicati
    metadata: dict[str, Any]         # metadati (plugin_config, meta_*, ecc.)
    handler: Callable = None         # il metodo dopo il wrapping middleware
```

`handler` parte uguale a `func` e viene sostituito dalla pipeline
middleware quando i plugin costruiscono i wrapper.

### 9.2 `BasePlugin` — il contratto

Ogni plugin eredita da `BasePlugin` e definisce:

**Attributi di classe (obbligatori)**:
```python
plugin_code = "auth"            # identificativo univoco
plugin_description = "..."      # descrizione human-readable
plugin_default_param = "rule"   # parametro shorthand (opzionale)
```

**Hook sovrascrivibili**:

| Hook | Quando | Scopo |
|------|--------|-------|
| `configure(*, _target, flags, ...)` | Configurazione | Definire la schema tramite la firma |
| `on_decore(router, func, entry)` | Registrazione handler | Analizzare/trasformare l'entry |
| `wrap_handler(router, entry, call_next)` | Build middleware | Restituire wrapper callable |
| `deny_reason(entry, **filters)` | `node()` / `nodes()` | Decidere l'accessibilità |
| `entry_metadata(router, entry)` | `nodes()` | Fornire metadati per introspezione |
| `on_attached_to_parent(parent_plugin)` | `attach_instance` | Gestire ereditarietà config |
| `on_parent_config_changed(old, new)` | Parent modifica config | Decidere se seguire o ignorare |

### 9.3 `__init_subclass__` — il pattern più elegante ⚠️

```python
class BasePlugin:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "configure" in cls.__dict__:
            cls.configure = _wrap_configure(cls.__dict__["configure"])
```

Ogni sottoclasse che definisce `configure()` se la vede automaticamente
wrappata da `_wrap_configure`. L'autore del plugin scrive:

```python
class AuthPlugin(BasePlugin):
    def configure(self, *, rule: str = "", enabled: bool = True,
                  _target: str = "_all_", flags: str | None = None):
        pass  # Il body è letteralmente vuoto!
```

La **firma dei parametri È la specifica di configurazione**.

`_wrap_configure` aggiunge:
1. Validazione Pydantic via `@validate_call` sulla firma originale
2. Parsing di `flags` (stringa `"enabled,before:off"` → dict booleano)
3. Gestione di target multipli (comma-separated)
4. Scrittura automatica nello store `_plugin_info` del router

**Perché è fatto così**: elimina completamente il boilerplate di
configurazione. Zero codice di validazione, zero codice di persistenza,
zero codice di serializzazione. Il plugin developer dichiara solo
i parametri accettati e i loro tipi.

### 9.4 Store di configurazione

La configurazione vive in `Router._plugin_info`:

```python
{
    "auth": {
        "_all_": {"config": {"rule": "user"}, "locals": {}},
        "admin_action": {"config": {"rule": "admin"}, "locals": {}}
    }
}
```

`_all_` è la configurazione globale; le entry specifiche la sovrascrivono.

### 9.5 Ereditarietà "segui se allineato, ignora se personalizzato"

Quando il parent modifica la sua config, `_notify_children` chiama
`on_parent_config_changed(old, new)` su ogni child. L'implementazione
di default:

- Se la config del child era **uguale** alla vecchia config del parent
  → aggiorna alla nuova
- Se la config del child era stata **personalizzata** → ignora

Questo evita sia la rigidità dell'ereditarietà forzata sia il caos
dell'indipendenza totale. La cascata si propaga ricorsivamente ai
nipoti ma si interrompe dove la config è stata personalizzata.

---

## 10. I plugin built-in

### 10.1 LoggingPlugin (`plugins/logging.py`, 175 righe)

**Hook**: `wrap_handler`

Aggiunge logging con timing a ogni chiamata handler. La closure `logged`
legge la configurazione **a runtime** (non a wrap-time), permettendo
toggle dinamici.

```python
configure(enabled=True, before=True, after=True, log=True, print=False)
```

Nota: `print` come nome parametro shadows il builtin — è intenzionale
(ha il commento `# noqa: A002`).

### 10.2 PydanticPlugin (`plugins/pydantic.py`, 247 righe)

**Hook**: `on_decore`, `wrap_handler`, `entry_metadata`

**In `on_decore`** (alla registrazione):
- Ispeziona signature e type hints
- Crea un modello Pydantic dinamico per i parametri di input
- Genera il response schema JSON dal return type hint

**In `wrap_handler`** (a runtime):
- Valida solo i parametri con type hint (quelli senza passano inalterati)
- Il check `disabled` avviene a ogni chiamata, non a wrap-time

Nota: il parametro di configurazione è `disabled` (negativo), non
`enabled`. Diverso dagli altri plugin.

### 10.3 AuthPlugin (`plugins/auth.py`, 170 righe)

**Hook**: `deny_reason`

Implementa RBAC con regole espressive:

| Regola | Significato |
|--------|-------------|
| `"admin"` | Richiede il tag "admin" |
| `"admin\|manager"` | OR: uno dei due basta |
| `"admin&internal"` | AND: servono entrambi |
| `"!guest"` | NOT: non deve avere "guest" |
| `"(admin\|manager)&!guest"` | Combinazione |

**Distinzione 401 vs 403**:
- Entry con regola ma nessun tag fornito → `"not_authenticated"` (401)
- Tag forniti ma non matchano → `"not_authorized"` (403)

**Ricorsione sui RouterInterface**: se l'entry è un router (non un
handler), itera su tutte le sue entry e child. Se almeno uno è
accessibile, il router è visibile.

### 10.4 EnvPlugin + CapabilitiesSet (`plugins/env.py`, 307 righe)

**Hook**: `deny_reason`

Filtra le entry in base alle **capability** disponibili nel sistema.
A differenza di AuthPlugin (chi sei tu), EnvPlugin riguarda **cosa è
disponibile** (Redis è attivo? Stripe è configurato?).

**`CapabilitiesSet`** è la classe base per definire capabilities dinamiche:

```python
class MyCapabilities(CapabilitiesSet):
    @capability
    def redis(self):
        return self._redis_client.ping()

    @capability
    def stripe(self):
        return self._stripe_key is not None
```

Il pattern è sorprendente: `CapabilitiesSet.__iter__` usa `dir(self)`
per scoprire i metodi marcati con `@capability`, li **chiama** a
runtime, e yield il nome solo se ritornano `True`. Non c'è cache:
ogni iterazione ri-valuta le capability.

**Accumulazione nella gerarchia**: le capability si sommano risalendo
la catena `_routing_parent`. Parent ha "redis", child ha "pyjwt" →
un'entry che richiede `redis&pyjwt` è soddisfatta.

### 10.5 ChannelPlugin (`plugins/channel.py`, 143 righe)

**Hook**: `deny_reason`

Filtra le entry in base al **canale di trasporto** (mcp, rest, bot_*, ecc.).

```python
@route("api", channel="mcp,bot_.*")
def mcp_and_bots_only(self): ...
```

- **Default closed**: senza configurazione di canali, l'entry non è
  disponibile su nessun canale
- I pattern sono **regex full-match** (`re.fullmatch`)
- `"*"` è un caso speciale (wildcard, tutto aperto)

### 10.6 OpenAPIPlugin + OpenAPITranslator (`plugins/openapi.py`, 594 righe)

**Hook**: `entry_metadata`

Il plugin aggiunge metadati espliciti (method override, tags, summary,
deprecated, security). L'`OpenAPITranslator` è una classe utility con
soli metodi statici che traduce l'output di `nodes()` in formato OpenAPI.

**HTTP method guessing**: se non viene forzato esplicitamente, il metodo
HTTP viene dedotto dalla signature:
- Tutti parametri scalari (str, int, float, bool, Enum) → **GET**
- Almeno un parametro complesso (dict, list, BaseModel) → **POST**

**Cross-plugin integration**: l'OpenAPITranslator legge i metadati di
AuthPlugin (→ `security`) e EnvPlugin (→ `x-requires`) per generare
l'output OpenAPI completo.

---

## 11. Eccezioni

**File**: `exceptions.py` (74 righe)

Quattro eccezioni, tutte con attributo `selector: str`:

| Eccezione | Codice HTTP tipico | Quando |
|-----------|--------------------|--------|
| `NotFound` | 404 | Path non risolto |
| `NotAuthenticated` | 401 | Servono credenziali, non fornite |
| `NotAuthorized` | 403 | Credenziali fornite ma insufficienti |
| `NotAvailable` | 501 | Capability mancante o canale non supportato |

Il `selector` ha formato `"router_name:path"` (es. `"api:admin/create"`).

---

## 12. Pattern non standard — riepilogo ragionato

### 12.1 `@route` come puro marker

| Pattern mainstream | Pattern genro-routes | Ragione |
|--------------------|---------------------|---------|
| `@app.route("/path")` muta il router globale | `@route("api")` annota la funzione | Router instance-scoped, no singleton |

### 12.2 Lazy binding

| Pattern mainstream | Pattern genro-routes | Ragione |
|--------------------|---------------------|---------|
| Registrazione esplicita o al tempo del decoratore | Binding al primo accesso a `_entries` | Ordine di setup irrilevante |

### 12.3 `__init_subclass__` su BasePlugin

| Pattern mainstream | Pattern genro-routes | Ragione |
|--------------------|---------------------|---------|
| Metaclass o ABC con metodi concreti | `__init_subclass__` wrappa `configure` | La firma = la schema, zero boilerplate |

### 12.4 `__setattr__` su RoutingClass

| Pattern mainstream | Pattern genro-routes | Ragione |
|--------------------|---------------------|---------|
| Chiamata esplicita `detach()` | Auto-detach alla riassegnazione dell'attributo | GC implicito della gerarchia |

### 12.5 `__getattr__` su Router

| Pattern mainstream | Pattern genro-routes | Ragione |
|--------------------|---------------------|---------|
| `router.get_plugin("logging")` | `router.logging` | Sintassi naturale |

### 12.6 `object.__setattr__` sparso nel codice

Usato per **bypassare** il `__setattr__` custom di RoutingClass quando
si impostano attributi interni che non devono triggerare l'auto-detach.
Lo vedrai in: `attach_instance`, `detach_instance`, `_register_router`,
`capabilities.setter`, `_RoutingProxy.__init__`.

### 12.7 `safe_is_instance` con stringa

```python
safe_is_instance(obj, "genro_routes.core.routing.RoutingClass")
```

Type check tramite nome completo della classe anziché import diretto.
Serve per rompere le dipendenze circolari tra `routing.py`,
`base_router.py` e `router.py` che si referenziano mutualmente.

### 12.8 Name mangling intenzionale (`__entries_raw`)

Attributo con doppio underscore per protezione. Router accede
esplicitamente a `self._BaseRouter__entries_raw` quando serve
l'accesso diretto senza triggerare il lazy binding.

### 12.9 Operations-first, non REST

| REST | genro-routes | Ragione |
|------|-------------|---------|
| `GET /users/{id}` | `node("get_user/42")()` | Il protocollo è un dettaglio del transport |
| Verbo HTTP esplicito | Metodo HTTP inferito dalla firma | Agnostico al trasporto |

### 12.10 CapabilitiesSet con `dir()` e chiamata dinamica

Un set il cui contenuto è calcolato a ogni iterazione chiamando i
metodi marcati `@capability`. Non c'è equivalente nei framework web.
Il pattern permette capability che cambiano a runtime (Redis va giù,
una feature viene attivata, ecc.).

---

## 13. Glossario rapido

| Termine | Significato |
|---------|-------------|
| **Entry** | Un handler registrato con nome logico in un router |
| **Router** | Contenitore di entry e child router, legato a un'istanza |
| **RouterNode** | Wrapper callable restituito da `node()` |
| **RoutingClass** | Mixin per classi che espongono router |
| **Plugin** | Componente che aggiunge comportamento (logging, auth, ecc.) |
| **Marker** | Attributo `_route_decorator_kw` su una funzione decorata |
| **Lazy binding** | Il router scopre i marker al primo uso |
| **Partial** | Segmenti di path non risolti, passati come argomenti |
| **Branch router** | Router organizzativo senza handler diretti |
| **Plugin store** | `Router._plugin_info` — configurazione per-plugin per-entry |
| **CapabilitiesSet** | Set di feature flags dinamici valutati a runtime |
| **Transport adapter** | Pacchetto esterno che mappa un protocollo a `node()` |

---

**Ordine di lettura consigliato dei file sorgente**:

1. `core/decorators.py` — 88 righe, il punto di ingresso concettuale
2. `core/router_interface.py` — 83 righe, il contratto
3. `plugins/_base_plugin.py` — 380 righe, MethodEntry e BasePlugin
4. `core/base_router.py` — 977 righe, il cuore (leggi i primi 500)
5. `core/router_node.py` — 233 righe, come viene invocato un handler
6. `core/routing.py` — 572 righe, il mixin e il proxy
7. `core/router.py` — 549 righe, plugin pipeline
8. I plugin in qualsiasi ordine

**Per i test**, inizia da:
- `test_router_basic.py` — uso base
- `test_node_resolution.py` — come funziona la risoluzione dei path
- `test_auth_plugin.py` — il sistema di autorizzazione
- `test_env_plugin.py` — le capabilities dinamiche
