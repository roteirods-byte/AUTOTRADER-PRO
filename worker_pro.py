from core.compute import finalize_out
from core.compute import rank_out
from urllib.parse import urlencode

# ---------------- Exchanges: OKX -> GATE -> KUCOIN ----------------
def okx_inst(par):
  p = (par or "").strip().upper().replace("USDT","").replace("-","").replace("_","")
  return f"{p}-USDT"

def gate_pair(par):
  p = (par or "").strip().upper().replace("USDT","").replace("-","").replace("_","")
  return f"{p}_USDT"

def kucoin_symbol(par):
  p = (par or "").strip().upper().replace("USDT","").replace("-","").replace("_","")
  return f"{p}-USDT"

def _okx(bar, par, limit):
  inst = okx_inst(par)
  inst_okx = inst if str(inst).endswith("-SWAP") else f"{inst}-SWAP"
  url = f"https://www.okx.com/api/v5/market/candles?instId={inst_okx}&bar={bar}&limit={limit}"
  # PATCH3B: OKX SWAP por padrão (mais cobertura)
  d = http_json(url, timeout=10)
  arr = (d.get("data") or [])
  out=[]
  for x in reversed(arr):
    try:
      ts=int(x[0]); o=float(x[1]); h=float(x[2]); l=float(x[3]); c=float(x[4])
      out.append((ts,o,h,l,c))
    except: pass
  return out

def _gate(interval, par, limit):
  pair = gate_pair(par)
  url = f"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair={pair}&interval={interval}&limit={limit}"
  arr = http_json(url, timeout=10)
  out=[]
  for x in reversed(arr or []):
    try:
      ts=int(float(x[0]))*1000
      c=float(x[2]); h=float(x[3]); l=float(x[4]); o=float(x[5])
      out.append((ts,o,h,l,c))
    except: pass
  return out

def _kucoin(typ, par, limit=120):
  sym = kucoin_symbol(par)
  url = f"https://api.kucoin.com/api/v1/market/candles?symbol={sym}&type={typ}"
  d = http_json(url, timeout=10)
  arr = (d.get("data") or [])
  out=[]
  for x in reversed(arr[:limit]):
    try:
      ts=int(float(x[0]))*1000
      o=float(x[1]); c=float(x[2]); h=float(x[3]); l=float(x[4])
      out.append((ts,o,h,l,c))
    except: pass
  return out


#!/usr/bin/env python3
# =============================================================================
# AUTOTRADER-PRO (PRO_V5) — CRITÉRIOS PRINCIPAIS (RESUMO)
# 1) Universo: lê MFE e POSICIONAL (apenas para pegar quais moedas analisar).
# 2) Mercado real (sem “filtro 5 dias”): usa candles 1H e 4H via OKX/Gate/Kucoin.
# 3) ALVO + ETA COERENTES (mesmo motor):
#    - ALVO: distância = max( ganho_min%, 2*ATR_4H )
#    - ETA: horas ≈ distância / ATR_1H  (resultado varia por moeda)
# 4) Assertividade reforçada:
#    - Confirma tendência em 1H e 4H (EMA20/EMA50) + ajustes com RSI
# 5) Publica só sinais bons:
#    - assert >= 70 e ganho >= 3
# 6) Ranking final: prioridade -> maior assert -> maior ganho -> menor ETA
# =============================================================================

from core.normalize import normalize_out
from core.contract import validate_out
import json, re, math
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor, as_completed

TZ = ZoneInfo("America/Sao_Paulo")

URLS = [
  ("MFE",        "http://127.0.0.1:8082/api/entrada"),
]

# >>> PARAMETROS DO MODELO (AJUSTE SEM MEXER NO CODIGO: via ENV) <<<
# OBS: Agora o GANHO é calculado como ROE% (ganho líquido no FUTURO USDT PERP),
#      considerando alavancagem + taxas + funding (estimado) + slippage (estimado).
#      Se quiser trocar o perfil (sua corretora/VIP), ajuste as variáveis abaixo.

import os

# PATCH_ATOMIC_JSON: evita arquivo cortado (write tmp + replace)
def _atomic_write_json(path, data, mode=0o644):
  import os, json
  tmp = str(path) + '.tmp'
  with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.flush()
    try:
      os.fsync(f.fileno())
    except Exception:
      pass
  os.replace(tmp, str(path))
  try:
    os.chmod(str(path), mode)
  except Exception:
    pass


# Regra visual (não filtra): ASSERT só colore (>=65 verde, <65 vermelho no site)
ASSERT_MIN = float(os.environ.get("ASSERT_MIN", "65"))

# Regra de operação: só publica se ROE% >= GAIN_MIN
GAIN_MIN   = float(os.environ.get("GAIN_MIN", "3"))
KILL_SWITCH = str(os.environ.get("KILL_SWITCH","0")).strip().lower() in ("1","true","yes","on")

# FUTUROS USDT PERP (ganho real)
LEV_DEFAULT        = float(os.environ.get("LEV_DEFAULT", "10"))         # sua alavancagem padrão
LEV_MAX            = float(os.environ.get("LEV_MAX", "20"))            # limite máximo de alavancagem
# clamp de segurança
try:
  LEV_DEFAULT = max(1.0, min(float(LEV_DEFAULT), float(LEV_MAX)))
except Exception:
  LEV_DEFAULT = 1.0
FEE_TAKER_PER_SIDE = float(os.environ.get("FEE_TAKER_PER_SIDE", "0.0006"))  # 0.06% por ordem (conservador)
FEE_MAKER_PER_SIDE = float(os.environ.get("FEE_MAKER_PER_SIDE", "0.0002"))  # 0.02% por ordem
USE_TAKER          = (str(os.environ.get("USE_TAKER", "1")).strip() != "0")

# Custo estimado (conservador) por 8h de posição (funding varia; aqui usamos ABS)
FUNDING_ABS_8H     = float(os.environ.get("FUNDING_ABS_8H", "0.0001"))      # 0.01% por 8h

# Slippage/Spread estimado por lado (ABS)
SLIPPAGE_PER_SIDE  = float(os.environ.get("SLIPPAGE_PER_SIDE", "0.0002"))   # 0.02% por ordem

# Universo oficial (78 moedas) — ordem alfabética, sem USDT
UNIVERSE = [
  "AAVE","ADA","APE","APT","AR","ARB","ATOM","AVAX","AXS","BAT","BCH","BLUR","BNB","BONK","BTC",
  "COMP","CRV","DASH","DGB","DENT","DOGE","DOT","EGLD","EOS","ETC","ETH","FET","FIL","FLOKI","FLOW",
  "FTM","GALA","GLM","GRT","HBAR","ICP","IMX","INJ","IOST","KAS","KAVA","KSM","LINK","LTC","MANA",
  "MATIC","MKR","NEAR","NEO","OMG","ONT","OP","ORDI","PEPE","QNT","QTUM","RNDR","ROSE","RUNE","SAND",
  "SEI","SHIB","SNX","SOL","STX","SUI","SUSHI","THETA","TIA","TRX","UNI","VET","XEM","XLM","XRP",
  "XVS","ZEC","ZRX"
]

