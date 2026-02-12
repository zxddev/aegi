#!/usr/bin/env bash
# Author: msq

set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8800}"
CASE_UID="${CASE_UID:-case_pykeen_live_20260211}"
EMBED_DIM="${EMBED_DIM:-16}"
EPOCHS="${EPOCHS:-1}"
PRED_TOP_K="${PRED_TOP_K:-5}"
ENTITY_UID="${ENTITY_UID:-lp_entity_0}"
ANOMALY_THRESHOLD="${ANOMALY_THRESHOLD:-0.2}"

echo "[1/4] Train model for case: ${CASE_UID}"
curl -fsS \
  -X POST \
  "${API_BASE}/cases/${CASE_UID}/links/train" \
  -H "Content-Type: application/json" \
  -d "{\"embedding_dim\": ${EMBED_DIM}, \"num_epochs\": ${EPOCHS}}" \
  | python3 -m json.tool

echo
echo "[2/4] Global missing-link predictions"
curl -fsS \
  "${API_BASE}/cases/${CASE_UID}/links/predictions?top_k=${PRED_TOP_K}&min_score=0.0" \
  | python3 -m json.tool

echo
echo "[3/4] Entity-specific predictions for ${ENTITY_UID}"
curl -fsS \
  "${API_BASE}/cases/${CASE_UID}/links/predictions/${ENTITY_UID}?direction=both&top_k=${PRED_TOP_K}" \
  | python3 -m json.tool

echo
echo "[4/4] Anomalous triples (show first 10)"
curl -fsS \
  "${API_BASE}/cases/${CASE_UID}/links/anomalies?threshold=${ANOMALY_THRESHOLD}" \
  | python3 -c '
import json
import sys

data = json.load(sys.stdin)
anomalies = data.get("anomalies", [])
print(json.dumps({"count": len(anomalies), "sample": anomalies[:10]}, ensure_ascii=False, indent=2))
'
