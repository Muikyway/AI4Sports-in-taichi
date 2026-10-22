# H36M-17 太极拳混合型动作规约语言：核心语法规范（v3.0 扁平 JSON + 内联微公式版）

> 本规范针对徒手太极拳竞赛规则（剔除器械条款），针对大语言模型（LLM）代码生成特性进行了专门优化：采用**“外层一级扁平 JSON 信封（100% 兼容 LLM `Structured Outputs` 受限解码，零递归嵌套）+ 内层 `@item_id: 微公式`（自然支持 `AND / OR / NOT / HOLD` 组合与子项级归因）”**的混合架构。本文件仅包含核心语法、原语算子表、扣分注册表与 Pydantic v2 校验器；典型动作案例详见配套《典型规则案例库（v3.0）》。

## 1. 为什么采用“外层扁平 JSON + 内层 `@item_id: 微公式`”架构？

1. **彻底消除多层递归 JSON-AST 带来的括号噪声与解码冲突**：主流大模型 API 的结构化输出（`Structured Outputs`）不支持递归自引用 JSON Schema（`$ref` 递归树），且深层 JSON 树会显著拉低模型推理准确率。外层固定为一级扁平 JSON，大模型可实现 100% 零语法报错生成。
2. **避免同阶段同编码规则的 3 倍冗余膨胀**：在同一动作阶段（如 `hold_left_bow`）判定同一扣分编码（如编码 `12` 弓步规格错误）时，通过 `"expr": ["@子项ID: 公式1", "@子项ID: 公式2"]` 挂载多个带名原子表达式，既避免拆成 3 个重复的顶层 Rule 块，又能精确追踪到底是哪一个具体原因触发了扣分。
3. **完美保留原版 DSL 的时序与逻辑表达力**：内层微公式仅在一行内书写，原生支持 `NOT HOLD(BALANCE_STILL() == true, 2000ms)`、`(A AND B)`、`BETWEEN` 与 `IN`，由轻量级解析器在毫秒级完成强类型校验。

## 2. 双坐标系与输入预处理标定协议（Calibration Protocol）

每帧输入为 MotionBERT 产出的 `P[frame][joint][x,y,z]`（`h36m-17` 拓扑），三维长度单位为身高归一化 `norm`，二维图像距离为 `image_norm`（`0..1`），角度为 `deg`，比例为 `ratio`，时间为 `frame` 或 `ms`。

| 坐标系名称 | 符号 | 标定方法与适用原语 | 标定失败降级策略 |
| :--- | :--- | :--- | :--- |
| **地面世界坐标系** | `W` | 以起势直立帧标定真实重力反方向为 `+up`（消除相机俯仰角），以非腾空期支撑踝最低包络面锚定 `up = 0` 水平地面。所有**绝对高度**（`HEIGHT`）、**支撑期水平漂移**（`MAX_DRIFT`）、**净位移**（`DISPLACEMENT`）及**水平累计旋转角**（`YAW_ROTATION`）均在 `W` 下计算。 | 若相机剧烈运动或地面平面拟合残差超标，依赖 `W` 的原语统一返回状态 `U`（`UNKNOWN`）。 |
| **解剖学朝向坐标系** | `B` | 由骨盆与双肩水平投影确定表演者瞬时或阶段朝向：`up` 竖直向上，`left` 指表演者左侧，`front` 指身体正前方。 | 若髋肩关键点缺失导致朝向轴无法解算，相关投影原语返回 `U`（`UNKNOWN`）。 |

## 3. H36M-17 关节枚举与派生对象

### 3.1 H36M-17 原始关节（17 个闭合枚举）
`root`(0), `right_hip`(1), `right_knee`(2), `right_ankle`(3), `left_hip`(4), `left_knee`(5), `left_ankle`(6), `belly`(7), `neck`(8), `nose`(9), `head`(10), `left_shoulder`(11), `left_elbow`(12), `left_wrist`(13), `right_shoulder`(14), `right_elbow`(15), `right_wrist`(16)。

### 3.2 派生对象
* **几何派生（`proxy=false`）**：`hip_center = (left_hip + right_hip)/2`、`shoulder_center = (left_shoulder + right_shoulder)/2`、`body_axis = hip_center -> shoulder_center`、`pelvis_heading`。
* **生物力学代理（`proxy=true`）**：`foot_len_est`（双侧小腿长均值 × `0.68`）、`com_est`（分段质量加权重心）、`support_side`（主承重侧 `left/right/both`）。