UNIVERSE_77 = UNIVERSE  # compat (mantém o resto do código funcionando)

DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(__file__), "data")
OUT_PATH = os.path.join(DATA_DIR, "pro.json")

# ---------------- HTTP helpers ----------------

def http_json(url: str, timeout=10, headers=None):
  h = {"User-Agent": "AUTOTRADER-PRO/5.0", "Accept": "application/json"}
  if headers: h.update(headers)
  req = Request(url, headers=h)
  with urlopen(req, timeout=timeout) as r:
    return json.loads(r.read().decode("utf-8", errors="replace"))

def as_float(x, default=0.0):
  try:
    if x is None: return default
    if isinstance(x, (int, float)): return float(x)
    s = str(x).replace("%","").strip().replace(",",".")
    return float(s)
  except:
    return default

def norm_key(s):
  return (s or "").strip().upper()

def pick_rows(payload):
  if isinstance(payload, dict):
    for k in ("posicional", "swing", "lista", "dados", "rows"):
      v = payload.get(k)
      if isinstance(v, list) and v:
        return v
    for v in payload.values():
      if isinstance(v, list) and v:
        return v
  return []

def normalize_side(x):
  s = norm_key(x)
  if s in ("NAO ENTRAR","NÃO ENTRAR","NE",""):
    return "NÃO ENTRAR"
  if s in ("LONG","COMPRA","BUY"):
    return "LONG"
  if s in ("SHORT","VENDA","SELL"):
    return "SHORT"
  return s

# ---------------- Exchanges: BINANCE -> BYBIT ----------------

def _clean_symbol(par):
  p = norm_key(par).replace("USDT","").replace("-","").replace("_","")
  return f"{p}USDT"

def _binance(interval, par, limit):
  sym = _clean_symbol(par)
  url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
  arr = http_json(url, timeout=10)
  out=[]
  # Binance: [openTime,open,high,low,close,...] (openTime em ms), ordem antiga->nova
  for x in arr:
    try:
      ts=int(x[0]); o=float(x[1]); h=float(x[2]); l=float(x[3]); c=float(x[4])
      out.append((ts,o,h,l,c))
    except: 
      pass
  return out

def _bybit(interval_min, par, limit):
  sym = _clean_symbol(par)
  # Bybit v5: interval em minutos (ex: 60, 240). list normalmente vem nova->antiga.
  url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval={interval_min}&limit={limit}"
  d = http_json(url, timeout=10)
  arr = (((d.get("result") or {}).get("list")) or [])
  out=[]
  for x in reversed(arr):
    try:
      ts=int(x[0]); o=float(x[1]); h=float(x[2]); l=float(x[3]); c=float(x[4])
      out.append((ts,o,h,l,c))
    except:
      pass
  return out


# --- PATCH2A: fetch real (Futuros) Binance + Bybit com fallback ---
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1/klines"
BYBIT_V5 = "https://api.bybit.com/v5/market/kline"

def _http_json(url, timeout=12, headers=None):
  req = Request(url, headers=headers or {"User-Agent":"AUTOTRADER-PRO/1.0"})
  with urlopen(req, timeout=timeout) as r:
    return json.loads(r.read().decode("utf-8", errors="ignore"))

def _norm_binance_klines(raw):
  out=[]
  if not isinstance(raw, list): return out
  for k in raw:
    try:
      out.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
    except Exception:
      pass
  out.sort(key=lambda x: x[0])
  return out

def _norm_bybit_klines(resp):
  out=[]
  try:
    lst = resp.get("result", {}).get("list", [])
  except Exception:
    lst = []
  if not isinstance(lst, list): return out
  for k in lst:
    try:
      # bybit: [start, open, high, low, close, volume, turnover]
      out.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
    except Exception:
      pass
  out.sort(key=lambda x: x[0])
  return out

def _fetch_binance(par, interval, limit=200, timeout=12):
  sym = f"{par}USDT"
  url = BINANCE_FAPI + "?" + urlencode({"symbol": sym, "interval": interval, "limit": limit})
  raw = _http_json(url, timeout=timeout)
  return _norm_binance_klines(raw)

def _fetch_bybit(par, interval, limit=200, timeout=12):
  # bybit linear USDT perpetual
  sym = f"{par}USDT"
  url = BYBIT_V5 + "?" + urlencode({"category":"linear", "symbol": sym, "interval": interval, "limit": limit})
  raw = _http_json(url, timeout=timeout)
  return _norm_bybit_klines(raw)


# --- PATCH2B: fetch real (spot) OKX + Gate.io com fallback ---
OKX_CANDLES = "https://www.okx.com/api/v5/market/candles"
GATE_SPOT   = "https://api.gateio.ws/api/v4/spot/candlesticks"

def _http_json(url, timeout=12, headers=None):
  req = Request(url, headers=headers or {"User-Agent":"AUTOTRADER-PRO/1.0"})
  with urlopen(req, timeout=timeout) as r:
    return json.loads(r.read().decode("utf-8", errors="ignore"))

def _norm_okx(resp):
  out=[]
  try:
    data = resp.get("data", [])
  except Exception:
    data = []
  if not isinstance(data, list): return out
  for k in data:
    try:
      # OKX: [ts_ms, open, high, low, close, vol, ...]
      out.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
    except Exception:
      pass
  out.sort(key=lambda x: x[0])
  return out

def _norm_gate(raw):
  out=[]
  if not isinstance(raw, list): return out
  for k in raw:
    try:
      # Gate: [ts_s, quote_vol, close, high, low, open, base_vol, finished]
      ts_ms = int(float(k[0])) * 1000
      open_ = float(k[5]); high=float(k[3]); low=float(k[4]); close=float(k[2]); vol=float(k[6])
      out.append([ts_ms, open_, high, low, close, vol])
    except Exception:
      pass
  out.sort(key=lambda x: x[0])
  return out

def _fetch_okx(par, bar, limit=240, timeout=12):
  # OKX SWAP (USDT Perp)
  inst = f"{par}-USDT-SWAP"
  url = OKX_CANDLES + "?" + urlencode({"instId": inst, "bar": bar, "limit": str(limit)})
  raw = _http_json(url, timeout=timeout)
  # OKX usa code="0"
  if str(raw.get("code")) != "0": return []
  return _norm_okx(raw)

def _fetch_gate(par, interval, limit=240, timeout=12):
  pair = f"{par}_USDT"
  url = GATE_SPOT + "?" + urlencode({"currency_pair": pair, "interval": interval, "limit": str(limit)})
  raw = _http_json(url, timeout=timeout)
  return _norm_gate(raw)


