"""
AUTOTRADER-PRO — worker_pro.py
Gera:
  data/pro.json
  data/top10.json

Regras fixas:
- Fuso BRT
- GAIN_MIN base 3% (dinâmico se vol alta)
- TTL dinâmico (vol alta => menor)
- Escrita atômica (tmp -> rename)
- NÃO publicar sinais abaixo do ganho mínimo
- Não ter LONG e SHORT no mesmo par (aqui 1 sinal por par)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Literal

from .config import BRT, COINS, GAIN_MIN_BASE
from .providers.prices_provider import get_price

Side = Literal["LONG","SHORT","NÃO ENTRAR"]

@dataclass
class Sinal:
    par: str
    side: Side
    preco: float
    alvo: float
    ganho_pct: float
    assert_pct: float
    eta: str
    zona: str
    risco: str
    prioridade: str
    data: str
    hora: str
    ttl_horas: float
    expira_em: str

def _now_brt() -> datetime:
    return datetime.now(tz=BRT)

def _fmt_data_hora(dt: datetime) -> tuple[str,str]:
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")

def _market_vol_status_stub() -> str:
    # placeholder: troque por regra BTC real
    # valores: "normal" | "alta"
    return "normal"

def _gain_min(vol_status: str) -> float:
    if vol_status == "alta":
        return 4.5  # dentro do 4–6% sugerido
    return float(GAIN_MIN_BASE)

def _ttl_hours(vol_status: str) -> float:
    # TTL dinâmico
    return 3.0 if vol_status == "alta" else 8.0

def _zone_from_gain(gain: float) -> str:
    if gain >= 7:
        return "VERDE"
    if gain >= 4:
        return "AMARELA"
    return "AMARELA"

def _risk_from_gain(gain: float) -> str:
    # exemplo simples
    if gain >= 7:
        return "MÉDIO"
    return "MÉDIO"

def _prio_from_gain(gain: float) -> str:
    if gain >= 8:
        return "ALTA"
    if gain >= 5:
        return "MÉDIA"
    return "MÉDIA"

def _assert_stub(symbol: str) -> float:
    # placeholder: substitua pelo seu backtest/score
    # fixa por símbolo p/ demo
    import random
    rnd = random.Random("assert:" + symbol)
    return rnd.uniform(65.0, 92.0)

def _side_stub(symbol: str) -> Side:
    # placeholder: alterna LONG/SHORT por símbolo
    return "SHORT" if (sum(map(ord, symbol)) % 2 == 0) else "LONG"

def _build_signals() -> tuple[dict, List[Sinal], float, str]:
    now = _now_brt()
    data_str, hora_str = _fmt_data_hora(now)

    vol_status = _market_vol_status_stub()
    gain_min = _gain_min(vol_status)
    ttl_h = _ttl_hours(vol_status)
    expira = now + timedelta(hours=ttl_h)

    sinais: List[Sinal] = []
    for coin in COINS:
        preco = float(get_price(coin))
        side = _side_stub(coin)

        # alvo fake: 3–10% em cima/baixo do preço conforme side
        import random
        rnd = random.Random("gain:" + coin)
        ganho = rnd.uniform(2.0, 10.0)  # antes do filtro

        if side == "LONG":
            alvo = preco * (1 + ganho/100.0)
        elif side == "SHORT":
            alvo = preco * (1 - ganho/100.0)
        else:
            alvo = preco

        # filtro publicação: GANHO% >= gain_min
        if ganho < gain_min:
            side_out: Side = "NÃO ENTRAR"
        else:
            side_out = side

        s = Sinal(
            par=coin,
            side=side_out,
            preco=preco,
            alvo=alvo,
            ganho_pct=ganho if side_out != "NÃO ENTRAR" else 0.0,
            assert_pct=_assert_stub(coin),
            eta=f"~{int(ttl_h)}h",
            zona=_zone_from_gain(ganho) if side_out != "NÃO ENTRAR" else "—",
            risco=_risk_from_gain(ganho) if side_out != "NÃO ENTRAR" else "—",
            prioridade=_prio_from_gain(ganho) if side_out != "NÃO ENTRAR" else "—",
            data=data_str,
            hora=hora_str,
            ttl_horas=ttl_h,
            expira_em=expira.isoformat(),
        )
        sinais.append(s)

    # top10: apenas sinais válidos e ainda “vivos”
    valid = [s for s in sinais if s.side in ("LONG","SHORT")]
    valid.sort(key=lambda x: (x.ganho_pct), reverse=True)
    top10 = valid[:10]

    payload_common = {
        "ultima_atualizacao": f"{data_str} {hora_str}",
        "regra_gain_min": gain_min,
        "status_volatilidade": vol_status,
    }
    return payload_common, sinais, gain_min, vol_status, top10

def _atomic_write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)

def main():
    base = Path(__file__).resolve().parents[1]  # .../AUTOTRADER-PRO
    data_dir = Path(os.environ.get("DATA_DIR", str(base / "data")))

    payload_common, sinais, gain_min, vol_status, top10 = _build_signals()

    pro_obj = dict(payload_common)
    pro_obj["sinais"] = [asdict(s) for s in sinais]

    top10_obj = dict(payload_common)
    top10_obj["sinais"] = [asdict(s) for s in top10]

    _atomic_write_json(data_dir / "pro.json", pro_obj)
    _atomic_write_json(data_dir / "top10.json", top10_obj)

if __name__ == "__main__":
    main()
