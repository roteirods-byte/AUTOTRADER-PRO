#!/usr/bin/env bash
set -e

BASE="http://127.0.0.1:8095"

echo "== HEALTH =="
curl -sS -i "$BASE/health" | head -n 5
echo

echo "== PRO (JSON) =="
curl -sS -i "$BASE/api/pro" | head -n 5
echo

echo "== TOP10 (JSON) =="
curl -sS -i "$BASE/api/top10" | head -n 5
echo

echo "== AUDIT (JSON) =="
curl -sS -i "$BASE/api/audit" | head -n 5
echo

echo "OK: endpoints vivos"
