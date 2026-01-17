# MOTOR PRO (modular) - NÃO muda regra, só organiza

from typing import Dict, Any, List, Tuple
from core.config import ASSERT_MIN, GAIN_MIN, UNIVERSE_77
from core.normalize import normalize_out

def normalize_par(p: str) -> str:
    return str(p or "").strip().upper().replace("USDT","").replace("-","").replace("_","")

def filter_universe(pars: List[str]) -> List[str]:
    out=[]
    seen=set()
    for p in pars:
        n=normalize_par(p)
        if n in UNIVERSE_77 and n not in seen:
            out.append(n); seen.add(n)
    return sorted(out)

def apply_filters(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # garante tipos e aplica filtros oficiais
    ok=[]
    for it in rows:
        if not isinstance(it, dict): 
            continue
        try:
            a=float(it.get("assert") or it.get("assert_%") or it.get("assert_pct") or 0)
        except:
            a=0.0
        try:
            g=float(it.get("ganho") or it.get("ganho_%") or it.get("gain") or it.get("gain_pct") or 0)
        except:
            g=0.0

        if a >= ASSERT_MIN and g >= GAIN_MIN:
            ok.append(it)
    return ok

def finalize_out(out: Dict[str, Any]) -> Dict[str, Any]:
    # normaliza campos sensíveis (zona/risco/prioridade) antes de sair
    return normalize_out(out)


def extract_pars(rows):
    # rows = lista de dicts com chave "par"
    pars=[]
    seen=set()
    for r in (rows or []):
        if not isinstance(r, dict): 
            continue
        p = normalize_par(r.get("par") or "")
        if p and p not in seen:
            pars.append(p); seen.add(p)
    return filter_universe(pars)


def rank_out(items):
    # GUARD: rank_out só aceita dict (evita crash por itens string)
    items = [it for it in (items or []) if isinstance(it, dict)]
    # ranking oficial: ASSERT% desc, depois GANHO% desc
    def fnum(x):
        try:
            if x is None: return 0.0
            if isinstance(x, (int,float)): return float(x)
            return float(str(x).replace("%","").strip())
        except:
            return 0.0

    arr = list(items or [])
    arr.sort(key=lambda it: (
        -fnum(it.get("assert")),
        -fnum(it.get("ganho")),
        str(it.get("par") or "")
    ))
    return arr
