# 太极自然语言规则到 JSON DSL：生成专用工作流

## 1. 工作目标

输入一条自然语言规则，输出符合既有太极 JSON DSL 的规则定义。输出前必须确认：

1. 规则含义被完整翻译，没有擅自补充动作条件。
2. 每一个准确数值都有数据库记录或已批准的规则模板作为依据。
3. 数值的单位、适用动作、版本和来源可以追溯。
4. 逻辑结构、字段类型、枚举值和扣分项符合 DSL 规范。
5. 规则通过合成反事实测试后，才允许标记为可发布。

## 2. 范围边界

本工作流只负责**生成规则定义**和**检查生成结果**，不负责运行期检测。它不接收、推断或生成：

- 视频、图像、姿态序列或真实帧区间；
- 某次动作的实际测量值、置信度、轨迹和检测结果；
- 运行期视觉请求、章节实例、事件去重或执行报告。

如果目标 JSON DSL 中有 `phase`、`frame_window`、`stance` 等字段，它们在本流程中只能作为规则的静态定义，并且必须来自规则数据库或已批准模板。不能从不存在的运行期视频中填写；数据库没有对应精确值时，返回 `DB_UPDATE_REQUEST`。

## 3. 总体流程

```text
自然语言规则 + JSON DSL 规范
        |
        v
Translator Agent
        |
        v
候选 rule_json + 数值来源声明
        |
        v
Database-backed Validator（独立检索数据库）
        |
        +-- 缺少或冲突的精确数值 --> DB_UPDATE_REQUEST
        |
        +-- 字段/逻辑/映射错误 ----> Modifier Agent
        |                              |
        |                              v
        |                       重新完整校验
        v
Counterfactual Audit Agent
        |
        v
合成测试 + 确定性静态求值器
        |
        +-- 失败 --> Modifier Agent -> 重新校验与审计
        |
        v
APPROVED：生成最终 JSON DSL
```

数据库缺失是阻断条件，不能由修改 Agent 猜测、插值或引用自然语言常识来绕过。

## 4. Agent 职责

### 4.1 Translator Agent：自然语言到候选 JSON

**输入**：自然语言规则、目标 JSON DSL schema、允许使用的动作/阶段/原语清单。

**输出**：候选 `rule_json` 和 `numeric_provenance`。

职责：

- 识别规则对象、适用阶段、条件、组合逻辑、违规项和扣分信息。
- 将自然语言条件映射到已注册的 primitive、operator、unit 和 deduction code。
- 对每个数值记录字段路径、单位、来源关键词和候选数据库条目。
- 保留原规则无法确定的部分，不得自行补数字、单位或阈值。

Translator 可以先检索数据库提高命中率，但 Validator 必须重新独立检索，不能把 Translator 的引用当作事实证明。

### 4.2 Database-backed Validator：数据库约束校验器

这是确定性校验器，不依赖 LLM 的自我判断。它根据原始规则文本、候选 JSON、动作代码、原语名称、数值和单位独立搜索数据库的相关部分。

必须检查：

- 每个精确数值是否有明确记录：阈值、角度、距离、时长、比例、次数、扣分、分数上限，以及目标 DSL 中要求的静态帧窗口。
- 数值的单位、方向、比较符、适用动作/阶段、有效版本是否一致。
- 数据记录是否为正式、可用、未废弃的记录；存在多个冲突记录时不得自行选择。
- `rule_id`、动作代码、primitive、operator、枚举和逻辑树是否符合 schema。
- `violation_items` 是否完整，每个违规项是否有可执行的条件和唯一扣分归因。
- 生成 JSON 中是否出现未声明、无法解释或与原文无关的字段。

数据库检索不到、记录冲突或单位无法换算时，输出：

```json
{
  "status": "DB_UPDATE_REQUEST",
  "rule_id": "...",
  "missing_items": [
    {
      "field_path": "conditions[0].threshold",
      "value_type": "number",
      "unit": "degree",
      "search_terms": ["..."],
      "reason": "no_authoritative_record"
    }
  ]
}
```

此状态表示需要补充或修订数据库，不能发布半成品规则。

### 4.3 Modifier Agent：有证据的规则修复

**输入**：候选 JSON、Validator 诊断、数据库证据、原始自然语言规则。

**输出**：JSON Patch 或完整修订版 JSON，以及修改理由。

允许修复：

- 字段路径、类型、枚举、逻辑树和 primitive 映射；
- 已有数据库证据支持的单位、比较符、字段关系；
- 漏掉的违规项或错误的扣分归因。

禁止：

- 编造数值、来源、动作代码或数据库记录；
- 用近似值替代缺失的精确值；
- 改变原规则意图来让测试通过；
- 修改后跳过完整数据库校验。

如果诊断属于数据库缺失，Modifier 只能保留 `DB_UPDATE_REQUEST`，不能“修复”为猜测值。

### 4.4 Counterfactual Audit Agent：生成语义反事实测试

这是生成质量审计，不是视频检测器。它只读取规则 AST/JSON、原始规则和数据库证据，生成合成的标量或状态测试向量。

