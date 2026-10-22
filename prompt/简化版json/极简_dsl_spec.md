# H36M-17 太极拳动作规约语言：核心语法规范（极简扁平 Clause 规范版 v2.3）

> 本规范针对徒手太极拳竞赛规则（剔除器械条款），采用对大模型受限解码（`Structured Outputs`）最友好的**“极简扁平 `primitive + args + op + target + unit` 五元组”**架构。所有时序积分（如 2 秒静止保持、最大水平漂移）均内聚于底层原语算子，所有复合原因均通过原子规则拆分与章节聚合层去重实现，从而实现 **0 递归套娃、100% 枚举锁死、0 语法报错**。

## 1. 为什么采用极简 `primitive + args + op + target` 架构？

1. **Token 级枚举锁死（零幻觉与零拼写错误）**：`primitive`、`args`、`op`、`unit` 全部为闭合 `Literal` 枚举。开启大模型 `Structured Outputs` 时，解码器在每个 Token 位置直接掩码非法选项，从物理上杜绝拼写错误和自造原语。
2. **三大降维机制消除复杂语法树**：
   * **时序算子内聚化**：用数值原语 `BALANCE_STILL_MS < 2000` 替代复杂的 `NOT HOLD(BALANCE_STILL() == true, 2000ms)`。
   * **取反逻辑算符化**：用逆向比较符（`== false`、`!=`、`<=`）直接吸收 `NOT`，无需独立的 `NOT` 语法树节点。
   * **原子规则拆分 + 聚合层去重**：每个具体违规原因拆分为独立的原子 `RuleNode`（或单层 `ALL/ANY` 列表），共用同一扣分编码 `code`，由章节聚合器自动去重计分。

## 2. 双坐标系与输入标定协议（Calibration Protocol）

每帧输入为 MotionBERT 产出的 `P[frame][joint][x,y,z]`（`h36m-17` 拓扑），三维长度单位为身高归一化 `norm`，角度为 `deg`，比例为 `ratio`，时间为 `frame` 或 `ms`。

| 坐标系名称 | 符号 | 标定方法与适用原语 | 标定失败降级策略 |
| :--- | :--- | :--- | :--- |
| **地面世界坐标系** | `W` | 以起势直立帧标定真实重力反方向为 `+up`（消除相机俯仰角），以非腾空期支撑踝最低包络面锚定 `up = 0` 水平地面。所有**绝对高度**（`HEIGHT`）、**支撑期水平漂移**（`MAX_DRIFT`）、**净位移**（`DISPLACEMENT`）及**水平累计转角**（`YAW_ROTATION`）均在 `W` 下计算。 | 若相机剧烈运动或地面拟合残差超标，依赖 `W` 的原语统一返回状态 `U`（`UNKNOWN`）。 |
| **解剖学朝向坐标系** | `B` | 由骨盆与双肩水平投影确定表演者瞬时或阶段朝向：`up` 竖直向上，`left` 指表演者左侧，`front` 指身体正前方。 | 若髋肩关键点缺失导致朝向轴无法解算，相关投影原语返回 `U`（`UNKNOWN`）。 |

## 3. H36M-17 关节枚举与派生对象

### 3.1 H36M-17 原始关节对象（17 个闭合枚举）

| 对象名 | 下标 | 含义 | 对象名 | 下标 | 含义 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `root` | 0 | 骨盆根节点 | `nose` | 9 | 鼻部（面部朝向与前额代理） |
| `right_hip` | 1 | 右髋 | `head` | 10 | 头部顶点 |
| `right_knee` | 2 | 右膝 | `left_shoulder` | 11 | 左肩 |
| `right_ankle` | 3 | 右踝 | `left_elbow` | 12 | 左肘 |
| `left_hip` | 4 | 左髋 | `left_wrist` | 13 | 左腕 |
| `left_knee` | 5 | 左膝 | `right_shoulder` | 14 | 右肩 |
| `left_ankle` | 6 | 左踝 | `right_elbow` | 15 | 右肘 |
| `belly` | 7 | 腹部/腰部基准点 | `right_wrist` | 16 | 右腕 |
| `neck` | 8 | 颈部基点 | | | |

### 3.2 派生对象
* **几何派生（`proxy=false`）**：`hip_center = (left_hip + right_hip) / 2`、`shoulder_center = (left_shoulder + right_shoulder) / 2`、`body_axis = hip_center -> shoulder_center`、`pelvis_heading`。
* **生物力学代理（`proxy=true`）**：`foot_len_est`（双侧小腿长均值 × `0.68`）、`com_est`（分段质量加权重心）、`support_side`（主承重侧 `left/right/both`）。

