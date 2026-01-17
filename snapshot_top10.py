#!/usr/bin/env python3
import json, os
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
SRC = "/home/roteiro_ds/AUTOTRADER-PRO/data/pro.json"
DST_DIR = "/home/roteiro_ds/AUTOTRADER-PRO/data/hist"

def main():
    os.makedirs(DST_DIR, exist_ok=True)

    if not os.path.exists(SRC):
        return

    with open(SRC, "r", encoding="utf-8") as f:
        d = json.load(f)

    ts = datetime.now(TZ).strftime("%Y%m%d_%H%M")
    top10 = (d.get("lista") or [])[:10]
    out = {
        "saved_brt": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "updated_brt": d.get("updated_brt", ""),
        "top10": top10
    }

    p = os.path.join(DST_DIR, f"top10_{ts}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # limpa arquivos antigos (ex: > 14 dias)
    os.system(f"find {DST_DIR} -type f -name 'top10_*.json' -mtime +14 -delete >/dev/null 2>&1")

if __name__ == "__main__":
    main()
