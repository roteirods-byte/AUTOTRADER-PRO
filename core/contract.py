def validate_out(out: dict):
    erros = []
    if not isinstance(out, dict):
        return False, ["out nao eh dict"]

    lst = out.get("lista", [])
    if not isinstance(lst, list):
        erros.append("out.lista nao eh list")
        return False, erros

    for i, it in enumerate(lst):
        if not isinstance(it, dict):
            erros.append(f"lista[{i}] nao eh dict")
            continue
        for k in ("zona", "risco", "prioridade"):
            v = it.get(k)
            if isinstance(v, (list, tuple)):
                erros.append(f"lista[{i}].{k} ainda eh list/tuple")
            elif v is None:
                erros.append(f"lista[{i}].{k} eh None")
            elif not isinstance(v, str):
                erros.append(f"lista[{i}].{k} nao eh str (eh {type(v).__name__})")

    return (len(erros) == 0), erros