## 4. 原语算子库（Primitives Specification）

> **与原版 DSL 完全对齐**：保留 `KNEE_LIFT_HEIGHT(side)` 相对**同侧髋**高度、`BALANCE_STILL()` 逐帧布尔静止判定、`HOLD(cond, duration)` 时序保持算子；同时补充竞赛规则表-8/表-11 必需的难度与跳跃算子。

### 4.1 三维骨骼几何、步型与运动学原语

| 类别 | 原语签名 | 返回单位 | 严格定义与对应规则编码 |
| :--- | :--- | :--- | :--- |
| **位置/距离** | `POS(object, axis)` | `norm` | 对象在 `up / left / front` 轴上的坐标 |
| **位置/距离** | `DIST(a, b)` / `HORIZONTAL_DIST(a, b)` | `norm` | 三维欧氏距离 / 水平面投影距离（正踢腿脚触前额 `DIST(right_ankle, head)`） |
| **高度** | `HEIGHT(object)` | `norm` | 对象在地面世界坐标系 `W` 中的垂直高度 |
| **高度** | `KNEE_LIFT_HEIGHT(side)` | `norm` | `HEIGHT(side.knee) - HEIGHT(side.hip)`；**严格对齐原版 DSL：膝相对同侧髋高度**（编码 `03` 提膝未过腰） |
| **高度** | `ANKLE_REL_HEIGHT(side, ref)` | `norm` | `HEIGHT(side.ankle) - HEIGHT(ref)`，`ref` 取 `shoulder_center / hip_center / belly / head`（编码 `50/60/61/70`，`proxy=true`） |
| **时序位移** | `DISPLACEMENT(object, axis)` | `norm` | 窗口末帧减首帧在 `W` 系下沿初始 `axis` 轴的净位移 |
| **时序位移** | `MAX_DRIFT(object)` | `norm` | 窗口内对象在水平面偏离首帧位置的最大距离（编码 `82` 支撑脚移动粗筛） |
| **运动学** | `SPEED(object)` | `norm/frame` | 相邻帧在 `W` 系下的三维速度幅值 |
| **跳跃辅助** | `STEP_COUNT()` | `count` | 助跑阶段双踝交替迈步次数（表-11 腾空飞脚/正踢腿助跑超 1 步，`proxy=true`） |
| **跳跃辅助** | `LANDING_TIME_DIFF()` | `ms` | 跳跃接跌叉落地阶段双腿触地时间差（表-11 两腿依次落地，`proxy=true`） |
| **关节角度** | `KNEE_ANGLE(side)` / `KNEE_BEND(side)` | `deg` | 膝角（直腿 `180deg`） / 屈膝角 `180deg - KNEE_ANGLE(side)`（直腿 `0deg`，覆盖 `12/14/60/61/71`） |
| **难度深度** | `THIGH_VERTICAL_ANGLE(side)` | `deg` | 大腿向量 `side.hip -> side.knee` 与竖直向上轴 `+up` 夹角（直立 `180deg`，水平蹲平 `90deg`；表-11 弓马步 `>115deg`、虚步 `>135deg`） |
| **关节角度** | `THIGH_SPLIT_ANGLE()` | `deg` | `ANGLE(left_knee, hip_center, right_knee)` 两大腿展开夹角（编码 `01` 跌叉 `<=45deg`） |
| **身型/上肢** | `TRUNK_TILT(axis)` / `SPINE_BEND()` | `deg` | 躯干倾角 / `180deg - ANGLE(hip_center, belly, neck)` 弓背角（编码 `16`） |
| **身型/上肢** | `HIP_ANGLE(side)` / `ELBOW_ANGLE(side)` | `deg` | `ANGLE(belly, side.hip, side.knee)` 髋角（编码 `16`） / 肘角（编码 `17` 直臂） |
| **身型/上肢** | `SHOULDER_SHRUG(side)` / `ELBOW_RAISE(side)` | `norm` | `HEIGHT(side.shoulder) - HEIGHT(neck)` 耸肩 / `HEIGHT(side.elbow) - HEIGHT(side.wrist)` 抬肘（编码 `17`） |
| **转体角度** | `YAW_ROTATION(target)` | `deg` | 窗口内 `pelvis` 或 `support_ankle` 在水平面累计旋转角绝对值（跳跃转体 `180..540deg`，`proxy=true`） |
| **站距/偏移** | `STANCE_WIDTH()` / `STANCE_FOOT_RATIO()` | `norm` / `ratio` | 双踝水平间距 / `STANCE_WIDTH / foot_len_est`（编码 `13` 马步过宽 `>3.5 ratio`，`proxy=true`） |
| **站距/偏移** | `KNEE_FORWARD_OFFSET(side)` / `KNEE_MEDIAL_OFFSET(side)` | `norm` | 膝相对同侧踝前冲投影 / 膝向中线内扣偏移（`proxy=true`） |
| **平衡/失稳** | `SWAY_ANGLE()` | `deg` | 支撑期躯干在竖直面往返摆动最大角位移（`<=45deg` 小晃动 `80`，`>45deg` 大晃动 `81`） |
| **平衡/失稳** | `BALANCE_STILL()` | `bool` | 逐帧判定全身是否处于静止平衡态（配合 `NOT HOLD(BALANCE_STILL() == true, 2000ms)` 判定编码 `87`） |
| **平衡/失稳** | `BALANCE_STILL_MS()` | `ms` | 平衡窗口内自首次静止起连续保持的毫秒数（`HOLD` 算子的等价数值语法糖） |
| **平衡/失稳** | `FALL_SUSPECTED()` | `bool` | 重心骤降且躯干大倾角失稳（编码 `84` 倒地粗筛，`proxy=true`） |

