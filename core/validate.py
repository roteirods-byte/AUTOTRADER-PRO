from .normalize import ensure_str_fields

def validate_items(lista):
    bad=[]
    for it in lista:
        if not isinstance(it, dict):
            bad.append(("ITEM_NAO_DICT", type(it).__name__))
            continue
        ensure_str_fields(it)
        for k in ("prioridade","zona","risco"):
            v=it.get(k)
            if isinstance(v,(list,tuple)):
                bad.append((it.get("par","?"), k, v))
    return bad