## 4. 原语算子库（Primitives Specification）

### 4.1 三维骨骼几何、步型、角度与时序原语

| 原语名称 (`primitive`) | 参数结构 (`args`) | 返回单位 (`unit`) | 严格定义与对应规则场景 |
| :--- | :--- | :--- | :--- |
| `POS` | `{object, axis}` | `norm` | 对象在 `up/left/front` 轴上的坐标 |
| `DIST` / `HORIZONTAL_DIST` | `{a, b}` | `norm` | 三维欧氏距离 / 水平面投影距离（正踢腿脚触前额 `DIST(right_ankle, head)`） |
| `HEIGHT` | `{object}` | `norm` | 对象在地面世界坐标系 `W` 中的垂直高度 |
| `KNEE_LIFT_HEIGHT` | `{side}` | `norm` | `HEIGHT(side.knee) - HEIGHT(side.hip)`；**严格对齐原版 DSL：膝相对同侧髋高度**（覆盖编码 `03` 提膝未过腰） |
| `ANKLE_REL_HEIGHT` | `{side, ref}` | `norm` | `HEIGHT(side.ankle) - HEIGHT(ref)`；`ref` 取 `shoulder_center / hip_center / belly / head`（覆盖编码 `50/60/61/70`，`proxy=true`） |
| `DISPLACEMENT` | `{object, axis}` | `norm` | 阶段窗口末帧减首帧在 `W` 系下沿初始 `axis` 轴的净位移 |
| `MAX_DRIFT` | `{object}` | `norm` | 阶段窗口内对象在水平面偏离首帧位置的最大欧氏距离（支撑脚移动粗筛 `82`） |
| `SPEED` | `{object}` | `norm/frame` | 相邻帧在 `W` 系下的三维速度幅值 |
| `STEP_COUNT` | `{}` | `count` | 助跑阶段双踝交替迈步次数（腾空飞脚/正踢腿助跑超 1 步，`proxy=true`） |
| `LANDING_TIME_DIFF` | `{}` | `ms` | 跳跃接跌叉落地阶段左右腿首次触地时间差（两腿依次落地，`proxy=true`） |
| `KNEE_ANGLE` / `KNEE_BEND` | `{side}` | `deg` | 膝角（直腿 `180deg`） / 屈膝角 `180deg - KNEE_ANGLE(side)`（直腿 `0deg`，覆盖 `12/14/60/61/71`） |
| `THIGH_VERTICAL_ANGLE` | `{side}` | `deg` | 大腿向量 `side.hip -> side.knee` 与 `+up` 夹角（直立 `180deg`，蹲平 `90deg`；表-11 弓马步 `>115deg`、虚步 `>135deg`） |
| `THIGH_SPLIT_ANGLE` | `{}` | `deg` | `ANGLE(left_knee, hip_center, right_knee)` 两大腿展开夹角（编码 `01` 跌叉 `<=45deg`） |
| `TRUNK_TILT` / `SPINE_BEND` | `{axis}` / `{}` | `deg` | 躯干倾角 / `180deg - ANGLE(hip_center, belly, neck)` 弓背角（编码 `16`） |
| `HIP_ANGLE` / `ELBOW_ANGLE` | `{side}` | `deg` | `ANGLE(belly, side.hip, side.knee)` 髋角（编码 `16`） / 肘角（编码 `17` 直臂） |
| `SHOULDER_SHRUG` / `ELBOW_RAISE` | `{side}` | `norm` | `HEIGHT(side.shoulder) - HEIGHT(neck)` 耸肩 / `HEIGHT(side.elbow) - HEIGHT(side.wrist)` 抬肘（编码 `17`） |
| `YAW_ROTATION` | `{target}` | `deg` | 窗口内 `pelvis` 或 `support_ankle` 水平面累计旋转角绝对值（跳跃转体 `180..540deg`，`proxy=true`） |
| `STANCE_WIDTH` / `STANCE_FOOT_RATIO` | `{}` | `norm` / `ratio` | 双踝水平间距 / `STANCE_WIDTH / foot_len_est`（编码 `13` 马步过宽 `>3.5 ratio`，`proxy=true`） |
| `KNEE_FORWARD_OFFSET` / `KNEE_MEDIAL_OFFSET` | `{side}` | `norm` | 膝相对同侧踝前冲投影 / 膝向中线内扣偏移（`proxy=true`） |
| `SWAY_ANGLE` | `{}` | `deg` | 支撑期躯干在竖直面往返摆动最大角位移（`<=45deg` 小晃动 `80`，`>45deg` 大晃动 `81`） |
| `BALANCE_STILL_MS` | `{}` | `ms` | 平衡窗口内自首次静止起连续保持静止的毫秒时长（内聚 `HOLD` 逻辑，覆盖编码 `87` `<2000ms`） |
| `FALL_SUSPECTED` | `{}` | `bool` | 重心骤降且躯干大倾角失稳（编码 `84` 倒地粗筛，`proxy=true`） |