### 4.2 按需图像视觉原语（`V_*`，仅在骨骼无法独立判定时唤醒）

| 原语签名 | 返回单位 / 类型 | 视觉语义与对应规则编码 |
| :--- | :--- | :--- |
| `V_HAND_FORM(side)` | `label` (`palm/fist/hook/other`) | 手型分类（编码 `10/11`） |
| `V_HAND_DEFECT(side)` | `label` (`uneven_fist/finger_gap/bent_finger/convex_palm/none`) | 拳面不平 `10`、指间过宽/指弯/掌心外凸 `11` |
| `V_FOOT_SLAP_HIT(side)` | `bool` | 摆莲/拍脚/飞脚/旋风脚手掌是否准确击中脚面（编码 `61/70`） |
| `V_FOOT_OUTTURN(side)` | `deg` | 脚尖相对身体前进方向有符号水平夹角：正为外展，负为内扣（编码 `01/14`） |
| `V_KNEE_OVER_TOE(side)` | `bool` | 膝前端水平投影是否明显超过同侧脚尖（编码 `12`） |
| `V_KNEE_TOE_ALIGNED(side)` | `bool` | 支撑膝弯曲方向与同侧脚尖朝向是否对正（编码 `15/18`） |
| `V_HEEL_LIFT(side)` | `bool` | 脚跟是否明显离地拔跟（`true` 触发弓步后跟离地 `12`；`false` 触发虚步前跟着地 `15`） |
| `V_FULL_FOOT_GROUNDED(side)` | `bool` | 全脚掌是否完整贴地（`false` 触发仆步未全脚掌着地 `14`） |
| `V_FOOT_SLIDE(side)` / `V_FOOT_PIVOT(side)` | `bool` | 支撑期脚掌平移滑动 / 脚底碾转（编码 `82` 及连接难度落地碾动） |
| `V_FOOT_RECOVERY_STEP(side)` / `V_FOOT_SKIP(side)` | `bool` | 单脚失稳提前落脚迈步（`82`） / 失去平衡跳动（`83`） |
| `V_GROUND_CONTACT(part)` / `V_UNEXPECTED_SUPPORT(part)` | `bool` | 指定部位触地（`01/51/84`） / 失衡附加支撑借力（`83`） |
| `V_OUT_OF_BOUNDS()` | `bool` | 身体触及场地线外地面（编码 `88`） |
| `V_FOOT_ROTATION(side)` | `deg` | 起跳至落地瞬间脚尖-脚跟连线的水平转体度数（表-11 跳跃旋转度数） |

