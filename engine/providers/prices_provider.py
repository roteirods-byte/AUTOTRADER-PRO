"""
Prices Provider (placeholder).
Troque por Binance/Bybit depois.
"""
import random

def get_price(symbol: str) -> float:
    # preço “fake” estável por símbolo (apenas para demo)
    rnd = random.Random(symbol)
    base = rnd.uniform(0.05, 200.0)
    jitter = rnd.uniform(-0.02, 0.02) * base
    return max(0.00001, base + jitter)
