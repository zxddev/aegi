/**
 * OpenClaw Plugin: AEGI Tools
 *
 * Registers custom tools that let the agent call back into the AEGI backend.
 * Each tool does an HTTP POST to the corresponding AEGI endpoint.
 *
 * Install: add to openclaw.yaml plugins.load.paths
 */

const AEGI_BASE = process.env.AEGI_BASE_URL || "http://localhost:8000";

function makeAegiTool(name, description, parameters, endpoint) {
  return {
    name,
    description,
    parameters,
    async execute(toolCallId, params) {
      const res = await fetch(`${AEGI_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      const data = await res.json();
      return { type: "text", text: JSON.stringify(data) };
    },
  };
}

/** @type {import('openclaw').OpenClawPluginDefinition} */
export default {
  id: "aegi-tools",
  name: "AEGI Tools",
  version: "0.1.0",
  description: "Custom tools for AEGI intelligence analysis backend",

  register(api) {
    api.registerTool(
      makeAegiTool(
        "aegi_submit_evidence",
        "向 AEGI 系统提交收集到的证据材料",
        {
          type: "object",
          properties: {
            user:    { type: "string", description: "当前用户ID" },
            content: { type: "string", description: "证据内容" },
            source:  { type: "string", description: "来源URL或描述" },
            case_id: { type: "string", description: "关联案例ID" },
          },
          required: ["user", "content", "source"],
        },
        "/openclaw/tools/submit_evidence",
      ),
    );

    api.registerTool(
      makeAegiTool(
        "aegi_create_case",
        "在 AEGI 中创建新的分析案例",
        {
          type: "object",
          properties: {
            user:        { type: "string", description: "当前用户ID" },
            title:       { type: "string", description: "案例标题" },
            description: { type: "string", description: "案例描述" },
          },
          required: ["user", "title"],
        },
        "/openclaw/tools/create_case",
      ),
    );

    api.registerTool(
      makeAegiTool(
        "aegi_query_kg",
        "查询 AEGI 知识图谱，获取实体关系和历史情报",
        {
          type: "object",
          properties: {
            user:  { type: "string", description: "当前用户ID" },
            query: { type: "string", description: "查询内容" },
            limit: { type: "integer", description: "返回结果数量上限" },
          },
          required: ["user", "query"],
        },
        "/openclaw/tools/query_kg",
      ),
    );

    api.registerTool(
      makeAegiTool(
        "aegi_run_pipeline",
        "触发 AEGI 分析管线对指定案例进行深度分析",
        {
          type: "object",
          properties: {
            user:    { type: "string", description: "当前用户ID" },
            case_id: { type: "string", description: "案例ID" },
          },
          required: ["user", "case_id"],
        },
        "/openclaw/tools/run_pipeline",
      ),
    );

    api.registerTool(
      makeAegiTool(
        "aegi_get_report",
        "获取 AEGI 生成的分析报告",
        {
          type: "object",
          properties: {
            user:    { type: "string", description: "当前用户ID" },
            case_id: { type: "string", description: "案例ID" },
          },
          required: ["user", "case_id"],
        },
        "/openclaw/tools/get_report",
      ),
    );

    api.logger.info("AEGI tools registered (base: " + AEGI_BASE + ")");
  },
};