## 5. 内层微公式语法（Micro-DSL EBNF）与四值克林逻辑（$\mathcal{L}_4$）

### 5.1 内层微公式 EBNF 语法
每条表达式字符串格式为 `"@<item_id>: <BoolExpr>"`，其中 `<item_id>` 唯一标识该原子违规原因：

```ebnf
TaggedExpr ::= "@" Identifier ":" BoolExpr
BoolExpr   ::= OrExpr
OrExpr     ::= AndExpr ( "OR" AndExpr )*
AndExpr    ::= NotExpr ( "AND" NotExpr )*
NotExpr    ::= "NOT" NotExpr | Primary
Primary    ::= "(" BoolExpr ")" | HoldExpr | Comparison
HoldExpr   ::= "HOLD" "(" BoolExpr "," DurationLit ")"
Comparison ::= CallExpr CompOp ValueLit
             | CallExpr "BETWEEN" "[" NumLit "," NumLit "]"
             | CallExpr "IN" "[" LabelLit ("," LabelLit)* "]"
```

### 5.2 扩展强克林四值逻辑（Strong Kleene $\mathcal{L}_4$）与骨骼优先短路求值
每个子表达式返回四值集合 $\mathcal{L}_4 = \{\mathbf{T}, \mathbf{F}, \mathbf{V}, \mathbf{U}\}$（$\mathbf{T}$=确认违规，`VIOLATION`；$\mathbf{F}$=确认合规，`PASS`；$\mathbf{V}$=待唤醒视觉，`NEEDS_VISION`；$\mathbf{U}$=不可恢复缺失，`UNKNOWN`）：

1. **取反 `NOT`（$\neg$）**：$\neg \mathbf{T} = \mathbf{F},\; \neg \mathbf{F} = \mathbf{T},\; \neg \mathbf{V} = \mathbf{V},\; \neg \mathbf{U} = \mathbf{U}$。
2. **合取 `AND`（`ALL`, $\land$）**：$\mathbf{F}$ 为绝对零元（任一条件为 $\mathbf{F}$ 直接短路返回 `PASS`）；无 $\mathbf{F}$ 时 **$\mathbf{U}$ 吸收 $\mathbf{V}$**（已有必需条件永久未知 $\mathbf{U}$，不再发起无效视觉请求，直接返回 `UNKNOWN`）。
3. **析取 `OR`（`ANY`, $\lor$）**：$\mathbf{T}$ 为绝对零元（任一骨骼条件为 $\mathbf{T}$ 直接短路返回 `VIOLATION`，免除视觉调用）；无 $\mathbf{T}$ 时 **$\mathbf{V}$ 吸收 $\mathbf{U}$**（只要仍有视觉分支有望测出违规，优先返回 `NEEDS_VISION`）。
4. **时序保持 `HOLD(cond, duration)`**：在窗口内滑动检测连续满足 `cond == T` 的最长时长 $d_{\max}$：若 $d_{\max} \ge \text{duration}$ 返回 $\mathbf{T}$；若即使将所有 $\mathbf{V}/\mathbf{U}$ 帧视为 $\mathbf{T}$ 仍不足 `duration` 返回 $\mathbf{F}$；否则含 $\mathbf{V}$ 返回 $\mathbf{V}$，含 $\mathbf{U}$ 返回 $\mathbf{U}$。

## 6. 扣分编码注册表与两级去重聚合规则

### 6.1 权威扣分编码表（32 项，严格核对 `(code, group, points, scope)`）

