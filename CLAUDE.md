# Claude Code Instructions - genro-routes

**Parent Document**: This project follows all policies from the central [meta-genro-modules CLAUDE.md](https://github.com/softwellsrl/meta-genro-modules/blob/main/CLAUDE.md)

## Project-Specific Context

### Current Status
- Development Status: Alpha
- Has Implementation: Yes

## Critical Testing Rules

### Rule: NO Private Methods in Tests

**I test NON DEVONO MAI usare metodi privati (che iniziano con `_`).**

Questa regola è CRITICA perché:
1. Un test che usa metodi privati testa l'implementazione, non il comportamento
2. Se il test fallisce, la tentazione è modificare l'implementazione per farlo passare
3. Questo rompe il codice di produzione per far passare un test invalido

**Pattern SBAGLIATO**:
```python
# ❌ MAI FARE QUESTO
def test_something():
    router = Router(...)
    router._add_entry(lambda: "x", name="foo")  # PRIVATO!
    router._entries["bar"] = ...                 # PRIVATO!
```

**Pattern CORRETTO**:
```python
# ✅ Usare sempre l'API pubblica
def test_something():
    class MyService(RoutingClass):
        def __init__(self):
            self.api = Router(self, name="api")

        @route("api")
        def foo(self):
            return "x"

    svc = MyService()
    # Testare via API pubblica
    handler = svc.api.get("foo")
    assert handler() == "x"
```

**Prima di scrivere QUALSIASI test**:
1. Verificare che NON si usino metodi/attributi che iniziano con `_`
2. Se serve accedere a qualcosa di privato, il test è sbagliato
3. Ripensare il test usando solo l'API pubblica

**Eccezioni ammesse** (rarissime):
- Test di plugin che devono accedere a `_plugins_by_name` per verificare la registrazione
- Devono essere esplicitamente marcati con commento `# Testing internal plugin registration`

## Coding Style Rules

### Rule: Minimal Code - No Redundant Lines

**Mai aggiungere righe di codice ridondanti o controlli inutili.**

Meno righe = meno rischio di errori = codice più leggibile.

**Pattern SBAGLIATI**:

```python
# ❌ if ridondante prima di for su dizionario vuoto
options = data.get("config", {})
if options:
    for key, val in options.items():
        process(key, val)

# ❌ variabile intermedia non necessaria
bucket = store.get(name, {})
entry = bucket.setdefault(key, {})
entry["value"] = x
```

**Pattern CORRETTI**:

```python
# ✅ for itera zero volte su dizionario vuoto
for key, val in data.get("config", {}).items():
    process(key, val)

# ✅ concatenare setdefault
store.get(name, {}).setdefault(key, {})["value"] = x
```

**Regola generale**: prima di creare una variabile intermedia o aggiungere un `if`, chiedersi se è davvero necessaria.

---

**All general policies are inherited from the parent document.**
