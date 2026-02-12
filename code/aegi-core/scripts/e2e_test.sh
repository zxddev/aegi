#!/usr/bin/env bash
# AEGI 端到端测试脚本
# 用法: bash scripts/e2e_test.sh
#
# 前置条件:
#   1. docker compose -f docker-compose.dev.yml up -d  (基础设施)
#   2. AntiHub Plugin API 已启动 (端口 8045, X-Account-Type: kiro)
#   3. OpenClaw Gateway 已启动 (端口 4800, 可选)
#
# 测试流程:
#   Step 1: 健康检查
#   Step 2: 创建 Case
#   Step 3: 上传文档 → 解析 + 入库
#   Step 4: 提交文本证据
#   Step 5: 查询知识图谱
#   Step 6: 运行 Pipeline (quick playbook)
#   Step 7: 获取报告
#   Step 8: 搜索 (SearXNG)
#   Step 9: 查看 Playbooks / Stages

set -euo pipefail

# 实际服务端口（匹配 docker ps）
export AEGI_POSTGRES_DSN_ASYNC="postgresql+asyncpg://aegi:aegi@localhost:15432/aegi"
export AEGI_POSTGRES_DSN_SYNC="postgresql+psycopg://aegi:aegi@localhost:15432/aegi"
export AEGI_NEO4J_URI="bolt://localhost:7687"
export AEGI_NEO4J_PASSWORD="neo4jzmkj123456"
export AEGI_QDRANT_URL="http://localhost:6333"
export AEGI_QDRANT_GRPC_URL="localhost:6334"
export AEGI_QDRANT_API_KEY="qdrantzmkj123456"
export AEGI_S3_ENDPOINT_URL="http://localhost:9000"
export AEGI_S3_ACCESS_KEY="root"
export AEGI_S3_SECRET_KEY="miniozmkj123456"
export AEGI_SEARXNG_BASE_URL="http://localhost:8701"
export AEGI_LITELLM_BASE_URL="http://127.0.0.1:8045"
export AEGI_LITELLM_API_KEY="sk-9ce69cfddf90f90c3720e71d65aecfc1f210e3e66b2921ef773a4dd8e8c278af"
export AEGI_LITELLM_DEFAULT_MODEL="claude-haiku-4-5-20251001"
export AEGI_LITELLM_EXTRA_HEADERS='{"X-Account-Type":"kiro"}'

BASE_URL="${AEGI_BASE_URL:-http://localhost:8700}"
USER="e2e_test_user"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✅ $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

# ─── Step 1: Health ───
info "Step 1: 健康检查"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
[ "$HTTP_CODE" = "200" ] && pass "Health OK" || fail "Health check failed (HTTP $HTTP_CODE)"

# ─── Step 2: Create Case ───
info "Step 2: 创建 Case"
CASE_RESP=$(curl -s -X POST "$BASE_URL/openclaw/tools/create_case" \
  -H "Content-Type: application/json" \
  -d "{\"user\": \"$USER\", \"title\": \"E2E测试案例 - 地缘政治分析\", \"description\": \"端到端测试\"}")
echo "  Response: $CASE_RESP"
CASE_OK=$(echo "$CASE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))")
[ "$CASE_OK" = "True" ] && pass "Case created" || fail "Create case failed"
CASE_UID=$(echo "$CASE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['case_uid'])")
info "  Case UID: $CASE_UID"

# ─── Step 3: Upload Document ───
info "Step 3: 上传文档"
# 创建临时测试文件
TMPFILE=$(mktemp /tmp/aegi_test_XXXXXX.txt)
cat > "$TMPFILE" << 'EOF'
情报简报：东南亚地缘政治动态

2024年第三季度，南海局势持续紧张。菲律宾与中国在仁爱礁附近多次发生对峙。
美国加强了在该地区的军事存在，派遣航母战斗群进行"自由航行"行动。

经济层面，RCEP 协定持续推进区域经济一体化。中国-东盟贸易额同比增长12%。
然而，供应链多元化趋势明显，越南和印度成为主要受益者。