| 编码 (`code`) | 组别 | 分值 | 作用域 (`scope`) | 扣分含义 |
| :--- | :--- | :--- | :--- | :--- |
| `10` / `11` | `E` | `0.10` | `technique` | 拳型错误（拳面不平） / 掌型错误（指间过宽、指弯、掌心外凸） |
| `12` / `13` | `E` | `0.10` | `technique` | 弓步错误（前膝过脚尖/后腿弯/拔跟） / 马步错误（横向间距 `>3.5` 倍脚长） |
| `14` / `15` | `E` | `0.10` | `technique` | 仆步错误（仆腿弯/未内扣全脚掌着地） / 虚步错误（膝与脚尖未对正/前跟着地） |
| `16` / `17` / `18` | `E` | `0.10` | `technique` | 身型错误（翻臀弓背/伸髋后仰） / 手法错误（直臂/耸肩/抬肘） / 上步错误 |
| `01` / `03` | `E` | `0.10` | `technique` | 跌叉错误（前脚掌内扣触地/夹角 `<=45deg`） / 提膝独立错误（膝未过腰） |
| `50` / `51` | `E` | `0.10` | `technique` | 前举腿平衡低于水平 / 后插腿平衡脚触地 |
| `60` / `61` | `E` | `0.10` | `technique` | 蹬脚分脚错误（支撑腿弯/上举腿弯） / 摆莲拍脚错误（摆腿弯/击拍落空/脚低于肩） |
| `70` / `71` | `E` | `0.10` | `technique` | 飞脚/旋风脚/腾空摆莲（击拍落空/未过肩） / 腾空正踢腿（悬垂腿弯曲） |
| `80` / `81` | `E` | `0.10` / `0.20` | `event` | 小晃动（`<=45deg`） / 大晃动（`>45deg`） |
| `82` / `83` / `84` | `E` | `0.10` / `0.20` / `0.30` | `event` | 脚碾动或移动 / 跳动或附加支撑 / 倒地 |
| `87` / `88` / `89` | `E` | `0.10` | `event` | 平衡静止不足 `2000ms` / 出界 / 遗忘 |
| `D_STANCE_115` / `135` | `D` | `0.10` | `technique` | 弓马步大腿与垂直轴夹角 `>115deg` / 虚步上步大腿与垂直轴夹角 `>135deg` |
| `D_SQUAT_INCOMPLETE` | `D` | `0.10` | `technique` | 仆步/前举腿低势平衡屈蹲腿未全蹲 |
| `D_BALANCE_51` / `D_KICK_LOW` | `D` | `0.15` / `0.10` | `technique` | 后插腿平衡支撑腿高于水平 / 蹬分摆莲脚低于肩 |
| `D_JUMP_CD` / `D_JUMP_EFG` | `D` | `0.15` / `0.20` | `technique` | C/D 级跳跃难度未完成 / E/F/G 级跳跃难度未完成 |

### 6.2 章节聚合去重算法（Aggregator Policy）
1. **单式技术错误去重（`scope == "technique"`）**：同一动作实例（`chapter_instance_id`）内，触发同一 `code` 的多条子项（如左弓步和右弓步均触发 `12`，或同一弓步同时触发后腿弯与拔跟），仅首条生效扣分（`effective_deduction_points = points, counted_events = 1`），后续同编码违规全部标记 `effective_deduction_points = 0.0, deduplicated_by = <first_event_id>`。支持切换 `aggregation_policy = "per_code" | "strict_single_spec_cap"`（后者将单式内所有 E 组规格错误总和封顶为 `0.10` 分，严格对应《规则》第 34.1.1 条）。
2. **动态失衡事件去重（`scope == "event"`）**：编码 `80~89` 按时间窗口聚类，若帧区间重叠或间隔 `< 12 frames`，合并为同一物理失衡事件并取最高分值（如同时触发 `80` 与 `81` 仅扣 `0.20` 分）；若间隔 `>= 12 frames`，按《规则》第 34.2.6 条累计扣分。

## 7. 输入规则与输出报告扁平 JSON 结构规范

### 7.1 输入规则 JSON 结构（`RuleNode`）
* `rule_id`: 章节内唯一英文标识符。
* `phase` & `frame_window`: 动作阶段名与闭区间 `[start_frame, end_frame]`。
* `stance`: 步型绑定对象 `{"front": "left|right|none", "rear": "left|right|none", "support": "left|right|both|airborne"}`。
* `logic` & `expr`: 外层组合逻辑（`"ANY"` 或 `"ALL"`）与带 `@item_id:` 前缀的微公式数组。若规则在 H36M-17 + 单目视觉下仍不可判定（如脚趾抓地），设 `"unresolvable": true, "expr": []`。
* `deduction`: `{"code": "...", "points": 0.10, "group": "E|D", "scope": "technique|event"}`。
* `vision_fallback`: 仅当 `expr` 含 `V_*` 原语时必填，含 `target_parts`、`frame_window`、`instruction`。
* `unknown_reason`: 数据缺失或遮挡时的诊断说明。

