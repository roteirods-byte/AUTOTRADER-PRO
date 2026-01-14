from dataclasses import dataclass
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")

# Regra mínima base (pode virar ENV futuramente)
GAIN_MIN_BASE = 3.0

# Lista base (sem USDT)
COINS = [
  "AAVE","ADA","APT","ARB","ATOM","AVAX","AXS","BCH","BNB","BTC","DOGE","DOT","ETH","FET",
  "FIL","FLUX","ICP","INJ","LDO","LINK","LTC","NEAR","OP","PEPE","POL","RATS","RENDER",
  "RUNE","SEI","SHIB","SOL","SUI","TIA","TNSR","TON","TRX","UNI","WIF","XRP"
]