每条规则至少生成：

- 合规样例；
- 明确违规样例；
- 阈值等于、刚低于、刚高于的边界样例；
- `AND`、`OR`、`NOT`、保持时长等逻辑的组合样例；
- 多个违规项同时成立时的扣分归因样例。

确定性静态求值器只对生成的 JSON 逻辑求值，并检查期望结果是否一致。它不读取视频、不调用姿态模型、不生成实际帧范围，也不执行运行期事件聚合。

审计失败时返回 `AUDIT_FAILED` 及失败测试；若是结构或逻辑问题交给 Modifier，若是数值无数据库依据仍返回 `DB_UPDATE_REQUEST`。

## 5. 状态与交付契约

推荐状态：

- `READY_FOR_VALIDATION`：Translator 已生成候选规则。
- `DB_UPDATE_REQUEST`：至少一个精确值缺少权威数据库依据，或数据库记录冲突。
- `REPAIR_REQUIRED`：有足够证据，但字段、映射或逻辑需要修改。
- `AUDIT_FAILED`：合成反事实测试未通过。
- `APPROVED`：数据库、schema、逻辑和反事实审计全部通过。

最终交付至少包含：

```json
{
  "status": "APPROVED",
  "rule_json": {},
  "numeric_provenance": [],
  "validation": {
    "database_checks": [],
    "counterfactual_tests": []
  }
}
```

`numeric_provenance` 是生成审计记录，不属于运行期检测结果。

## 6. 既有规则 MD 的范围审计

### 6.1 `prompt/全面版json+DSL/h36m17_taiji_json_old.md`

**可保留为生成规范的内容**：

- Typed JSON-AST 的字段和类型设计；
- primitive 注册表、比较符和逻辑组合；
- `violation_items` 与“一码多因”的扣分归因；
- 动作/阶段/规则编码和数值单位约束。

**混入运行期检测的内容**：

- MotionBERT 的逐帧骨架输入、`P[frame][joint][x,y,z]` 和坐标标定；
- `input_spec.fps`、视觉模式、活动视觉请求和骨架优先短路；
- `NEEDS_VISION`、`UNKNOWN` 等运行期不确定状态；
- 从视频推导的 `frame_window`、实际轨迹、实际值和置信度；
- `chapter_instance_id`、帧范围、事件去重、执行 trace 和运行期报告；
- 代理检测、置信度阈值和模糊带治理。

**判断**：旧版不是纯生成文档，但其 Typed AST 更适合作为生成规则的主规范。应保留静态 schema 和原语定义，把执行器、输入数据和执行输出拆到独立的 runtime 文档。

### 6.2 `prompt/h36m17_taiji_json_dsl_spec.md` 与 `rules/h36m17_taiji_json_dsl_spec.md`

**可保留为生成规范的内容**：

- 规则 envelope、动作/阶段编码和 primitive 清单；
- JSON 字段约束、数值单位和违规项结构；
- MicroDSL 作为人类可读的派生表示或导出格式。

**混入运行期检测的内容**：

- 逐帧 MotionBERT 输入和 W/B 坐标校准；
- 时间运动量、视觉原语的执行语义；
- 四值运行期语义、视觉 fallback 和运行时请求；
- `chapter_instance_id`、帧重叠去重和事件聚合；
- 带实际帧范围、trace、source、vision、actual value 的评估报告；
- 同时承载输入规则和运行结果的 Pydantic/执行器代码。

**判断**：这两份新版内容都混合了规则定义和机器执行接口，不能直接作为唯一的 LLM 生成协议。把逻辑压成字符串 MicroDSL 会削弱字段级类型检查，也会让数值来源更难独立审计。建议以旧版 Typed JSON-AST 作为生成主格式，MicroDSL 只做可选展示或导出；两份新版只保留一份作为运行接口或导出规范，避免重复维护。

### 6.3 其他 DSL 与案例文件

`prompt/H36M-17 太极拳动作 DSL（规范版）.md` 的硬约束和自然语言到条件的映射可作为生成提示材料，但其中的执行结果格式和运行状态也应移出生成契约。两份 curated cases 应只保留经过数据库确认的输入规则/输出 JSON；案例中的视频帧、实际测量值和检测结果不能作为生成阶段的必填字段。

## 7. 是否满足当前需求

按“自然语言规则翻译为既有 JSON、所有精确数值必须可回查数据库、缺失则请求更新数据库”的要求，原来的两份 JSON MD 都**没有完全满足**，主要问题是把生成规范和运行期检测规范写在了同一份文档中，导致字段冗余和职责混乱。

当前建议的最小生成契约只保留：

- `rule_id`、动作/阶段静态标识；
- 条件逻辑树、primitive、参数、operator、unit；
- `violation_items`、扣分和规则元数据；
- 必要的静态 `phase`/`frame_window`/`stance`，但只能来自数据库或批准模板；
- 数值来源、数据库记录 ID、版本和校验结果。

运行期视频输入、真实测量、视觉 fallback、实例去重、trace 和执行报告不应出现在生成 Agent 的输入输出契约中。