### 7.2 输出评估报告 JSON 结构（`ChapterEvalReport` & `RuleEvalResult`）
* 每条 `RuleEvalResult` 包含：`rule_id`, `chapter_instance_id`, `phase`, `frame_range`, `result`（`VIOLATION / PASS / NEEDS_VISION / UNKNOWN / UNRESOLVABLE`）, `triggered_items`（命中的 `@item_id` 列表）, `item_traces`（每个 `@item_id` 的实测值 `actual_values`、数据源与四值状态 `T/F/V/U`）, `raw_deduction_points`, `effective_deduction_points`, `counted_events`, `deduplicated_by`。

## 8. 强类型 Pydantic v2 Schema 与内联微公式校验器

```python
import re
from typing import Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

DeductionCodeLiteral = Literal[
    "10", "11", "12", "13", "14", "15", "16", "17", "18",
    "01", "03", "50", "51", "60", "61", "70", "71",
    "80", "81", "82", "83", "84", "87", "88", "89",
    "D_STANCE_115", "D_STANCE_135", "D_SQUAT_INCOMPLETE",
    "D_BALANCE_51", "D_KICK_LOW", "D_JUMP_CD", "D_JUMP_EFG"
]

DEDUCTION_REGISTRY: Dict[str, Tuple[str, float, str]] = {
    "10": ("E", 0.10, "technique"), "11": ("E", 0.10, "technique"),
    "12": ("E", 0.10, "technique"), "13": ("E", 0.10, "technique"),
    "14": ("E", 0.10, "technique"), "15": ("E", 0.10, "technique"),
    "16": ("E", 0.10, "technique"), "17": ("E", 0.10, "technique"),
    "18": ("E", 0.10, "technique"), "01": ("E", 0.10, "technique"),
    "03": ("E", 0.10, "technique"), "50": ("E", 0.10, "technique"),
    "51": ("E", 0.10, "technique"), "60": ("E", 0.10, "technique"),
    "61": ("E", 0.10, "technique"), "70": ("E", 0.10, "technique"),
    "71": ("E", 0.10, "technique"), "80": ("E", 0.10, "event"),
    "81": ("E", 0.20, "event"),     "82": ("E", 0.10, "event"),
    "83": ("E", 0.20, "event"),     "84": ("E", 0.30, "event"),
    "87": ("E", 0.10, "event"),     "88": ("E", 0.10, "event"),
    "89": ("E", 0.10, "event"),
    "D_STANCE_115": ("D", 0.10, "technique"),
    "D_STANCE_135": ("D", 0.10, "technique"),
    "D_SQUAT_INCOMPLETE": ("D", 0.10, "technique"),
    "D_BALANCE_51": ("D", 0.15, "technique"),
    "D_KICK_LOW": ("D", 0.10, "technique"),
    "D_JUMP_CD": ("D", 0.15, "technique"),
    "D_JUMP_EFG": ("D", 0.20, "technique"),
}

PRIMITIVE_SIGNATURES: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "POS": (("object", "axis"), "norm"),
    "DIST": (("object", "object"), "norm"),
    "HORIZONTAL_DIST": (("object", "object"), "norm"),
    "HEIGHT": (("object",), "norm"),
    "KNEE_LIFT_HEIGHT": (("side",), "norm"),
    "ANKLE_REL_HEIGHT": (("side", "ref"), "norm"),
    "DISPLACEMENT": (("object", "axis"), "norm"),
    "MAX_DRIFT": (("object",), "norm"),
    "SPEED": (("object",), "norm/frame"),
    "STEP_COUNT": ((), "count"),
    "LANDING_TIME_DIFF": ((), "ms"),
    "KNEE_ANGLE": (("side",), "deg"),
    "KNEE_BEND": (("side",), "deg"),
    "THIGH_VERTICAL_ANGLE": (("side",), "deg"),
    "THIGH_SPLIT_ANGLE": ((), "deg"),
    "TRUNK_TILT": (("axis",), "deg"),
    "SPINE_BEND": ((), "deg"),
    "HIP_ANGLE": (("side",), "deg"),
    "ELBOW_ANGLE": (("side",), "deg"),
    "SHOULDER_SHRUG": (("side",), "norm"),
    "ELBOW_RAISE": (("side",), "norm"),
    "YAW_ROTATION": (("yaw_target",), "deg"),
    "STANCE_WIDTH": ((), "norm"),
    "STANCE_FOOT_RATIO": ((), "ratio"),
    "KNEE_FORWARD_OFFSET": (("side",), "norm"),
    "KNEE_MEDIAL_OFFSET": (("side",), "norm"),
    "SWAY_ANGLE": ((), "deg"),
    "BALANCE_STILL": ((), "bool"),
    "BALANCE_STILL_MS": ((), "ms"),
    "FALL_SUSPECTED": ((), "bool"),
    "V_HAND_FORM": (("side",), "label"),
    "V_HAND_DEFECT": (("side",), "label"),
    "V_FOOT_SLAP_HIT": (("side",), "bool"),
    "V_FOOT_OUTTURN": (("side",), "deg"),
    "V_KNEE_OVER_TOE": (("side",), "bool"),
    "V_KNEE_TOE_ALIGNED": (("side",), "bool"),
    "V_HEEL_LIFT": (("side",), "bool"),
    "V_FULL_FOOT_GROUNDED": (("side",), "bool"),
    "V_FOOT_SLIDE": (("side",), "bool"),
    "V_FOOT_PIVOT": (("side",), "bool"),
    "V_FOOT_RECOVERY_STEP": (("side",), "bool"),
    "V_FOOT_SKIP": (("side",), "bool"),
    "V_GROUND_CONTACT": (("vpart",), "bool"),
    "V_UNEXPECTED_SUPPORT": (("vpart",), "bool"),
    "V_OUT_OF_BOUNDS": ((), "bool"),
    "V_FOOT_ROTATION": (("side",), "deg"),
}

VALID_DOMAINS: Dict[str, set] = {
    "side": {"left", "right", "front", "rear"},
    "axis": {"up", "left", "front"},
    "ref": {"shoulder_center", "hip_center", "belly", "head"},
    "yaw_target": {"pelvis", "support_ankle"},
    "object": {
        "root", "right_hip", "right_knee", "right_ankle", "left_hip", "left_knee", "left_ankle",
        "belly", "neck", "nose", "head", "left_shoulder", "left_elbow", "left_wrist",
        "right_shoulder", "right_elbow", "right_wrist", "hip_center", "shoulder_center", "com_est"
    },
    "vpart": {
        "left_hand", "right_hand", "left_elbow", "right_elbow", "left_shoulder", "right_shoulder",
        "left_knee", "right_knee", "front_knee", "rear_knee", "left_foot", "right_foot",
        "front_foot", "rear_foot", "left_heel", "right_heel", "front_heel", "rear_heel",
        "left_toe", "right_toe", "front_toe", "rear_toe", "head", "back", "hip"
    },
}

TAGGED_EXPR_RE = re.compile(r"^@([a-z][a-z0-9_]*)\s*:\s*(.+)$")
CALL_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)\s*\(([^()]*)\)")

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class StanceSpec(StrictModel):
    front: Literal["left", "right", "none"]
    rear: Literal["left", "right", "none"]
    support: Literal["left", "right", "both", "airborne"]

    @model_validator(mode="after")
    def validate_stance(self) -> "StanceSpec":
        if (self.front == "none") != (self.rear == "none"):
            raise ValueError("front 与 rear 必须同时为 'none'，或分别为 'left' 和 'right'")
        if self.front != "none" and self.front == self.rear:
            raise ValueError(f"front 与 rear 不能同为 '{self.front}'")
        if self.support == "airborne" and self.front != "none":
            raise ValueError("support='airborne' 时 front 和 rear 必须为 'none'")
        return self

class DeductionSpec(StrictModel):
    code: DeductionCodeLiteral
    points: Literal[0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    group: Literal["E", "D"]
    scope: Literal["technique", "event"]

    @model_validator(mode="after")
    def validate_registry(self) -> "DeductionSpec":
        exp_g, exp_p, exp_s = DEDUCTION_REGISTRY[self.code]
        if (self.group, self.points, self.scope) != (exp_g, exp_p, exp_s):
            raise ValueError(f"编码 {self.code} 必须匹配 group={exp_g}, points={exp_p}, scope={exp_s}")
        return self

class VisionFallbackSpec(StrictModel):
    target_parts: List[str] = Field(min_length=1)
    frame_window: List[StrictInt] = Field(min_length=2, max_length=2)
    instruction: str = Field(min_length=5)

    @model_validator(mode="after")
    def validate_parts(self) -> "VisionFallbackSpec":
        for p in self.target_parts:
            if p not in VALID_DOMAINS["vpart"]:
                raise ValueError(f"非法视觉目标部位: {p}")
        return self

class RuleNode(StrictModel):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    phase: str = Field(min_length=1)
    frame_window: List[StrictInt] = Field(min_length=2, max_length=2)
    stance: StanceSpec
    unresolvable: bool = False
    logic: Literal["ANY", "ALL"] = "ANY"
    expr: List[str] = Field(default_factory=list)
    deduction: DeductionSpec
    vision_fallback: Optional[VisionFallbackSpec] = None
    unknown_reason: str = Field(min_length=8)

    @model_validator(mode="after")
    def validate_rule_and_micro_dsl(self) -> "RuleNode":
        if self.frame_window[0] < 0 or self.frame_window[0] > self.frame_window[1]:
            raise ValueError(f"非法 frame_window: {self.frame_window}")
        if self.unresolvable:
            if self.expr:
                raise ValueError("unresolvable=True 的规则 expr 必须为空列表")
            return self
        if not self.expr:
            raise ValueError("可执行规则的 expr 不能为空")

        uses_vision = False
        uses_front_rear = False
        for line in self.expr:
            m = TAGGED_EXPR_RE.match(line.strip())
            if not m:
                raise ValueError(f"表达式必须以 '@item_id: 公式' 格式书写: {line}")
            _, formula = m.groups()
            for prim, raw_args in CALL_RE.findall(formula):
                if prim == "HOLD":
                    continue
                if prim not in PRIMITIVE_SIGNATURES:
                    raise ValueError(f"未知原语算子: {prim}")
                if prim.startswith("V_"):
                    uses_vision = True
                arg_list = [a.strip() for a in raw_args.split(",") if a.strip()]
                exp_domains, _ = PRIMITIVE_SIGNATURES[prim]
                if len(arg_list) != len(exp_domains):
                    raise ValueError(f"{prim} 参数数量错误: 期望 {len(exp_domains)} 个，实际 {len(arg_list)} 个")
                for arg_val, dom in zip(arg_list, exp_domains):
                    if arg_val not in VALID_DOMAINS[dom]:
                        raise ValueError(f"{prim} 的参数 '{arg_val}' 不在合法枚举域 {dom} 中")
                    if arg_val in ("front", "rear") or arg_val.startswith(("front_", "rear_")):
                        uses_front_rear = True

        if uses_front_rear and self.stance.front == "none":
            raise ValueError(f"规则 {self.rule_id} 使用了 front/rear，但 stance 未绑定前后腿")
        if uses_vision and self.vision_fallback is None:
            raise ValueError(f"规则 {self.rule_id} 含有 V_* 视觉原语，必须配置 vision_fallback")
        if self.vision_fallback and self.vision_fallback.frame_window != self.frame_window:
            raise ValueError("vision_fallback.frame_window 必须与规则 frame_window 一致")
        return self

class InputSpec(StrictModel):
    skeleton: Literal["h36m-17"] = "h36m-17"
    fps: StrictInt = Field(gt=0)
    vision_mode: Literal["demand_driven", "full"] = "demand_driven"

class ChapterSpec(StrictModel):
    chapter_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    action_name: str = Field(min_length=1)
    action_code: str = Field(min_length=1)

class RootSpec(StrictModel):
    dsl_version: Literal["H36M17-TAICHI-HYBRID-3.0"] = "H36M17-TAICHI-HYBRID-3.0"
    input_spec: InputSpec
    chapter: ChapterSpec
    rules: List[RuleNode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_uniqueness(self) -> "RootSpec":
        rule_ids = [r.rule_id for r in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("章节内 rule_id 必须唯一")
        all_items: List[str] = []
        for r in self.rules:
            for line in r.expr:
                item_id = TAGGED_EXPR_RE.match(line.strip()).group(1)
                all_items.append(item_id)
        if len(all_items) != len(set(all_items)):
            raise ValueError("章节内所有 @item_id 必须全局唯一")
        return self
```