def _agg_4h_from_1h(c1):
  # agrega candles 1H -> 4H (alinhado em janelas de 4 horas)
  out=[]
  if not isinstance(c1, list) or not c1:
    return out
  try:
    c1 = sorted(c1, key=lambda x: x[0])
  except Exception:
    pass

  period = 4*60*60*1000  # 4h em ms
  cur_k = None
  o=h=l=c=v = None

  for row in c1:
    try:
      ts = int(row[0])
      op = float(row[1]); hi=float(row[2]); lo=float(row[3]); cl=float(row[4]); vol=float(row[5] or 0.0)
    except Exception:
      continue

    k = (ts // period) * period

    if cur_k is None:
      cur_k = k
      o, h, l, c, v = op, hi, lo, cl, vol
      continue

    if k != cur_k:
      out.append([cur_k, o, h, l, c, v])
      cur_k = k
      o, h, l, c, v = op, hi, lo, cl, vol
    else:
      if hi > h: h = hi
      if lo < l: l = lo
      c = cl
      v += vol

  if cur_k is not None:
    out.append([cur_k, o, h, l, c, v])

  out.sort(key=lambda x: x[0])
  return out


def fetch_1h_4h(par):
  # FUTUROS USDT PERP (prioridade): Binance FAPI -> Bybit Linear -> OKX SWAP -> (último caso) Gate Spot
  # 4H é agregado local a partir do 1H (menos requests, mais estabilidade)
  c1=[]; c4=[]
  src={"1h":"", "4h":""}

  LIMIT_1H = 320  # suficiente para EMA/RSI e para formar 4H

  # 1) Binance Futures
  try:
    c1 = _fetch_binance(par, "1h", limit=LIMIT_1H)
    if c1: src["1h"]="BINANCE_FAPI"
  except Exception:
    c1=[]

  # 2) Bybit (Linear USDT Perp)
  if not c1:
    try:
      c1 = _fetch_bybit(par, "60", limit=LIMIT_1H)
      if c1: src["1h"]="BYBIT_LINEAR"
    except Exception:
      c1=[]

  # 3) OKX SWAP
  if not c1:
    try:
      c1 = _fetch_okx(par, "1H", limit=LIMIT_1H)
      if c1: src["1h"]="OKX_SWAP"
    except Exception:
      c1=[]

  # 4) Último caso: Gate Spot
  if not c1:
    try:
      c1 = _fetch_gate(par, "1h", limit=LIMIT_1H)
      if c1: src["1h"]="GATE_SPOT"
    except Exception:
      c1=[]

  if c1:
    try:
      c4 = _agg_4h_from_1h(c1)
      if c4: src["4h"]=(src["1h"] or "AGG") + "+AGG4H"
    except Exception:
      c4=[]

  return c1, c4, src

# --- /PATCH2B ---

# --- /PATCH2A ---

def ema(series, period):
  if not series: return None
  k = 2.0/(period+1.0)
  e = series[0]
  for v in series[1:]:
    e = (v*k) + (e*(1-k))
  return e

def rsi(closes, period=14):
  if len(closes) < period + 2:
    return None
  gains=[]; losses=[]
  for i in range(1, period+1):
    ch = closes[i]-closes[i-1]
    gains.append(max(ch,0)); losses.append(max(-ch,0))
  avg_gain=sum(gains)/period
  avg_loss=sum(losses)/period
  for i in range(period+1, len(closes)):
    ch = closes[i]-closes[i-1]
    g=max(ch,0); l=max(-ch,0)
    avg_gain=(avg_gain*(period-1)+g)/period
    avg_loss=(avg_loss*(period-1)+l)/period
  if avg_loss==0: return 100.0
  rs=avg_gain/avg_loss
  return 100.0 - (100.0/(1.0+rs))

def atr(ohlc, period=14):
  if len(ohlc) < period + 2:
    return None
  trs=[]
  prev_close=ohlc[0][4]
  for i in range(1, len(ohlc)):
    h=ohlc[i][2]; l=ohlc[i][3]; c=ohlc[i][4]
    tr=max(h-l, abs(h-prev_close), abs(l-prev_close))
    trs.append(tr)
    prev_close=c
  a=sum(trs[:period])/period
  for tr in trs[period:]:
    a=(a*(period-1)+tr)/period
  return a

def clamp(a, x, b):
  return max(a, min(x, b))

def parse_eta_hours(eta):
  s = str(eta).lower()
  m=re.search(r"(\d+)\s*h", s)
  if m:
    return int(m.group(1))
  m=re.search(r"(\d+)\s*d", s)
  if m:
    return int(m.group(1)) * 24
  # sem ETA: assume 8h (conservador)
  return 8

# ---------------- ALVO + ETA (mesmo motor) ----------------


def calc_target_and_eta(side, price, atr_4h, atr_1h, gain_min, e20_1=None, e50_1=None, e20_4=None, e50_4=None):
  # PATCH2C: ALVO/ETA dinâmicos por regime (trend vs range)
  try:
    price = float(price or 0.0)
    atr_4h = float(atr_4h or 0.0)
    atr_1h = float(atr_1h or 0.0)
  except Exception:
    return 0.0, ""

  if price <= 0 or atr_4h <= 0:
    return 0.0, ""

  def _clamp(a, x, b):
    return a if x < a else (b if x > b else x)

  # trend_score (0..1) usando EMA20/EMA50 e alinhamento 1H/4H
  trend_score = 0.0
  try:
    e20_4 = float(e20_4) if e20_4 is not None else None
    e50_4 = float(e50_4) if e50_4 is not None else None
    e20_1 = float(e20_1) if e20_1 is not None else None
    e50_1 = float(e50_1) if e50_1 is not None else None

    if e20_4 and e50_4:
      strength = abs(e20_4 - e50_4) / price
      strength = _clamp(0.0, strength * 160.0, 1.0)  # normaliza
      ok4 = ((side=="LONG" and e20_4>e50_4) or (side=="SHORT" and e20_4<e50_4))
      ok1 = False
      if e20_1 and e50_1:
        ok1 = ((side=="LONG" and e20_1>e50_1) or (side=="SHORT" and e20_1<e50_1))
      align = 1.0 if (ok1 and ok4) else (0.6 if ok4 else (0.3 if ok1 else 0.0))
      trend_score = _clamp(0.0, 0.65*strength + 0.35*align, 1.0)
  except Exception:
    trend_score = 0.0

  # multiplicador dinâmico: range -> menor; trend -> maior
  mult = 0.90 + 0.70*trend_score  # 0.90 .. 1.60

  # suaviza em volatilidade extrema (evita alvo irreal)
  try:
    if atr_1h > 0:
      vr = atr_1h / price
      if vr > 0.03:
        mult *= 0.85
  except Exception:
    pass

  dist = atr_4h * mult

  # piso mínimo para não virar “alvo microscópico”
  dist_min = price * 0.005  # 0.5%
  if dist < dist_min:
    dist = dist_min

  if side == "LONG":
    alvo = price + dist
  else:
    alvo = price - dist

  # ETA: dist / ATR1H (limites)
  eta = ""
  if atr_1h and atr_1h > 0:
    eta_h = dist / atr_1h
    # se trend_score alto, tende a “andar” melhor
    eta_h *= (1.10 - 0.25*trend_score)
    eta_h = _clamp(1.0, eta_h, 96.0)
    if eta_h < 24:
      eta = f"~{int(round(eta_h))}h"
    else:
      eta = f"~{int(round(eta_h/24.0))}d"

  return float(alvo), eta

def zona_risco_prioridade(assert_pct, ganho_pct, eta_h):
  if assert_pct >= 82 and ganho_pct >= 8 and eta_h <= 36:
    return "VERDE","BAIXO","ALTA"
  if assert_pct >= 74 and ganho_pct >= 5 and eta_h <= 72:
    return "AMARELA","MÉDIO","MÉDIA"
  return "AMARELA","MÉDIO","MÉDIA" if assert_pct >= 70 else ("VERMELHA","ALTO","BAIXA")

# ---------------- Main ----------------

def main():
  # garante pasta de saída
  try:
    os.makedirs(DATA_DIR, exist_ok=True)
  except Exception:
    pass
  now = datetime.now(TZ)
  updated_brt = now.strftime("%Y-%m-%d %H:%M")
  data = now.strftime("%Y-%m-%d")
  hora = now.strftime("%H:%M")

  # 1) Universo (moedas) vindo dos painéis internos
  base=[]
  for src,url in URLS:
    try:
      payload=http_json(url, timeout=6)
      rows=pick_rows(payload)
      for r in rows:
        par=norm_key(r.get("par") or r.get("symbol") or r.get("moeda"))
        if not par: continue
        base.append({
          "src": src,
          "par": par,
          "side_src": normalize_side(r.get("side") or r.get("sinal") or ""),
          "assert_src": as_float(r.get("assert_pct") or r.get("assert") or r.get("assertividade"), 0.0),
        })
    except:
      pass

  if not base:
    out={"updated_brt":updated_brt,"meta":{"version":"PRO_V5","notes":"sem fontes internas"},"lista":[]}
    with open(OUT_PATH,"w",encoding="utf-8") as f:
      # FIX_NORMALIZA_PRIORIDADE_ARRAY_20260115
      try:
        for _it in out.get("lista", []):
          for _k in ("zona","risco","prioridade"):
            _v=_it.get(_k)
            if isinstance(_v,(list,tuple)):
              _it[_k]=(_v[-1] if _v else "")
      except Exception:
        pass
      # FIX_PRIORIDADE_LIST_NO_OUTPATH_20260115
      def _norm(v):
        return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      try:
        for _it in out.get('lista', []):
          if isinstance(_it, dict):
            _it['prioridade'] = _norm(_it.get('prioridade'))
            _it['risco']      = _norm(_it.get('risco'))
            _it['zona']       = _norm(_it.get('zona'))
      except Exception:
        pass
      # FIX: normalizar zona/risco/prioridade (evitar list no JSON)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se alguém colocou [ZONA,RISCO,PRIORIDADE] em um único campo
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # FIX: normalizar zona/risco/prioridade (evitar list no JSON)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se alguém colocou [ZONA,RISCO,PRIORIDADE] em um único campo
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # FIX: normalizar zona/risco/prioridade (evitar list no JSON)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se alguém colocou [ZONA,RISCO,PRIORIDADE] em um único campo
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # FIX: normalizar zona/risco/prioridade (evitar list no JSON)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se alguém colocou [ZONA,RISCO,PRIORIDADE] em um único campo
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # FIX: normalizar zona/risco/prioridade (evitar list no JSON)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se alguém colocou [ZONA,RISCO,PRIORIDADE] em um único campo
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # FIX: normalizar zona/risco/prioridade (evitar list no JSON)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se alguém colocou [ZONA,RISCO,PRIORIDADE] em um único campo
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # FIX FINAL: garantir zona/risco/prioridade como STRING (nunca list)
      def _last(v):
          return (v[-1] if isinstance(v,(list,tuple)) and v else v)
      def _split3(v):
          if isinstance(v,(list,tuple)) and len(v)==3 and all(isinstance(x,str) for x in v):
              return v[0], v[1], v[2]
          return None
      try:
          for it in out.get('lista', []):
              if not isinstance(it, dict):
                  continue
              # se algum campo veio como [ZONA,RISCO,PRIORIDADE]
              for k in ('prioridade','risco','zona'):
                  t=_split3(it.get(k))
                  if t:
                      it['zona'], it['risco'], it['prioridade'] = t
                      break
              it['zona'] = _last(it.get('zona'))
              it['risco'] = _last(it.get('risco'))
              it['prioridade'] = _last(it.get('prioridade'))
      except Exception:
          pass
      # AUTOTRADER_PRO_CONTRACT_V1
      out = finalize_out(out)
      ok, errs = validate_out(out)
      if not ok:
          print('ERRO: contrato invalido:', errs[:10])
          raise SystemExit(2)
      # garante schema padrao do PRO (dict com lista)
      payload = out
      if isinstance(out, list):
          payload = {'updated_brt': locals().get('updated_brt'), 'meta': locals().get('meta', {}), 'lista': rank_out(out)}
      elif isinstance(out, dict) and 'lista' in out:
          payload = out
      else:
          payload = {'updated_brt': locals().get('updated_brt'), 'meta': locals().get('meta', {}), 'lista': []}
      # GARANTIA: sempre 77 itens (preenche faltantes com NAO ENTRAR)
      if 'out' in locals() and isinstance(out, list):
        mp = {str(i.get('par','')).strip().upper(): i for i in out if isinstance(i, dict)}
        fixed = []
        for sym in UNIVERSE_77:
          it = mp.get(sym)
          if not isinstance(it, dict):
            it = {'par': sym, 'side': 'NÃO ENTRAR', 'ganho_pct': '0.00', 'assert_pct': 0.0, 'assert_cor': 'VERMELHA'}
          it.setdefault('par', sym)
          it.setdefault('side', 'NÃO ENTRAR')
          it.setdefault('ganho_pct', '0.00')
          it.setdefault('assert_pct', 0.0)
          it.setdefault('assert_cor', 'VERMELHA')
          fixed.append(it)
        out = fixed

      # --- PATCH1: GARANTIA 77 + compat "lista"/"sinais" ---
      try:
        u77 = list(globals().get("UNIVERSE_77") or [])
        if isinstance(payload, dict) and u77:
          lst = payload.get("lista")
          if not isinstance(lst, list): lst = []
          by = {}
          for it in lst:
            if isinstance(it, dict) and it.get("par"):
              by[str(it.get("par")).strip().upper()] = it
          fixed = []
          _ub = payload.get("updated_brt") or locals().get("updated_brt")
          _data, _hora = "", ""
          if isinstance(_ub, str) and " " in _ub:
            _data, _hora = _ub.split(" ", 1)
            _hora = _hora[:5]
          for par in u77:
            it = by.get(par)
            if not it:
              it = {
                "par": par,
                "side": "NÃO ENTRAR",
                "preco": 0.0,
                "alvo": 0.0,
                "ganho_pct": 0.0,
                "assert_pct": 0.0,
                "eta": "",
                "zona": "",
                "risco": "",
                "prioridade": "",
                "data": _data,
                "hora": _hora,
              }
            fixed.append(it)
          payload["lista"] = fixed
          payload["sinais"] = fixed
      except Exception:
        pass
      # PATCHZ_PRECO0: evita preco=0 usando último pro.json (cache simples)
      try:
        last={}
        if 'OUT_PATH' in globals() and OUT_PATH and os.path.exists(OUT_PATH):
          old=json.load(open(OUT_PATH,"r",encoding="utf-8"))
          for it in old.get("lista",[]):
            if isinstance(it,dict) and it.get("par") and float(it.get("preco") or 0)>0:
              last[it["par"]]=float(it["preco"])
        for it in (results or []):
          if isinstance(it,dict) and it.get("par") and float(it.get("preco") or 0)==0 and it["par"] in last:
            it["preco"]=last[it["par"]]
            it["eta"]=(it.get("eta") or "") + " (cache)"
      except Exception:
        pass

      # PATCHP_PRICE_FEED: aplica fallback de preco=0 usando px_map

      try:

        for it in (results or []):

          if isinstance(it,dict) and it.get("par") and float(it.get("preco") or 0)==0:

            px=float(px_map.get(it["par"]) or 0.0)

            if px>0:

              it["preco"]=px

              it["eta"]=(it.get("eta") or "") + " (pxfeed)"

            else:

              it["side"]="NÃO ENTRAR"

      except Exception:

        pass


      # PATCHP_APPLY_OUTPATH: aplica preco em lote (px_map) antes de salvar pro.json


      try:


        _lst = None


        if 'out' in locals() and isinstance(locals().get('out'), dict) and isinstance(out.get('lista'), list):


          _lst = out['lista']


        elif 'results' in locals() and isinstance(locals().get('results'), list):


          _lst = results


      


        if _lst is not None:


          # garante px_map


          if 'px_map' not in locals() or not isinstance(px_map, dict) or not px_map:


            try:


              px_map = {}


              _a = _px_okx_swap()


              if isinstance(_a, dict): px_map.update(_a)


              _b = _px_gate_spot()


              _c = _px_binance_spot()
              if isinstance(_c, dict):
                for k,v in _c.items():
                  if k not in px_map and float(v or 0)>0:
                    px_map[k]=float(v)

              if isinstance(_b, dict):


                for k,v in _b.items():


                  if k not in px_map and float(v or 0)>0:


                    px_map[k]=float(v)


            except Exception:


              px_map = {}


      


          for it in _lst:


            if isinstance(it, dict) and it.get('par') and float(it.get('preco') or 0)==0:


              px = float(px_map.get(it['par']) or 0.0)


              if px>0:


                it['preco']=px


                it['eta']=(it.get('eta') or '') + ' (pxfeed)'


              else:


                it['side']='NÃO ENTRAR'


      except Exception:


        pass



      # PATCH_FINAL_PRECO: preenche preco<=0 com feed em lote (OKX swap -> Gate spot -> OKX spot)



      try:



        import json, subprocess



        def _curl_json(url):



          r = subprocess.run(["curl","-sS","--max-time","12","-H","User-Agent: Mozilla/5.0",url], capture_output=True, text=True)



          if r.returncode!=0 or not (r.stdout or "").strip(): return None



          try: return json.loads(r.stdout)



          except Exception: return None



        px={}



        d=_curl_json("https://www.okx.com/api/v5/market/tickers?instType=SWAP")



        if isinstance(d,dict):



          for it in (d.get("data") or []):



            inst=(it.get("instId") or "")



            if inst.endswith("-USDT-SWAP"):



              sym=inst.split("-")[0]



              try:



                v=float(it.get("last") or 0.0)



                if v>0: px.setdefault(sym, v)



              except Exception:



                pass



        d=_curl_json("https://api.gateio.ws/api/v4/spot/tickers")



        if isinstance(d,list):



          for it in d:



            cp=(it.get("currency_pair") or "")



            if cp.endswith("_USDT"):



              sym=cp.split("_")[0]



              if sym in px: 



                continue



              try:



                v=float(it.get("last") or 0.0)



                if v>0: px[sym]=v



              except Exception:



                pass



        d=_curl_json("https://www.okx.com/api/v5/market/tickers?instType=SPOT")



        if isinstance(d,dict):



          for it in (d.get("data") or []):



            inst=(it.get("instId") or "")



            if inst.endswith("-USDT"):



              sym=inst.split("-")[0]



              if sym in px:



                continue



              try:



                v=float(it.get("last") or 0.0)



                if v>0: px[sym]=v



              except Exception:



                pass

        if isinstance(payload,dict) and isinstance(payload.get("lista"),list) and px:
          alias={"FTM":"S","MATIC":"POL","MKR":"SKY"}
          for it in payload["lista"]:
            try:
              sym=it.get("par")
              if not sym:
                continue
              if float(it.get("preco") or 0.0)>0:
                continue
              if sym in px:
                it["preco"]=px[sym]
              else:
                a=alias.get(sym)
                if a and a in px:
                  it["preco"]=px[a]
                  it["eta"]=(it.get("eta") or "") + f" (OKX:{a})"
            except Exception:
              pass

          # remove moedas sem feed (evita preco=0 no painel)
# DISABLED_KEEP_78:           payload["lista"]=[it for it in payload["lista"] if not (it.get("par")=="EOS" and float(it.get("preco") or 0.0)<=0)]



      except Exception:



        pass



      # PATCH_BINANCE_FILL: se preco==0, tenta Binance Spot (só preço)



      try:



        import json, subprocess



        url="https://api.binance.com/api/v3/ticker/price"



        r=subprocess.run(["curl","-sS","--max-time","12","-H","User-Agent: Mozilla/5.0",url], capture_output=True, text=True)



        data=json.loads(r.stdout) if (r.returncode==0 and (r.stdout or "").strip().startswith("[")) else []



        px={}



        if isinstance(data,list):



          for it in data:



            sym=(it.get("symbol") or "")



            if sym.endswith("USDT"):



              k=sym[:-4]



              try:



                v=float(it.get("price") or 0.0)



                if v>0: px[k]=v



              except Exception:



                pass



        if isinstance(payload,dict) and isinstance(payload.get("lista"),list) and px:



          for it in payload["lista"]:



            try:



              if isinstance(it,dict) and it.get("par") and float(it.get("preco") or 0)==0:



                v=px.get(it["par"])



                if v:



                  it["preco"]=v



                  it["eta"]=(it.get("eta") or "") + " (BN)"



            except Exception:



              pass



      except Exception:



        pass





      # PATCH_ALIAS_TICKER_OKX: resolve tickers renomeados (FTM->S, MATIC->POL, MKR->SKY) + remove EOS sem feed
      try:
        import json, subprocess
        alias={"FTM":"S","MATIC":"POL","MKR":"SKY"}
        def _okx_last(sym):
          inst=f"{sym}-USDT"
          url=f"https://www.okx.com/api/v5/market/ticker?instId={inst}"
          r=subprocess.run(["curl","-sS","--max-time","12",url], capture_output=True, text=True)
          t=(r.stdout or "").strip()
          if r.returncode!=0 or not t.startswith("{"):
            return 0.0
          try:
            d=json.loads(t)
            data=d.get("data") or []
            if data and isinstance(data,list):
              return float(data[0].get("last") or 0.0)
          except Exception:
            return 0.0
          return 0.0

        if isinstance(payload,dict) and isinstance(payload.get("lista"),list):
          for it in payload["lista"]:
            try:
              if not isinstance(it,dict): 
                continue
              par=it.get("par")
              if not par:
                continue
              if float(it.get("preco") or 0.0)>0:
                continue
              a=alias.get(par)
              if a:
                v=_okx_last(a)
                if v>0:
                  it["preco"]=v
                  it["eta"]=(it.get("eta") or "") + f" (OKX:{a})"
            except Exception:
              pass

# DISABLED_KEEP_78:           payload["lista"]=[it for it in payload["lista"] if not (isinstance(it,dict) and it.get("par")=="EOS" and float(it.get("preco") or 0.0)<=0)]
      except Exception:
        pass

      ### KILL_SWITCH_ENFORCE ###
      try:
        if 'KILL_SWITCH' in globals() and KILL_SWITCH:
          _lst = payload.get('lista') or payload.get('sinais') or []
          if isinstance(_lst, list):
            for _it in _lst:
              if isinstance(_it, dict):
                _it['side'] = 'NÃO ENTRAR'
                _it['motivo'] = 'KILL_SWITCH'
                _it['ganho_pct'] = 0.0
      except Exception:
        pass

      ### MOTIVO_ENFORCE ###
      try:
        _lst = payload.get('lista') or payload.get('sinais') or []
        if isinstance(_lst, list):
          for _it in _lst:
            if not isinstance(_it, dict):
              continue
            _side = _it.get('side') or _it.get('sinal') or ''
            if _side == 'NÃO ENTRAR':
              _m = _it.get('motivo')
              if _m is None or _m == '':
                try:
                  _g = float(_it.get('ganho_pct') or _it.get('ganho') or 0.0)
                except Exception:
                  _g = 0.0
                _it['motivo'] = (('GANHO<' + str(GAIN_MIN) + '%') if _g < GAIN_MIN else 'SEM DADOS')
            else:
              if 'motivo' not in _it or _it.get('motivo') is None:
                _it['motivo'] = ''
      except Exception:
        pass

      ### PATCH_SEM_DADOS ###
      try:
        _lst = payload.get('lista') or payload.get('sinais') or []
        if isinstance(_lst, list):
          def _f(x):
            try:
              return float(x)
            except Exception:
              return 0.0
          for _it in _lst:
            if not isinstance(_it, dict):
              continue
            _side = _it.get('side') or _it.get('sinal')
            if _side != 'NÃO ENTRAR':
              continue
            _preco = _f(_it.get('preco'))
            _alvo  = _f(_it.get('alvo'))
            _atr4  = _f(_it.get('atr_4h') or _it.get('atr4h') or _it.get('atr'))
            # prioridade: SEM DADOS
            if _preco <= 0 or _alvo <= 0 or (_atr4 != 0.0 and _atr4 <= 0):
              _it['motivo'] = 'SEM DADOS'
      except Exception:
        pass

      json.dump(payload, f,ensure_ascii=False,indent=2)
    print(f"OK pro.json atualizado: {OUT_PATH} | itens=0 | updated_brt={updated_brt}")
    return

  # dedupe universo por PAR
  universe={}
  for r in base:
    p=r["par"]
    if p not in universe:
      universe[p]=r
    else:
      a=universe[p]
      if a["side_src"]=="NÃO ENTRAR" and r.get("side_src") in ("LONG","SHORT"):
        universe[p]=r
      elif r["assert_src"] > a["assert_src"]:
        universe[p]=r

  pars=sorted(universe.keys())

  # 2) calcula sinais por moeda (candles 1H+4H)
  results=[]


  # PATCHP_PRICE_FEED: batch last prices (OKX SWAP + Gate spot) para evitar preco=0
  def _px_okx_swap():
    try:
      import json, subprocess
      url="https://www.okx.com/api/v5/market/tickers?instType=SWAP"
      r=subprocess.run(["curl","-sS","--max-time","12",url], capture_output=True, text=True)
      if r.returncode!=0 or not r.stdout.strip():
        return {}
      d=json.loads(r.stdout)
      out={}
      for it in (d.get("data") or []):
        inst=it.get("instId") or ""
        if inst.endswith("-USDT-SWAP"):
          sym=inst.split("-")[0]
          try:
            out[sym]=float(it.get("last") or 0.0)
          except Exception:
            pass
      return out
    except Exception:
      return {}


  def _px_binance_spot():
    try:
      import json, subprocess
      url="https://api.binance.com/api/v3/ticker/price"
      r=subprocess.run(["curl","-sS","--max-time","12",url], capture_output=True, text=True)
      if r.returncode!=0 or not (r.stdout or "").strip():
        return {}
      d=json.loads(r.stdout)
      out={}
      if isinstance(d, list):
        for it in d:
          sym=str(it.get("symbol") or "")
          if not sym.endswith("USDT"):
            continue
          base=sym[:-4]
          try:
            v=float(it.get("price") or 0.0)
            if v>0:
              out[base]=v
          except Exception:
            pass
      return out
    except Exception:
      return {}

  def _px_gate_spot():
    try:
      import json, subprocess
      url="https://api.gateio.ws/api/v4/spot/tickers"
      r=subprocess.run(["curl","-sS","--max-time","12",url], capture_output=True, text=True)
      if r.returncode!=0 or not r.stdout.strip():
        return {}
      arr=json.loads(r.stdout)
      out={}
      if isinstance(arr,list):
        for it in arr:
          cp=it.get("currency_pair") or ""
          if cp.endswith("_USDT"):
            sym=cp.split("_")[0]
            try:
              out[sym]=float(it.get("last") or 0.0)
            except Exception:
              pass
      return out
    except Exception:
      return {}

  px_map={}
  _a=_px_okx_swap()
  if isinstance(_a,dict): px_map.update(_a)
  _b=_px_gate_spot()
  if isinstance(_b,dict):
    for k,v in _b.items():
      if k not in px_map and v and v>0:
        px_map[k]=v
  def job(par):
    c1, c4, ex = fetch_1h_4h(par)
    if not c1 or not c4: return None

    closes1=[x[4] for x in c1]
    closes4=[x[4] for x in c4]
    price = closes1[-1]

    atr_1h = atr(c1,14)
    atr_4h = atr(c4,14)

    side = universe.get(par, {}).get("side_src")
    if side not in ("LONG","SHORT"):
      side = "NÃO ENTRAR"

    # inferência de direção só se vier "NÃO ENTRAR"
    e20_1 = ema(closes1[-120:],20) if len(closes1)>=40 else None
    e50_1 = ema(closes1[-200:],50) if len(closes1)>=80 else None
    e20_4 = ema(closes4[-120:],20) if len(closes4)>=40 else None
    e50_4 = ema(closes4[-180:],50) if len(closes4)>=60 else None

    if side == "NÃO ENTRAR" and e20_4 and e50_4:
      side = "LONG" if e20_4 > e50_4 else "SHORT"
    if side not in ("LONG","SHORT"):
      return None

    alvo, eta = calc_target_and_eta(side, price, atr_4h, atr_1h, GAIN_MIN, e20_1, e50_1, e20_4, e50_4)
    if alvo <= 0: return None

    # ----- GANHO REAL (FUTURO USDT PERP) -----
    # 1) movimento bruto (% no preço)
    ganho_bruto_pct = ((alvo-price)/price)*100.0 if side=="LONG" else ((price-alvo)/price)*100.0
    ganho_bruto_pct = float(max(0.0, ganho_bruto_pct))

    # 2) custos estimados no NOTIONAL (taxas + slippage + funding)
    fee_side = (FEE_TAKER_PER_SIDE if USE_TAKER else FEE_MAKER_PER_SIDE)
    eta_h = parse_eta_hours(eta)
    # funding: custo absoluto por 8h (conservador). Se ETA vier vazio/0, assume 8h.
    funding_mult = max(1.0, float(eta_h or 0.0)/8.0)
    custo_notional_pct = (2.0*(fee_side + SLIPPAGE_PER_SIDE) + (FUNDING_ABS_8H * funding_mult)) * 100.0

    # 3) ganho líquido no notional
    ganho_liq_notional_pct = float(ganho_bruto_pct - custo_notional_pct)

    # 4) ROE% (impacto na margem, considerando alavancagem)
    ganho_pct = float(ganho_liq_notional_pct * LEV_DEFAULT)

    

    side_out = side
    if ganho_pct < GAIN_MIN:
      side_out = "NÃO ENTRAR"
# ASSERT reforçada (multi-timeframe)
    base_assert = universe.get(par, {}).get("assert_src") or 62.0
    adj=0.0

    # tendência 1H e 4H
    ok1 = (e20_1 and e50_1 and ((side=="LONG" and e20_1>e50_1) or (side=="SHORT" and e20_1<e50_1)))
    ok4 = (e20_4 and e50_4 and ((side=="LONG" and e20_4>e50_4) or (side=="SHORT" and e20_4<e50_4)))

    if ok1 and ok4: adj += 7.0
    elif ok1 or ok4: adj += 2.0
    else: adj -= 8.0

    # força da tendência
    if e20_4 and e50_4:
      adj += clamp(-2.0, (abs(e20_4-e50_4)/price)*220.0, 6.0)

    # RSI 1H
    rsi14 = rsi(closes1[-250:],14) if len(closes1)>=20 else None
    if rsi14 is not None:
      if side=="LONG" and rsi14>75: adj -= 3.0
      if side=="SHORT" and rsi14<25: adj -= 3.0
      if side=="LONG" and 45<=rsi14<=65: adj += 1.5
      if side=="SHORT" and 35<=rsi14<=55: adj += 1.5

    # volatilidade (evita extremos)
    if atr_1h and price:
      vr = atr_1h/price
      if vr < 0.002: adj -= 2.0   # “travado”
      if vr > 0.02:  adj -= 2.0   # “nervoso demais”

    # (eta_h já calculado acima)
    if eta_h > 90: adj -= 4.0     # muito demorado
    if eta_h < 6:  adj -= 1.0     # rápido demais (spike)

    assert_pct = clamp(50.0, base_assert + adj, 92.0)

    zona, risco, prioridade = zona_risco_prioridade(assert_pct, ganho_pct, eta_h)

    return {
      "src": ex or universe[par]["src"],
      "par": par,
      "side": side_out,
      "preco": float(price),
      "alvo": float(alvo),
      "ganho_pct": float(ganho_pct),
      "ganho_bruto_pct": float(ganho_bruto_pct),
      "ganho_liq_notional_pct": float(ganho_liq_notional_pct),
      "custo_notional_pct": float(custo_notional_pct),
      "alav": float(LEV_DEFAULT),
      "assert_pct": float(assert_pct),
      "eta": eta,
      "zona": zona,
      "risco": risco,
      "prioridade": prioridade,
      "data": data,
      "hora": hora
    }

  with ThreadPoolExecutor(max_workers=10) as pool:
    # FORCA 77 SEMPRE (independente do MFE)
    pars = sorted(list(UNIVERSE_77))
    futs={pool.submit(job,p):p for p in pars}
    for fut in as_completed(futs):
      r=fut.result()
      if not r: continue
      # ASSERT NÃO FILTRA (só cor no site). Mantemos a regra de operação no GANHO (GAIN_MIN).
      if r["ganho_pct"] < GAIN_MIN: continue
      results.append(r)

  # ranking final
  prio_rank={"ALTA":0,"MÉDIA":1,"MEDIA":1,"BAIXA":2}
  results.sort(key=lambda x: (
    prio_rank.get(x["prioridade"], 9),
    -x["assert_pct"],
    -x["ganho_pct"],
    parse_eta_hours(x.get("eta",""))
  ))

  out={
    "updated_brt": updated_brt,
    "meta": {"version":"PRO_V5","notes":"mais assertivo (1H+4H). ALVO+ETA coerentes (ATR4H/ATR1H)."},
    "lista": rank_out(results)
  }
  with open(OUT_PATH,"w",encoding="utf-8") as f:
    # AUTOTRADER_PRO_CONTRACT_V1
    out = finalize_out(out)
    ok, errs = validate_out(out)
    if not ok:
        print('ERRO: contrato invalido:', errs[:10])
        raise SystemExit(2)
    # garante schema padrao do PRO (dict com lista)
    payload = out
    if isinstance(out, list):
        payload = {'updated_brt': locals().get('updated_brt'), 'meta': locals().get('meta', {}), 'lista': out}
    elif isinstance(out, dict) and 'lista' in out:
        payload = out
    else:
        payload = {'updated_brt': locals().get('updated_brt'), 'meta': locals().get('meta', {}), 'lista': []}

    # --- PATCH1: GARANTIA 77 + compat "lista"/"sinais" ---
    try:
      u77 = list(globals().get("UNIVERSE_77") or [])
      if isinstance(payload, dict) and u77:
        lst = payload.get("lista")
        if not isinstance(lst, list): lst = []
        by = {}
        for it in lst:
          if isinstance(it, dict) and it.get("par"):
            by[str(it.get("par")).strip().upper()] = it
        fixed = []
        _ub = payload.get("updated_brt") or locals().get("updated_brt")
        _data, _hora = "", ""
        if isinstance(_ub, str) and " " in _ub:
          _data, _hora = _ub.split(" ", 1)
          _hora = _hora[:5]
        for par in u77:
          it = by.get(par)
          if not it:
            it = {
              "par": par,
              "side": "NÃO ENTRAR",
              "preco": 0.0,
              "alvo": 0.0,
              "ganho_pct": 0.0,
              "assert_pct": 0.0,
              "eta": "",
              "zona": "",
              "risco": "",
              "prioridade": "",
              "data": _data,
              "hora": _hora,
            }
          fixed.append(it)
        payload["lista"] = fixed
        payload["sinais"] = fixed
    except Exception:
      pass
      # linear (fallback adicional)
      d=_bybit_load("https://api.bybit.com/v5/market/tickers?category=linear")
      lst=(((d.get("result") or {}).get("list")) if isinstance(d,dict) else None)
      if isinstance(lst,list):
        for it in lst:
          sym=(it.get("symbol") or "")
          if sym.endswith("USDT"):
            k=sym[:-4]
            if k in px:
              continue
            try:
              v=float(it.get("lastPrice") or 0.0)
              if v>0: px[k]=v
            except Exception:
              pass

      if isinstance(payload,dict) and isinstance(payload.get("lista"),list) and px:
        for it in payload["lista"]:
          try:
            if isinstance(it,dict) and it.get("par") and float(it.get("preco") or 0)==0:
              v=px.get(it["par"])
              if v:
                it["preco"]=v
                it["eta"]=(it.get("eta") or "") + " (BY)"
          except Exception:
            pass
    except Exception:
      pass
    # PATCH_FINAL_PRECO: preenche preco<=0 com feed em lote (OKX swap -> Gate spot -> OKX spot)
    try:
      import json, subprocess
      def _curl_json(url):
        r = subprocess.run(["curl","-sS","--max-time","12","-H","User-Agent: Mozilla/5.0",url], capture_output=True, text=True)
        if r.returncode!=0 or not (r.stdout or "").strip(): return None
        try: return json.loads(r.stdout)
        except Exception: return None
      px={}
      d=_curl_json("https://www.okx.com/api/v5/market/tickers?instType=SWAP")
      if isinstance(d,dict):
        for it in (d.get("data") or []):
          inst=(it.get("instId") or "")
          if inst.endswith("-USDT-SWAP"):
            sym=inst.split("-")[0]
            try:
              v=float(it.get("last") or 0.0)
              if v>0: px.setdefault(sym, v)
            except Exception:
              pass
      d=_curl_json("https://api.gateio.ws/api/v4/spot/tickers")
      if isinstance(d,list):
        for it in d:
          cp=(it.get("currency_pair") or "")
          if cp.endswith("_USDT"):
            sym=cp.split("_")[0]
            try:
              v=float(it.get("last") or 0.0)
              if v>0: px[sym]=v
            except Exception:
              pass
      d=_curl_json("https://www.okx.com/api/v5/market/tickers?instType=SPOT")
      if isinstance(d,dict):
        for it in (d.get("data") or []):
          inst=(it.get("instId") or "")
          if inst.endswith("-USDT"):
            sym=inst.split("-")[0]
            if sym in px:
              continue
            try:
              v=float(it.get("last") or 0.0)
              if v>0: px[sym]=v
            except Exception:
              pass
      if isinstance(payload,dict) and isinstance(payload.get("lista"),list) and px:
        for it in payload["lista"]:
          try:
            sym=it.get("par")
            if sym and float(it.get("preco") or 0.0)<=0 and sym in px:
              it["preco"]=px[sym]
          except Exception:
            pass
    except Exception:
      pass
    # PATCH_BINANCE_FILL: se preco==0, tenta Binance Spot (só preço)
    try:
      import json, subprocess
      url="https://api.binance.com/api/v3/ticker/price"
      r=subprocess.run(["curl","-sS","--max-time","12","-H","User-Agent: Mozilla/5.0",url], capture_output=True, text=True)
      data=json.loads(r.stdout) if (r.returncode==0 and (r.stdout or "").strip().startswith("[")) else []
      px={}
      if isinstance(data,list):
        for it in data:
          sym=(it.get("symbol") or "")
          if sym.endswith("USDT"):
            k=sym[:-4]
            try:
              v=float(it.get("price") or 0.0)
              if v>0: px[k]=v
            except Exception:
              pass
      if isinstance(payload,dict) and isinstance(payload.get("lista"),list) and px:
        for it in payload["lista"]:
          try:
            if isinstance(it,dict) and it.get("par") and float(it.get("preco") or 0)==0:
              v=px.get(it["par"])
              if v:
                it["preco"]=v
                it["eta"]=(it.get("eta") or "") + " (BN)"
          except Exception:
            pass
    except Exception:
      pass

    ### KILL_SWITCH_ENFORCE ###
    try:
      if 'KILL_SWITCH' in globals() and KILL_SWITCH:
        _lst = payload.get('lista') or payload.get('sinais') or []
        if isinstance(_lst, list):
          for _it in _lst:
            if isinstance(_it, dict):
              _it['side'] = 'NÃO ENTRAR'
              _it['motivo'] = 'KILL_SWITCH'
              _it['ganho_pct'] = 0.0
    except Exception:
      pass

    ### MOTIVO_ENFORCE ###
    try:
      _lst = payload.get('lista') or payload.get('sinais') or []
      if isinstance(_lst, list):
        for _it in _lst:
          if not isinstance(_it, dict):
            continue
          _side = _it.get('side') or _it.get('sinal') or ''
          if _side == 'NÃO ENTRAR':
            _m = _it.get('motivo')
            if _m is None or _m == '':
              try:
                _g = float(_it.get('ganho_pct') or _it.get('ganho') or 0.0)
              except Exception:
                _g = 0.0
              _it['motivo'] = (('GANHO<' + str(GAIN_MIN) + '%') if _g < GAIN_MIN else 'SEM DADOS')
          else:
            if 'motivo' not in _it or _it.get('motivo') is None:
              _it['motivo'] = ''
    except Exception:
      pass

    ### PATCH_SEM_DADOS ###
    try:
      _lst = payload.get('lista') or payload.get('sinais') or []
      if isinstance(_lst, list):
        def _f(x):
          try:
            return float(x)
          except Exception:
            return 0.0
        for _it in _lst:
          if not isinstance(_it, dict):
            continue
          _side = _it.get('side') or _it.get('sinal')
          if _side != 'NÃO ENTRAR':
            continue
          _preco = _f(_it.get('preco'))
          _alvo  = _f(_it.get('alvo'))
          _atr4  = _f(_it.get('atr_4h') or _it.get('atr4h') or _it.get('atr'))
          # prioridade: SEM DADOS
          if _preco <= 0 or _alvo <= 0 or (_atr4 != 0.0 and _atr4 <= 0):
            _it['motivo'] = 'SEM DADOS'
    except Exception:
      pass

    json.dump(payload, f,ensure_ascii=False,indent=2)
  print(f"OK pro.json atualizado: {OUT_PATH} | itens={len(results)} | updated_brt={updated_brt}")

if __name__=="__main__":
  main()