### 4.2 按需图像视觉原语（`V_*`，仅在骨骼无法独立判定时唤醒）

| 原语名称 (`primitive`) | 参数结构 (`args`) | 返回单位 (`unit`) | 目标值类型 (`target`) | 视觉语义与对应规则编码 |
| :--- | :--- | :--- | :--- | :--- |
| `V_HAND_FORM` | `{side}` | `label` | `palm / fist / hook / other` | 手型分类（编码 `10/11`） |
| `V_HAND_DEFECT` | `{side}` | `label` | `uneven_fist / finger_gap / bent_finger / convex_palm / none` | 拳面不平 `10`、指间过宽/指弯/掌心外凸 `11` |
| `V_FOOT_SLAP_HIT` | `{side}` | `bool` | `true / false` | 摆莲/拍脚/飞脚/旋风脚手掌是否准确击中脚面（编码 `61/70`） |
| `V_FOOT_OUTTURN` | `{side}` | `deg` | `float` | 脚尖相对身体前进方向有符号水平夹角：正为外展，负为内扣（编码 `01/14`） |
| `V_KNEE_OVER_TOE` | `{side}` | `bool` | `true / false` | 膝前端水平投影是否明显超过同侧脚尖（编码 `12`） |
| `V_KNEE_TOE_ALIGNED` | `{side}` | `bool` | `true / false` | 支撑膝弯曲方向与同侧脚尖朝向是否对正（编码 `15/18`） |
| `V_HEEL_LIFT` | `{side}` | `bool` | `true / false` | 脚跟是否离地拔跟（`true` 触发弓步后跟离地 `12`；`false` 触发虚步前跟着地 `15`） |
| `V_FULL_FOOT_GROUNDED` | `{side}` | `bool` | `true / false` | 全脚掌是否完整贴地（`false` 触发仆步未全脚掌着地 `14`） |
| `V_FOOT_SLIDE` / `V_FOOT_PIVOT` | `{side}` | `bool` | `true / false` | 支撑期脚掌平移滑动 / 脚底碾转（编码 `82` 及连接难度落地碾动） |
| `V_FOOT_RECOVERY_STEP` / `V_FOOT_SKIP` | `{side}` | `bool` | `true / false` | 单脚失稳提前落脚迈步（`82`） / 失去平衡跳动（`83`） |
| `V_GROUND_CONTACT` / `V_UNEXPECTED_SUPPORT` | `{part}` | `bool` | `true / false` | 指定部位触地（`01/51/84`） / 失衡附加支撑借力（`83`） |
| `V_OUT_OF_BOUNDS` | `{}` | `bool` | `true / false` | 身体触及场地线外地面（编码 `88`） |
| `V_FOOT_ROTATION` | `{side}` | `deg` | `float` | 起跳至落地瞬间脚尖-脚跟连线的水平转体度数（表-11 跳跃旋转度数） |

## 5. 扣分编码注册表与两级去重聚合规则

### 5.1 权威扣分编码表（32 项，严格校验 `(code, group, points, scope)`）

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
| `D_STANCE_115` / `D_STANCE_135` | `D` | `0.10` | `technique` | 弓马步大腿与垂直轴夹角 `>115deg` / 虚步上步大腿与垂直轴夹角 `>135deg` |
| `D_SQUAT_INCOMPLETE` | `D` | `0.10` | `technique` | 仆步/前举腿低势平衡屈蹲腿未全蹲 |
| `D_BALANCE_51` / `D_KICK_LOW` | `D` | `0.15` / `0.10` | `technique` | 后插腿平衡支撑腿高于水平 / 蹬分摆莲脚低于肩 |
| `D_JUMP_CD` / `D_JUMP_EFG` | `D` | `0.15` / `0.20` | `technique` | C/D 级跳跃难度未完成 / E/F/G 级跳跃难度未完成 |

