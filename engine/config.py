from dataclasses import dataclass
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")

# Regra mínima base (pode virar ENV futuramente)
GAIN_MIN_BASE = 3.0

# Lista base (sem USDT) — Universo oficial (78) em ordem alfabética
COINS = [
  "AAVE","ADA","APE","APT","AR","ARB","ATOM","AVAX","AXS","BAT","BCH","BLUR","BNB","BONK","BTC",
  "COMP","CRV","DASH","DGB","DENT","DOGE","DOT","EGLD","EOS","ETC","ETH","FET","FIL","FLOKI","FLOW",
  "FTM","GALA","GLM","GRT","HBAR","ICP","IMX","INJ","IOST","KAS","KAVA","KSM","LINK","LTC","MANA",
  "MATIC","MKR","NEAR","NEO","OMG","ONT","OP","ORDI","PEPE","QNT","QTUM","RNDR","ROSE","RUNE","SAND",
  "SEI","SHIB","SNX","SOL","STX","SUI","SUSHI","THETA","TIA","TRX","UNI","VET","XEM","XLM","XRP",
  "XVS","ZEC","ZRX"
]