分析师评估：短期内军事冲突风险较低，但误判风险上升。经济相互依存是主要稳定因素。
EOF

DOC_RESP=$(curl -s -X POST "$BASE_URL/ingest/document" \
  -F "file=@$TMPFILE" \
  -F "case_id=$CASE_UID" \
  -F "actor_id=$USER")
rm -f "$TMPFILE"
echo "  Response: $DOC_RESP"
DOC_OK=$(echo "$DOC_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))")
[ "$DOC_OK" = "True" ] && pass "Document ingested" || fail "Document ingest failed"

# ─── Step 4: Submit Text Evidence ───
info "Step 4: 提交文本证据"
EV_RESP=$(curl -s -X POST "$BASE_URL/openclaw/tools/submit_evidence" \
  -H "Content-Type: application/json" \
  -d "{
    \"user\": \"$USER\",
    \"content\": \"日本宣布将防卫预算提升至GDP的2%，并加强与菲律宾的安全合作。这被视为对中国在南海活动的回应。\",
    \"source\": \"https://example.com/japan-defense\",
    \"case_id\": \"$CASE_UID\"
  }")
echo "  Response: $EV_RESP"
EV_OK=$(echo "$EV_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))")
[ "$EV_OK" = "True" ] && pass "Evidence submitted" || fail "Submit evidence failed"

# ─── Step 5: Query KG ───
info "Step 5: 查询知识图谱"
KG_RESP=$(curl -s -X POST "$BASE_URL/openclaw/tools/query_kg" \
  -H "Content-Type: application/json" \
  -d "{\"user\": \"$USER\", \"query\": \"南海 菲律宾 军事\", \"case_id\": \"$CASE_UID\"}")
echo "  Response: $(echo "$KG_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'ok={d[\"ok\"]}, results={len(d.get(\"data\",{}).get(\"results\",[]))}')")"
pass "KG query completed"

# ─── Step 6: Run Pipeline ───
info "Step 6: 运行 Pipeline (default playbook, with LLM claim extraction)"
PIPE_RESP=$(curl -s --max-time 120 -X POST "$BASE_URL/openclaw/tools/run_pipeline" \
  -H "Content-Type: application/json" \
  -d "{\"user\": \"$USER\", \"case_id\": \"$CASE_UID\", \"playbook\": \"default\"}")
echo "  Response: $(echo "$PIPE_RESP" | python3 -m json.tool 2>/dev/null || echo "$PIPE_RESP")"
PIPE_OK=$(echo "$PIPE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))")
[ "$PIPE_OK" = "True" ] && pass "Pipeline completed" || fail "Pipeline failed"

# ─── Step 7: Get Report ───
info "Step 7: 获取报告"
RPT_RESP=$(curl -s -X POST "$BASE_URL/openclaw/tools/get_report" \
  -H "Content-Type: application/json" \
  -d "{\"user\": \"$USER\", \"case_id\": \"$CASE_UID\"}")
echo "  Response: $(echo "$RPT_RESP" | python3 -m json.tool 2>/dev/null || echo "$RPT_RESP")"
pass "Report retrieved"

# ─── Step 8: Search ───
info "Step 8: SearXNG 搜索"
SEARCH_RESP=$(curl -s -f -G "$BASE_URL/search" --data-urlencode "q=南海局势2024")
SEARCH_COUNT=$(echo "$SEARCH_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])")
echo "  Results: $SEARCH_COUNT"
[ "$SEARCH_COUNT" -gt 0 ] && pass "Search returned results" || fail "SearXNG search returned 0 results"

# ─── Step 9: Playbooks & Stages ───
info "Step 9: 查看 Playbooks / Stages"
PB_RESP=$(curl -s "$BASE_URL/openclaw/tools/playbooks")
echo "  Playbooks: $(echo "$PB_RESP" | python3 -c "import sys,json; print([p['name'] for p in json.load(sys.stdin)['playbooks']])")"
ST_RESP=$(curl -s "$BASE_URL/openclaw/tools/stages")
echo "  Stages: $(echo "$ST_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['stages'])")"
pass "Introspection OK"

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  E2E 测试完成！${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