### 5.2 扩展强克林四值逻辑（$\mathcal{L}_4$）与章节去重规则
1. **四值短路求值**：每个 `Clause` 求值返回 $\mathbf{T}$（违规）、$\mathbf{F}$（合规）、$\mathbf{V}$（待请求视觉）、$\mathbf{U}$（不可恢复未知）。`ANY` 规则遇 $\mathbf{T}$ 立即短路返回 `VIOLATION`（免唤醒视觉）；`ALL` 规则遇 $\mathbf{F}$ 立即返回 `PASS`，遇 $\mathbf{U}$ 立即返回 `UNKNOWN`。
2. **两级去重聚合**：
   * `scope == "technique"`：同一动作实例（`chapter_instance_id`）内多条规则触发同一 `code` 时，仅首条保留 `effective_deduction_points = points`，其余记 `0.0` 并标注 `deduplicated_by`。
   * `scope == "event"`：编码 `80~89` 在帧窗口重叠或间隔 `< 12 frames` 时合并为同一失衡事件并取最高分值，间隔 `>= 12 frames` 时累计扣分。

## 6. 强类型 Pydantic v2 Schema（判别联合锁死 `primitive + args + op + target`）

```python
from typing import Annotated, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator

SideLiteral = Literal["left", "right", "front", "rear"]
AxisLiteral = Literal["up", "left", "front"]
RefPartLiteral = Literal["shoulder_center", "hip_center", "belly", "head"]
YawTargetLiteral = Literal["pelvis", "support_ankle"]
TruthStateLiteral = Literal["T", "F", "V", "U"]
EvalResultLiteral = Literal["VIOLATION", "PASS", "NEEDS_VISION", "UNKNOWN", "UNRESOLVABLE"]

ObjectLiteral = Literal[
    "root", "right_hip", "right_knee", "right_ankle",
    "left_hip", "left_knee", "left_ankle", "belly", "neck",
    "nose", "head", "left_shoulder", "left_elbow", "left_wrist",
    "right_shoulder", "right_elbow", "right_wrist",
    "hip_center", "shoulder_center", "com_est"
]

VisionPartLiteral = Literal[
    "left_hand", "right_hand", "left_elbow", "right_elbow",
    "left_shoulder", "right_shoulder", "left_knee", "right_knee",
    "front_knee", "rear_knee", "left_foot", "right_foot",
    "front_foot", "rear_foot", "left_heel", "right_heel",
    "front_heel", "rear_heel", "left_toe", "right_toe",
    "front_toe", "rear_toe", "head", "back", "hip"
]

HandFormLabel = Literal["palm", "fist", "hook", "other"]
HandDefectLabel = Literal["uneven_fist", "finger_gap", "bent_finger", "convex_palm", "none"]

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

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class EmptyArgs(StrictModel): pass
class SideArgs(StrictModel): side: SideLiteral
class AxisArgs(StrictModel): axis: AxisLiteral
class ObjectArgs(StrictModel): object: ObjectLiteral
class ObjectAxisArgs(StrictModel): object: ObjectLiteral; axis: AxisLiteral
class PairObjectArgs(StrictModel): a: ObjectLiteral; b: ObjectLiteral
class AnkleRelHeightArgs(StrictModel): side: SideLiteral; ref: RefPartLiteral
class YawRotationArgs(StrictModel): target: YawTargetLiteral
class VisionPartArgs(StrictModel): part: VisionPartLiteral

NumericScalar = Union[StrictFloat, StrictInt]
NumericTarget = Union[NumericScalar, List[NumericScalar]]
NumericOp = Literal["==", "!=", "<", "<=", ">", ">=", "BETWEEN"]

class NumericClauseBase(StrictModel):
    op: NumericOp
    target: NumericTarget

    @model_validator(mode="after")
    def check_numeric_op_target(self) -> "NumericClauseBase":
        if self.op == "BETWEEN":
            if not isinstance(self.target, list) or len(self.target) != 2 or self.target[0] > self.target[1]:
                raise ValueError("BETWEEN 的 target 必须为 [low, high] 且 low <= high")
        elif isinstance(self.target, list):
            raise ValueError(f"运算符 {self.op} 的 target 必须为单值")
        return self

class BoolClauseBase(StrictModel):
    op: Literal["==", "!="]
    target: StrictBool
    unit: Literal["bool"]

class SideDegClause(NumericClauseBase):
    primitive: Literal["KNEE_ANGLE", "KNEE_BEND", "THIGH_VERTICAL_ANGLE", "HIP_ANGLE", "ELBOW_ANGLE", "V_FOOT_OUTTURN", "V_FOOT_ROTATION"]
    args: SideArgs
    unit: Literal["deg"]

class EmptyDegClause(NumericClauseBase):
    primitive: Literal["THIGH_SPLIT_ANGLE", "SPINE_BEND", "SWAY_ANGLE"]
    args: EmptyArgs = Field(default_factory=EmptyArgs)
    unit: Literal["deg"]

class AxisDegClause(NumericClauseBase):
    primitive: Literal["TRUNK_TILT"]
    args: AxisArgs
    unit: Literal["deg"]

class YawDegClause(NumericClauseBase):
    primitive: Literal["YAW_ROTATION"]
    args: YawRotationArgs
    unit: Literal["deg"]

class SideNormClause(NumericClauseBase):
    primitive: Literal["KNEE_LIFT_HEIGHT", "SHOULDER_SHRUG", "ELBOW_RAISE", "KNEE_FORWARD_OFFSET", "KNEE_MEDIAL_OFFSET"]
    args: SideArgs
    unit: Literal["norm"]

class AnkleRelNormClause(NumericClauseBase):
    primitive: Literal["ANKLE_REL_HEIGHT"]
    args: AnkleRelHeightArgs
    unit: Literal["norm"]

class ObjectNormClause(NumericClauseBase):
    primitive: Literal["HEIGHT", "MAX_DRIFT"]
    args: ObjectArgs
    unit: Literal["norm"]

class ObjectAxisNormClause(NumericClauseBase):
    primitive: Literal["POS", "DISPLACEMENT"]
    args: ObjectAxisArgs
    unit: Literal["norm"]

class PairObjectNormClause(NumericClauseBase):
    primitive: Literal["DIST", "HORIZONTAL_DIST"]
    args: PairObjectArgs
    unit: Literal["norm"]

class EmptyNormClause(NumericClauseBase):
    primitive: Literal["STANCE_WIDTH"]
    args: EmptyArgs = Field(default_factory=EmptyArgs)
    unit: Literal["norm"]

class ObjectSpeedClause(NumericClauseBase):
    primitive: Literal["SPEED"]
    args: ObjectArgs
    unit: Literal["norm/frame"]

class EmptyRatioClause(NumericClauseBase):
    primitive: Literal["STANCE_FOOT_RATIO"]
    args: EmptyArgs = Field(default_factory=EmptyArgs)
    unit: Literal["ratio"]

class EmptyCountClause(NumericClauseBase):
    primitive: Literal["STEP_COUNT"]
    args: EmptyArgs = Field(default_factory=EmptyArgs)
    unit: Literal["count"]

class EmptyMsClause(NumericClauseBase):
    primitive: Literal["LANDING_TIME_DIFF", "BALANCE_STILL_MS"]
    args: EmptyArgs = Field(default_factory=EmptyArgs)
    unit: Literal["ms"]

class EmptyBoolClause(BoolClauseBase):
    primitive: Literal["FALL_SUSPECTED", "V_OUT_OF_BOUNDS"]
    args: EmptyArgs = Field(default_factory=EmptyArgs)

class SideBoolClause(BoolClauseBase):
    primitive: Literal["V_FOOT_SLAP_HIT", "V_KNEE_OVER_TOE", "V_KNEE_TOE_ALIGNED", "V_HEEL_LIFT", "V_FULL_FOOT_GROUNDED", "V_FOOT_SLIDE", "V_FOOT_PIVOT", "V_FOOT_RECOVERY_STEP", "V_FOOT_SKIP"]
    args: SideArgs

class VisionPartBoolClause(BoolClauseBase):
    primitive: Literal["V_GROUND_CONTACT", "V_UNEXPECTED_SUPPORT"]
    args: VisionPartArgs

class HandFormLabelClause(StrictModel):
    primitive: Literal["V_HAND_FORM"]
    args: SideArgs
    op: Literal["==", "!=", "IN"]
    target: Union[HandFormLabel, List[HandFormLabel]]
    unit: Literal["label"]

class HandDefectLabelClause(StrictModel):
    primitive: Literal["V_HAND_DEFECT"]
    args: SideArgs
    op: Literal["==", "!=", "IN"]
    target: Union[HandDefectLabel, List[HandDefectLabel]]
    unit: Literal["label"]

ClauseUnion = Annotated[
    Union[
        SideDegClause, EmptyDegClause, AxisDegClause, YawDegClause,
        SideNormClause, AnkleRelNormClause, ObjectNormClause,
        ObjectAxisNormClause, PairObjectNormClause, EmptyNormClause,
        ObjectSpeedClause, EmptyRatioClause, EmptyCountClause,
        EmptyMsClause, EmptyBoolClause, SideBoolClause,
        VisionPartBoolClause, HandFormLabelClause, HandDefectLabelClause
    ],
    Field(discriminator="primitive")
]
```