def norm_key(s):
    return (s or "").strip().upper()

def normalize_side(x):
    s = norm_key(x)
    if s in ("NAO ENTRAR","NÃO ENTRAR","NE",""):
        return "NÃO ENTRAR"
    if s in ("LONG","COMPRA","BUY"):
        return "LONG"
    if s in ("SHORT","VENDA","SELL"):
        return "SHORT"
    return s

def last_if_list(v):
    if isinstance(v, (list, tuple)) and v:
        return v[-1]
    return v

def ensure_str_fields(it: dict, keys=("zona","risco","prioridade")):
    for k in keys:
        v = it.get(k)
        v = last_if_list(v)
        if v is None:
            it[k] = ""
        else:
            it[k] = str(v)
    return it

# --- compat: API usada pelo worker_pro.py ---
def normalize_out(out):
    """Normaliza campos para string (zona/risco/prioridade) antes do json.dump."""
    try:
        if isinstance(out, dict):
            lst = out.get("lista")
            if isinstance(lst, list):
                for it in lst:
                    if isinstance(it, dict):
                        for k in ("prioridade", "risco", "zona"):
                            v = it.get(k)
                            if isinstance(v, (list, tuple)):
                                it[k] = (v[-1] if v else "")
                            elif v is None:
                                it[k] = ""
        return out
    except Exception:
        return out
