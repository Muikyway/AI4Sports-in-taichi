# 太极规则生成案例（极简扁平 Clause DSL）

> 本文件示范如何将自然语言规则翻译为规则 JSON。每条规则包含规则身份、动作/阶段、违规项、扁平条件及扣分信息。它只描述规则本身，不包含视频输入、帧号、实测值、置信度、运行状态、事件实例或检测报告。
>
> 下面的数值是**格式示例**，不是已验证的权威规则数值。真实生成时，每个精确数值必须附数据库来源；检索不到或来源冲突时，不得照抄示例，必须返回数据库更新请求。

## 案例一：弓步规格错误（编码 12）

**自然语言规则**：弓步前膝明显超过脚尖、后腿明显弯曲或后脚跟离地，任一情况成立时，记弓步规格错误，扣 0.10 分。

`ANY` 表示三个独立违规原因中任意一个成立即可触发本规则。阈值 `20 deg` 仅为格式示例，必须以数据库记录为准；前膝过脚尖和后脚跟离地按布尔条件表达。

```json
{
  "rule_id": "bow_step_spec_error",
  "action": "bow_step",
  "phase": "support",
  "violation_items": [
    {
      "item_id": "front_knee_over_toe",
      "reason_zh": "弓步前膝明显超过同侧脚尖",
      "logic": "ALL",
      "clauses": [
        { "primitive": "V_KNEE_OVER_TOE", "args": { "side": "front" }, "op": "==", "target": true, "unit": "bool" }
      ]
    },
    {
      "item_id": "rear_leg_bent",
      "reason_zh": "弓步后腿明显弯曲",
      "logic": "ALL",
      "clauses": [
        { "primitive": "KNEE_BEND", "args": { "side": "rear" }, "op": ">", "target": 20.0, "unit": "deg" }
      ]
    },
    {
      "item_id": "rear_heel_lifted",
      "reason_zh": "弓步后脚跟离地",
      "logic": "ALL",
      "clauses": [
        { "primitive": "V_HEEL_LIFT", "args": { "side": "rear" }, "op": "==", "target": true, "unit": "bool" }
      ]
    }
  ],
  "violation_logic": "ANY",
  "deduction": { "code": "12", "points": 0.10, "group": "E", "scope": "technique" },
  "numeric_provenance": [
    { "field": "violation_items[rear_leg_bent].clauses[0].target", "value": 20.0, "unit": "deg", "database_record_id": "REQUIRED" },
    { "field": "deduction.points", "value": 0.10, "unit": "point", "database_record_id": "REQUIRED" }
  ]
}
```

## 案例二：提膝未过腰（编码 03）

**自然语言规则**：提膝独立时，提起的膝盖未超过腰部基准，扣 0.10 分。

当前 primitive 表把 `KNEE_LIFT_HEIGHT` 定义为“膝相对同侧髋的高度差”。这不等同于“膝相对腰部基准的高度差”。因此此案例**不伪造可执行条件**：除非数据库/DSL 明确指定腰部参照 primitive，否则应返回 `DB_UPDATE_REQUEST`，请求补充经确认的测量定义。以下展示请求格式，不是规则 JSON。

```json
{
  "status": "DB_UPDATE_REQUEST",
  "rule_id": "knee_raise_below_waist",
  "missing_items": [
    {
      "field": "condition.primitive_or_reference",
      "requested_meaning": "提起膝盖相对腰部基准的高度",
      "reason": "现有 KNEE_LIFT_HEIGHT 的基准为同侧髋，不能直接代表腰部"
    },
    {
      "field": "deduction.points",
      "requested_meaning": "编码 03 的正式扣分数值及来源",
      "reason": "需要权威数据库记录"
    }
  ]
}
```

## 案例三：跌叉两大腿夹角过小（编码 01）

**自然语言规则**：跌叉支撑阶段，两大腿夹角小于或等于 45 度，判为该项规格错误。

该条件可以直接映射为 `THIGH_SPLIT_ANGLE`。阈值及扣分必须通过数据库确认。

```json
{
  "rule_id": "split_thigh_angle_too_small",
  "action": "split",
  "phase": "support",
  "violation_items": [
    {
      "item_id": "thigh_split_angle_le_45",
      "reason_zh": "跌叉两大腿夹角小于或等于规定值",
      "logic": "ALL",
      "clauses": [
        { "primitive": "THIGH_SPLIT_ANGLE", "args": {}, "op": "<=", "target": 45.0, "unit": "deg" }
      ]
    }
  ],
  "violation_logic": "ANY",
  "deduction": { "code": "01", "points": 0.10, "group": "E", "scope": "technique" },
  "numeric_provenance": [
    { "field": "violation_items[0].clauses[0].target", "value": 45.0, "unit": "deg", "database_record_id": "REQUIRED" },
    { "field": "deduction.points", "value": 0.10, "unit": "point", "database_record_id": "REQUIRED" }
  ]
}
```

## 案例四：马步站距过大（编码 13）

**自然语言规则**：马步两脚横向间距大于本人脚长的 3.5 倍，扣 0.10 分。

极简 DSL 提供 `STANCE_FOOT_RATIO`，形式上可表达该条件；但规范将其定义为使用估算脚长 `foot_len_est` 的代理量。生成规则时必须确认数据库是否认可此估算口径，并能提供阈值与扣分来源。否则返回数据库更新请求，不得把代理值写成“本人真实脚长”的精确测量。

```json
{
  "rule_id": "horse_stance_too_wide",
  "action": "horse_stance",
  "phase": "support",
  "violation_items": [
    {
      "item_id": "stance_width_over_foot_ratio",
      "reason_zh": "马步两脚横向间距超过本人脚长规定倍数",
      "logic": "ALL",
      "clauses": [
        { "primitive": "STANCE_FOOT_RATIO", "args": {}, "op": ">", "target": 3.5, "unit": "ratio" }
      ]
    }
  ],
  "violation_logic": "ANY",
  "deduction": { "code": "13", "points": 0.10, "group": "E", "scope": "technique" },
  "numeric_provenance": [
    { "field": "violation_items[0].clauses[0].target", "value": 3.5, "unit": "ratio", "database_record_id": "REQUIRED" },
    { "field": "deduction.points", "value": 0.10, "unit": "point", "database_record_id": "REQUIRED" }
  ],
  "proxy_policy": "requires_database_approval"
}
```

## 案例中的格式约定

- 一条规则下可用 `violation_items` 表达多个具名违规原因；每个 item 的 `logic` 仅用单层 `ALL` 或 `ANY`，`clauses` 中每项均为极简 DSL 定义的五元组。
- `violation_logic` 表示多个 item 之间如何组合；这里的 JSON envelope 是案例展示约定，当前极简 DSL 文档尚未为完整规则 envelope 提供 Pydantic 模型。实现时应固定该 envelope schema。
- 规则定义中不填写 `frame_window`、`chapter_instance_id`、`actual_value`、`confidence`、`source`、`state`、`trace`、去重结果等运行期数据。
- `numeric_provenance` 是生成审计元数据，不是规则条件。`database_record_id: "REQUIRED"` 代表示例尚未绑定数据库记录，不能作为 `APPROVED` 规则发布。
- 如果规则涉及的数值、扣分、参照物或代理口径无法在数据库中确认，输出 `DB_UPDATE_REQUEST`，不要自行补值。
