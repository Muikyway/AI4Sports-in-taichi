# H36M-17 太极拳神经符号动作规约语言（JSON-AST 规范版 v2.3）

> 本规范针对徒手太极拳竞赛规则（剔除器械与剑法条款），采用**“底层强类型抽象语法树（Typed JSON-AST，用于大模型受限解码、静态类型校验与确定性求值）+ 表层确定性导出微公式（Surface Micro-DSL，由 AST 自动转译，用于学术论文呈现与裁判端可读展示）”**的单源同构架构。骨骼输入固定为 MotionBERT 输出的 `h36m-17` 三维序列；涉及手型、脚法、足部朝向或触地关系时，按需触发图像模型结构化视觉证据。   

## 1. 目标、边界与双坐标系约定

### 1.1 系统边界

本语言规约四类核心计算内容：   

1. **三维骨骼几何**：基于 `H36M-17` 的 17 个三维关节点空间向量、角度与相对高度。   
2. **太极姿态与步型代理**：屈膝、提膝、踢腿高度、步型（弓/马/仆/虚/跌叉）、身型（弓背/翻臀/伸髋/斜身）、重心投影与站距比例。   
3. **时序模态与运动学事件**：指定动作阶段（Phase）内的净位移、最大水平漂移、累计转体度数、往返摇晃角、连续静止保持时长与失稳倒地。   
4. **按需视觉证据（Active Vision Evidence）**：仅在骨骼无法独立判定的细粒度部位（掌拳勾手型、击拍脚法、脚尖内扣/外展、拔跟、全脚掌着地、脚掌滑动/碾转、非预期触地）唤醒图像模型。   

### 1.2 双坐标系约定（适配 MotionBERT 预处理）

每帧输入为 `P[frame][joint][x,y,z]`，三维长度使用身高归一化单位 `norm`，二维图像距离使用 `image_norm`（`0..1`），角度使用 `deg`，比例使用 `ratio`，时间使用 `frame` 或 `ms`。为避免下蹲或重心平移时产生虚假位移，所有计算通过预处理转换到以下两个坐标系：   

| **坐标系名称**       | **符号** | **标定方法与适用原语**                                       | **标定失败降级策略**                                         |
| -------------------- | -------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **地面世界坐标系**   | `W`      | 利用起势直立帧标定真实重力反方向为 `+up`（消除相机俯仰角），并以非腾空帧双踝最低包络面锚定 `up = 0` 水平地面。所有**绝对高度**（`HEIGHT`）、**支撑期脚踝漂移**（`MAX_DRIFT`）、**净位移**（`DISPLACEMENT`）及**水平累计转角**（`YAW_ROTATION`）均在 `W` 下计算。 | 若相机剧烈运动或地面拟合残差超标，依赖 `W` 的原语统一返回状态 `U`（`UNKNOWN`）。 |
| **解剖学朝向坐标系** | `B`      | 由骨盆与双肩水平投影确定表演者瞬时或阶段朝向：`up` 竖直向上，`left` 指表演者左侧，`front` 指表演者身体正前方。 | 若髋肩关键点缺失导致朝向轴无法解算，相关投影原语返回 `U`（`UNKNOWN`）。 |

## 2. H36M-17 原始对象与派生对象

### 2.1 H36M-17 原始关节对象（17 个闭合枚举）

仅以下 17 个小写规范名为合法原始关节对象：   

| **对象名**    | **下标** | **含义**        | **对象名**       | **下标** | **含义**                   |
| ------------- | -------- | --------------- | ---------------- | -------- | -------------------------- |
| `root`        | 0        | 骨盆根节点      | `nose`           | 9        | 鼻部（面部朝向与前额代理） |
| `right_hip`   | 1        | 右髋            | `head`           | 10       | 头部顶点                   |
| `right_knee`  | 2        | 右膝            | `left_shoulder`  | 11       | 左肩                       |
| `right_ankle` | 3        | 右踝            | `left_elbow`     | 12       | 左肘                       |
| `left_hip`    | 4        | 左髋            | `left_wrist`     | 13       | 左腕                       |
| `left_knee`   | 5        | 左膝            | `right_shoulder` | 14       | 右肩                       |
| `left_ankle`  | 6        | 左踝            | `right_elbow`    | 15       | 右肘                       |
| `belly`       | 7        | 腹部/腰部基准点 | `right_wrist`    | 16       | 右腕                       |
| `neck`        | 8        | 颈部基点        |                  |          |                            |

### 2.2 几何与生物力学派生对象

| **派生对象名**    | **计算公式定义**                                             | **类型标识**             |
| ----------------- | ------------------------------------------------------------ | ------------------------ |
| `hip_center`      | `(left_hip + right_hip) / 2`                                 | 几何派生 (`proxy=false`) |
| `shoulder_center` | `(left_shoulder + right_shoulder) / 2`                       | 几何派生 (`proxy=false`) |
| `body_axis`       | 向量 `hip_center -> shoulder_center`                         | 几何派生 (`proxy=false`) |
| `pelvis_heading`  | 向量 `right_hip -> left_hip` 绕 `+up` 顺时针旋转 `90deg` 的水平朝向向量 | 几何派生 (`proxy=false`) |
| `foot_len_est`    | 双侧小腿长均值乘人体统计比例系数（默认 `0.68`）              | 代理量 (`proxy=true`)    |
| `com_est`         | 按固定人体分段质量权重计算的整体重心三维坐标                 | 代理量 (`proxy=true`)    |
| `support_side`    | 由 `com_est` 地面投影与双踝坐标推断的主承重侧（`left/right/both`） | 代理量 (`proxy=true`)    |

## 3. 原语算子库

所有原语在输入点缺失或置信度低于阈值时统一返回状态 `U`（`UNKNOWN`）。每个原语均绑定唯一的**参数结构（Args Schema）\**与\**返回单位（Unit）**。   

### 3.1 空间位置、相对高度与时序运动原语

| **原语名称**        | **参数结构 (args)** | **返回单位 (unit)** | **代理属性** | **严格定义与对应规则场景**                                   |
| ------------------- | ------------------- | ------------------- | ------------ | ------------------------------------------------------------ |
| `POS`               | `{object, axis}`    | `norm`              | `false`      | 对象在 `up/left/front` 轴上的坐标                            |
| `DIST`              | `{a, b}`            | `norm`              | `false`      | 同帧两点三维欧氏距离（正踢腿脚踝与 `head/nose` 距离判定）    |
| `HORIZONTAL_DIST`   | `{a, b}`            | `norm`              | `false`      | 地面水平面（忽略 `up`）上的两点距离                          |
| `HEIGHT`            | `{object}`          | `norm`              | `false`      | 对象在地面世界坐标系 `W` 中的垂直高度                        |
| `KNEE_LIFT_HEIGHT`  | `{side}`            | `norm`              | `true`       | `HEIGHT(side.knee) - HEIGHT(belly)`；膝点相对腰腹基准点 `belly(7)` 的高度差（覆盖编码 `03` 提膝未过腰；因单目腰腹点受服装影响标为代理量） |
| `ANKLE_REL_HEIGHT`  | `{side, ref}`       | `norm`              | `true`       | `HEIGHT(side.ankle) - HEIGHT(ref)`；`ref` 取 `shoulder_center / hip_center / belly / head`（覆盖编码 `50/60/61/70`） |
| `DISPLACEMENT`      | `{object, axis}`    | `norm`              | `false`      | 阶段窗口末帧减首帧在 `W` 系下沿初始 `axis` 轴的净位移        |
| `MAX_DRIFT`         | `{object}`          | `norm`              | `false`      | 阶段窗口内对象在水平面偏离窗口首帧位置的最大欧氏距离（编码 `82` 支撑踝移动粗筛） |
| `SPEED`             | `{object}`          | `norm/frame`        | `false`      | 相邻帧在 `W` 系下的三维速度幅值                              |
| `STEP_COUNT`        | `{}`                | `count`             | `true`       | 助跑阶段窗口内双踝交替触地迈步次数（表-11 腾空飞脚/正踢腿助跑超 1 步） |
| `LANDING_TIME_DIFF` | `{}`                | `ms`                | `true`       | 跳跃接跌叉落地阶段，左右腿首次触地帧的时间差绝对值（表-11 两腿依次落地） |

### 3.2 角度、步型深度、身型与旋转原语

| **原语名称**           | **参数结构 (args)** | **返回单位 (unit)** | **代理属性** | **严格定义与对应规则场景**                                   |
| ---------------------- | ------------------- | ------------------- | ------------ | ------------------------------------------------------------ |
| `KNEE_ANGLE`           | `{side}`            | `deg`               | `false`      | `ANGLE(side.hip, side.knee, side.ankle)`，直腿为 `180deg`    |
| `KNEE_BEND`            | `{side}`            | `deg`               | `false`      | `180deg - KNEE_ANGLE(side)`，直腿为 `0deg`，屈膝首选算子（覆盖 `12/14/60/61/71`） |
| `THIGH_VERTICAL_ANGLE` | `{side}`            | `deg`               | `false`      | 大腿向量 `side.hip -> side.knee` 与竖直向上轴 `+up` 夹角；直立 `180deg`，水平蹲平 `90deg`（表-11 弓马步 `>115deg`、虚步 `>135deg`） |
| `THIGH_SPLIT_ANGLE`    | `{}`                | `deg`               | `false`      | `ANGLE(left_knee, hip_center, right_knee)`；两大腿展开夹角（覆盖编码 `01` 跌叉夹角 `<=45deg`） |
| `TRUNK_TILT`           | `{axis}`            | `deg`               | `false`      | `axis=up` 为 `body_axis` 与 `+up` 夹角；`axis=left/front` 为对应平面倾角（斜身/后仰 `16`） |
| `SPINE_BEND`           | `{}`                | `deg`               | `false`      | `180deg - ANGLE(hip_center, belly, neck)`；直背 `0deg`，正值衡量含胸弓背（编码 `16`） |
| `HIP_ANGLE`            | `{side}`            | `deg`               | `false`      | `ANGLE(belly, side.hip, side.knee)`；衡量髋部折叠、翻臀与伸髋（编码 `16`） |
| `ELBOW_ANGLE`          | `{side}`            | `deg`               | `false`      | `ANGLE(side.shoulder, side.elbow, side.wrist)`（覆盖编码 `17` 直臂） |
| `SHOULDER_SHRUG`       | `{side}`            | `norm`              | `false`      | `HEIGHT(side.shoulder) - HEIGHT(neck)`（覆盖编码 `17` 耸肩） |
| `ELBOW_RAISE`          | `{side}`            | `norm`              | `false`      | `HEIGHT(side.elbow) - HEIGHT(side.wrist)`（覆盖编码 `17` 抬肘） |
| `YAW_ROTATION`         | `{target}`          | `deg`               | `true`       | 窗口内 `target`（`pelvis` 或 `support_ankle`）在水平面累计旋转角绝对值（跳跃转体 `180..540deg`） |

### 3.3 站距、重心与平衡摇晃原语

| **原语名称**          | **参数结构 (args)** | **返回单位 (unit)** | **代理属性** | **严格定义与对应规则场景**                                   |
| --------------------- | ------------------- | ------------------- | ------------ | ------------------------------------------------------------ |
| `STANCE_WIDTH`        | `{}`                | `norm`              | `false`      | `HORIZONTAL_DIST(left_ankle, right_ankle)`                   |
| `STANCE_FOOT_RATIO`   | `{}`                | `ratio`             | `true`       | `STANCE_WIDTH / foot_len_est`；双脚横向间距与估算脚长比值（编码 `13` 马步 `>3.5 ratio`） |
| `KNEE_FORWARD_OFFSET` | `{side}`            | `norm`              | `true`       | 膝点相对同侧踝在 `front` 轴有符号投影距离（仅作弓步前膝过冲粗筛，不可单独定罪） |
| `KNEE_MEDIAL_OFFSET`  | `{side}`            | `norm`              | `true`       | 膝点相对同侧髋踝连线向身体中线内扣的偏移距离（仅作虚步/上步膝内扣粗筛） |
| `SWAY_ANGLE`          | `{}`                | `deg`               | `false`      | 稳定支撑期内躯干在竖直面往返摆动的最大角位移（`1..45deg` 小晃动 `80`，`>45deg` 大晃动 `81`） |
| `BALANCE_STILL_MS`    | `{}`                | `ms`                | `false`      | 平衡窗口内自首次进入全身静止状态起，连续保持静止的最长毫秒数（编码 `87` 平衡 `<2000ms`） |
| `FALL_SUSPECTED`      | `{}`                | `bool`              | `true`       | 重心快速跌落且躯干大倾角失稳（编码 `84` 倒地粗筛）           |

### 3.4 图像模型视觉原语（`V_*`，仅徒手太极拳）

| **原语名称**           | **参数结构 (args)** | **返回单位 (unit)** | **目标值类型 (target)**                                      | **视觉语义与对应规则编码**                                   |
| ---------------------- | ------------------- | ------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| `V_HAND_FORM`          | `{side}`            | `label`             | `palm / fist / hook / other`                                 | 手型分类（覆盖编码 `10/11`）                                 |
| `V_HAND_DEFECT`        | `{side}`            | `label`             | `uneven_fist / finger_gap / bent_finger / convex_palm / none` | 手型细粒度错误标签（直接对应编码 `10` 与 `11`）              |
| `V_FOOT_SLAP_HIT`      | `{side}`            | `bool`              | `true / false`                                               | 摆莲/拍脚/飞脚/旋风脚中手掌是否准确击中脚面（编码 `61/70`）  |
| `V_FOOT_OUTTURN`       | `{side}`            | `deg`               | `float`                                                      | 脚尖相对身体前进方向的有符号水平夹角：正为外展，负为内扣（编码 `01/14`） |
| `V_KNEE_OVER_TOE`      | `{side}`            | `bool`              | `true / false`                                               | 膝前端水平投影是否明显超过同侧脚尖（编码 `12` 弓步前膝过脚尖） |
| `V_KNEE_TOE_ALIGNED`   | `{side}`            | `bool`              | `true / false`                                               | 支撑膝弯曲方向与同侧脚尖朝向是否对正（虚步 `15`、上步 `18`） |
| `V_HEEL_LIFT`          | `{side}`            | `bool`              | `true / false`                                               | 脚跟是否明显离地拔跟（`true` 触发弓步后跟离地 `12`；`false` 触发虚步前跟着地 `15`） |
| `V_FULL_FOOT_GROUNDED` | `{side}`            | `bool`              | `true / false`                                               | 全脚掌是否完整贴地（`false` 触发仆步未全脚掌着地 `14`）      |
| `V_FOOT_SLIDE`         | `{side}`            | `bool`              | `true / false`                                               | 支撑期脚掌与地面接触时发生平移滑动（编码 `82` 移动）         |
| `V_FOOT_PIVOT`         | `{side}`            | `bool`              | `true / false`                                               | 支撑期或跳跃落地后脚跟/脚尖发生碾转（编码 `82` 及连接难度落地碾动） |
| `V_FOOT_RECOVERY_STEP` | `{side}`            | `bool`              | `true / false`                                               | 单脚独立失稳时非支撑脚提前下落迈步（编码 `82`）              |
| `V_FOOT_SKIP`          | `{side}`            | `bool`              | `true / false`                                               | 支撑期或落地时脚短暂离地跳动（编码 `83` 跳动）               |
| `V_GROUND_CONTACT`     | `{part}`            | `bool`              | `true / false`                                               | 指定部位与地面可见接触（跌叉前脚掌触地 `01`、后插腿触地 `51`、倒地 `84`） |
| `V_UNEXPECTED_SUPPORT` | `{part}`            | `bool`              | `true / false`                                               | 失衡时手、肘、膝、头或非支撑脚触地借力（编码 `83` 附加支撑） |
| `V_OUT_OF_BOUNDS`      | `{}`                | `bool`              | `true / false`                                               | 身体任何一部分触及场地白线外地面（编码 `88` 出界）           |
| `V_FOOT_ROTATION`      | `{side}`            | `deg`               | `float`                                                      | 起跳瞬间至落地瞬间脚跟-脚尖连线的水平转体度数（表-11 跳跃旋转度数） |

## 4. 扣分编码与分值注册表（Deduction Registry）

Schema 校验器在运行时强制核对 `(code, group, points, scope)` 四元组必须与下表完全一致：   

| **编码 (code)**               | **评分组 (group)** | **分值 (points)**        | **去重作用域 (scope)** | **规则名称与扣分含义**                                       |
| ----------------------------- | ------------------ | ------------------------ | ---------------------- | ------------------------------------------------------------ |
| `10` / `11`                   | `E`                | `0.10`                   | `technique`            | **拳型错误**（拳面不平） / **掌型错误**（指间过宽、指弯、掌心外凸） |
| `12` / `13`                   | `E`                | `0.10`                   | `technique`            | **弓步规格错误**（前膝过脚尖/后腿弯/拔跟） / **马步错误**（横向间距 `>3.5` 倍脚长） |
| `14` / `15`                   | `E`                | `0.10`                   | `technique`            | **仆步规格错误**（仆腿弯/未内扣全脚掌着地） / **虚步规格错误**（膝与脚尖未对正/前跟着地） |
| `16` / `17` / `18`            | `E`                | `0.10`                   | `technique`            | **身型错误**（翻臀弓背/伸髋后仰） / **手法错误**（直臂/耸肩/抬肘） / **上步错误** |
| `01` / `03`                   | `E`                | `0.10`                   | `technique`            | **跌叉错误**（前脚掌内扣触地/夹角 `<=45deg`） / **提膝独立错误**（提腿膝部未过腰） |
| `50` / `51`                   | `E`                | `0.10`                   | `technique`            | **前举腿低势平衡错误**（前举腿低于水平） / **后插腿低势平衡错误**（插出腿脚触地） |
| `60` / `61`                   | `E`                | `0.10`                   | `technique`            | **蹬脚/分脚错误**（支撑腿弯/上举腿弯） / **摆莲/拍脚错误**（摆腿弯/击拍落空/脚低于肩） |
| `70` / `71`                   | `E`                | `0.10`                   | `technique`            | **飞脚/旋风脚/腾空摆莲错误**（击拍落空/未过肩） / **腾空正踢腿错误**（悬垂腿弯曲） |
| `80` / `81`                   | `E`                | `0.10` / `0.20`          | `event`                | **小晃动**（`<=45deg`） / **大晃动**（`>45deg`）             |
| `82` / `83` / `84`            | `E`                | `0.10` / `0.20` / `0.30` | `event`                | **脚碾动、移动** / **跳动、附加支撑** / **倒地**             |
| `87` / `88` / `89`            | `E`                | `0.10`                   | `event`                | **平衡时间不足**（静止 `<2000ms`） / **出界** / **遗忘**     |
| `D_STANCE_115` / `135`        | `D`                | `0.10`                   | `technique`            | **弓/马/偏马步难度不符**（`>115deg`） / **虚步/上步难度不符**（`>135deg`） |
| `D_SQUAT_INCOMPLETE`          | `D`                | `0.10`                   | `technique`            | **仆步/前举腿平衡难度不符**：屈蹲支撑腿未全蹲                |
| `D_BALANCE_51` / `D_KICK_LOW` | `D`                | `0.15` / `0.10`          | `technique`            | **后插腿平衡难度不符**（支撑大腿高于水平） / **蹬分摆莲难度不符**（脚低于肩） |
| `D_JUMP_CD` / `D_JUMP_EFG`    | `D`                | `0.15` / `0.20`          | `technique`            | **C/D级跳跃难度未完成** / **E/F/G级跳跃难度未完成**          |

## 5. 扩展强克林四值逻辑（Strong Kleene $\mathcal{L}_4$）、骨骼优先求值与代理保护协议

### 5.1 命题真值域与顶层违规映射解耦（Truth vs. Violation Separation）

为消除“命题真假”与“违规极性”混同引发的逻辑悖论，本语言严格区分**内部命题真值（Proposition Truth Value）\**与\**顶层判罚结果（Evaluation Result）**：

1. **违规条件建模范式**：每个 `ViolationItem` 及其内部的 `Clause` 均统一表述为“构成违规的触发条件”（例如：`KNEE_BEND(rear) > 20.0deg` 或 `BALANCE_STILL_MS() < 2000ms`）。   

2. **四值命题真值域 $\mathcal{L}_4 = \{\mathbf{T}, \mathbf{F}, \mathbf{V}, \mathbf{U}\}$**：

   - $\mathbf{T}$（`TRUE`）：该原子条件或子项命题**求值为真**（确认满足违规触发条件）。   
   - $\mathbf{F}$（`FALSE`）：该原子条件或子项命题**求值为假**（确认未触发该违规）。   
   - $\mathbf{V}$（`NEEDS_VISION`）：该条件为 `V_*` 视觉原语，当前处于第一阶段纯骨骼推理，唤醒图像模型后可求解。   
   - $\mathbf{U}$（`UNKNOWN`）：骨骼关键点缺失/低置信度、代理量落入模糊边界，或视觉遮挡导致**不可恢复未知**。   

3. **规则级状态映射**：仅当整条 `RuleNode` 下所有 `violation_items` 按析取（`ANY`）汇总完毕后，才将顶层真值映射为规则评估结果：

   $$\mathbf{T} \mapsto \text{"VIOLATION"}, \quad \mathbf{F} \mapsto \text{"PASS"}, \quad \mathbf{V} \mapsto \text{"NEEDS\_VISION"}, \quad \mathbf{U} \mapsto \text{"UNKNOWN"}$$

### 5.2 二层逻辑组合真值表与吸收优先级

每条 `RuleNode` 采用**二层析取范式（2-Level DNF）**：内层 `ViolationItem` 通过 `logic: "ALL" | "ANY"` 组合多个 `Clause`；外层 `RuleNode` 对所有 `violation_items` 执行 `ANY`（任一违规原因成立即触发该规则扣分）。   

- **合取算子 `ALL`（$\land$ —— 子项内所有原子条件同时为真才构成该子项违规）**：   
  - **短路吸收律**：$\mathbf{F}$ 为绝对零元（任一必要条件为 $\mathbf{F}$，该子项绝无可能成立，直接返回 $\mathbf{F}$）。   
  - **不可恢复优先律**：无 $\mathbf{F}$ 时，$\mathbf{U}$ 吸收 $\mathbf{V}$（已有必需条件永久不可知 $\mathbf{U}$，不再发起无效视觉请求，直接返回 $\mathbf{U}$）。   

| **ALL (a∧b)**                 | **T**        | **V (NEEDS_VISION)** | **U (UNKNOWN)** | **F**        |
| ----------------------------- | ------------ | -------------------- | --------------- | ------------ |
| $\mathbf{T}$                  | $\mathbf{T}$ | $\mathbf{V}$         | $\mathbf{U}$    | $\mathbf{F}$ |
| $\mathbf{V}$ (`NEEDS_VISION`) | $\mathbf{V}$ | $\mathbf{V}$         | $\mathbf{U}$    | $\mathbf{F}$ |
| $\mathbf{U}$ (`UNKNOWN`)      | $\mathbf{U}$ | $\mathbf{U}$         | $\mathbf{U}$    | $\mathbf{F}$ |
| $\mathbf{F}$                  | $\mathbf{F}$ | $\mathbf{F}$         | $\mathbf{F}$    | $\mathbf{F}$ |

- **析取算子 `ANY`（$\lor$ —— 任一条件/子项为真即构成违规）**：   
  - **短路吸收律**：$\mathbf{T}$ 为绝对零元（一旦确认任一骨骼违规子项为 $\mathbf{T}$，立即短路确认违规，免除后续视觉请求）。   
  - **可恢复唤醒优先律**：无 $\mathbf{T}$ 时，$\mathbf{V}$ 吸收 $\mathbf{U}$（只要仍有视觉分支有望检出违规，优先返回 $\mathbf{V}$ 唤醒图像模型）。   

| **ANY (a∨b)**                 | **T**        | **V (NEEDS_VISION)** | **U (UNKNOWN)** | **F**        |
| ----------------------------- | ------------ | -------------------- | --------------- | ------------ |
| $\mathbf{T}$                  | $\mathbf{T}$ | $\mathbf{T}$         | $\mathbf{T}$    | $\mathbf{T}$ |
| $\mathbf{V}$ (`NEEDS_VISION`) | $\mathbf{T}$ | $\mathbf{V}$         | $\mathbf{V}$    | $\mathbf{V}$ |
| $\mathbf{U}$ (`UNKNOWN`)      | $\mathbf{T}$ | $\mathbf{V}$         | $\mathbf{U}$    | $\mathbf{U}$ |
| $\mathbf{F}$                  | $\mathbf{T}$ | $\mathbf{V}$         | $\mathbf{U}$    | $\mathbf{F}$ |

### 5.3 骨骼优先短路求值协议（Skeletal-First Evaluation Protocol）

1. **重排求值顺序**：执行器先评估純三维骨骼 `ViolationItem`，再评估含已缓存视觉原语的子项，最后评估含待请求 `V_*` 原语的子项。   
2. **跨子项短路**：若某个纯骨骼 `ViolationItem` 已求值为 $\mathbf{T}$（且当前处于 `per_code` 去重模式，无需枚举同编码其余视觉缺陷），整条规则立即短路返回 `VIOLATION`，不触发 `REQUEST_VISION`。   

### 5.4 生物力学代理量判罚保护协议（Proxy Governance Protocol）

针对第 3 节中标记为 `proxy=true` 的近似生物力学原语（如 `KNEE_LIFT_HEIGHT`、`STANCE_FOOT_RATIO`、`KNEE_FORWARD_OFFSET`），执行器强制实施以下保护准则：   

1. **粗筛代理禁止独立定罪**：`KNEE_FORWARD_OFFSET`（膝踝偏移）与 `KNEE_MEDIAL_OFFSET`（膝内扣偏移）仅允许作为唤醒 `V_KNEE_OVER_TOE` / `V_KNEE_TOE_ALIGNED` 的前置粗筛条件，严禁在无视觉原语配合下单独作为 `ViolationItem` 触发扣分。   
2. **独立代理的置信度与边界裕度门控**：当 `STANCE_FOOT_RATIO`（马步估算脚长比）或 `KNEE_LIFT_HEIGHT`（提膝相对 `belly` 高度）独立构成 `ViolationItem` 时：
   - 若关联关节点平均置信度 `< 0.85`，该 `Clause` 强制返回 $\mathbf{U}$（`UNKNOWN`）；
   - 若实测值落入阈值边界的统计误差模糊带（如马步阈值 `3.50 ratio` 的 `+0.15 ratio` 裕度区间 `[3.50, 3.65]`，或提膝高度 `0.0 norm` 的 `[-0.03, 0.0]` 裕度区间），不得直接判为 $\mathbf{T}$，必须返回 $\mathbf{U}$（`UNKNOWN`）并标记需人工复核。

## 6. 强类型 JSON-AST 语言结构与实例（v2.3）

### 6.1 顶层与各层级必要字段说明

| **层级**   | **字段名**                                  | **类型**                       | **必填** | **设计目的与强类型约束说明**                                 |
| ---------- | ------------------------------------------- | ------------------------------ | -------- | ------------------------------------------------------------ |
| **Root**   | `dsl_version`                               | `Literal`                      | 是       | 固定为 `"H36M17-TAICHI-JSON-2.3"`                            |
| **Root**   | `input_spec`                                | `InputSpec`                    | 是       | 含 `skeleton: "h36m-17"`, `fps > 0`, `vision_mode: "demand_driven" | "full"` |
| **Root**   | `chapter`                                   | `ChapterSpec`                  | 是       | 含 `chapter_id`、`action_name`、`action_code`                |
| **Root**   | `rules`                                     | `List[RuleNode]`               | 是       | 章节内规则列表；强制校验 `rule_id` 及所有 `violation_items.item_id` 全局唯一 |
| **Rule**   | `rule_id`, `phase`, `frame_window`          | `str`, `[int, int]`            | 是       | 规则唯一 ID、动作阶段名及闭区间 `[start, end]`（`0 <= start <= end`） |
| **Rule**   | `stance_binding`                            | `StanceBinding`                | 是       | 显式绑定 `front`, `rear`, `support`；拦截 `front == rear` 或 `airborne` 下绑定前后腿 |
| **Rule**   | `unresolvable`                              | `bool`                         | 是       | 默认为 `false`；若为单目+H36M17 物理不可测条款（如五趾抓地），设为 `true` 且 `violation_items` 置空 |
| **Rule**   | `violation_items`                           | `List[ViolationItem]`          | 条件     | 同阶段、同扣分编码下的具名违规原因列表（外层为 `ANY` 析取）；`unresolvable=false` 时必填 |
| **Item**   | `item_id`, `reason_zh`                      | `str`                          | 是       | 子项唯一英文 ID（如 `"bow_left_rear_leg_bent"`）与中文判罚原因说明 |
| **Item**   | `logic`, `clauses`                          | `Literal`, `List[ClauseUnion]` | 是       | 子项内部组合逻辑（默认 `"ALL"`，支持跌叉等复合条件）与强类型判别联合原子条件列表 |
| **Clause** | `primitive`, `args`, `op`, `target`, `unit` | 判别联合绑定                   | 是       | 由 `primitive` 唯一决定合法参数模型、运算符、目标值类型与物理单位 |
| **Rule**   | `deduction`                                 | `DeductionSpec`                | 是       | 强制对照第 4 节注册表校验 `(code, group, points, scope)` 四元组一致性 |
| **Rule**   | `uncertainty`                               | `UncertaintySpec`              | 是       | 若任一子项含 `V_*` 原语，强制要求配置 `on_unavailable` 且其 `frame_window` 与规则一致 |

### 6.2 完整输入规则 JSON-AST 实例（含一码多因与复合逻辑）

JSON

```
{
  "dsl_version": "H36M17-TAICHI-JSON-2.3",
  "input_spec": {
    "skeleton": "h36m-17",
    "fps": 25,
    "vision_mode": "demand_driven"
  },
  "chapter": {
    "chapter_id": "yang_yema_fenzong",
    "action_name": "杨式左右野马分鬃",
    "action_code": "100A"
  },
  "rules": [
    {
      "rule_id": "yema_left_bow_spec_e",
      "phase": "hold_left_bow",
      "frame_window": [45, 90],
      "stance_binding": {
        "front": "left",
        "rear": "right",
        "support": "left"
      },
      "unresolvable": false,
      "violation_items": [
        {
          "item_id": "bow_left_front_knee_over_toe",
          "reason_zh": "左弓步前腿膝部超出脚尖",
          "logic": "ALL",
          "clauses": [
            {
              "primitive": "V_KNEE_OVER_TOE",
              "args": { "side": "front" },
              "op": "==",
              "target": true,
              "unit": "bool"
            }
          ]
        },
        {
          "item_id": "bow_left_rear_leg_bent",
          "reason_zh": "左弓步后腿明显弯曲",
          "logic": "ALL",
          "clauses": [
            {
              "primitive": "KNEE_BEND",
              "args": { "side": "rear" },
              "op": ">",
              "target": 20.0,
              "unit": "deg"
            }
          ]
        },
        {
          "item_id": "bow_left_rear_heel_lift",
          "reason_zh": "左弓步后脚跟离地拔跟",
          "logic": "ALL",
          "clauses": [
            {
              "primitive": "V_HEEL_LIFT",
              "args": { "side": "rear" },
              "op": "==",
              "target": true,
              "unit": "bool"
            }
          ]
        }
      ],
      "deduction": {
        "code": "12",
        "points": 0.10,
        "group": "E",
        "scope": "technique"
      },
      "uncertainty": {
        "on_unavailable": {
          "action": "REQUEST_VISION",
          "target_parts": ["front_knee", "front_toe", "rear_heel"],
          "frame_window": [45, 90],
          "instruction": "需侧面视角检测 45..90 帧左弓步定式期：1) 左膝前端水平投影是否超过左脚尖；2) 右脚跟是否离地拔跟"
        },
        "on_unknown": "左脚尖、右脚跟被遮挡或后腿骨骼关节点缺失，无法完整判定弓步规格错误（编码 12）"
      }
    }
  ]
}
```

## 7. 执行结果 JSON 格式与多规则去重聚合规范

### 7.1 单条规则求值结果与子项轨迹对齐（`RuleEvalResult` & `ItemTrace`）

为与输入端的 `violation_items` 严格对齐，输出报告采用 **`RuleEvalResult` $\to$ `item_traces: List[ItemTrace]` $\to$ `clause_traces: List[ClauseTrace]`** 的三级审计结构，并提供 `triggered_items: List[str]` 直接列出所有状态为 `T` 的违规子项 ID。   

### 7.2 多规则触发同一扣分项的两级去重算法

对照《国际太极拳竞赛规则》第 34 条，章节聚合器（Aggregator）对同一 `chapter_instance_id` 下所有 `result == "VIOLATION"` 的规则执行两级去重：   

1. **单式技术错误去重（`deduction_scope == "technique"`，编码 `01~71` 及 `D_\*`）**：   
   - **同规则内多子项去重**：同一条 `RuleNode` 内无论命中多少个 `triggered_items`（如左弓步同时发生后腿弯曲和拔跟），该规则仅产生一次 `raw_deduction_points = points`。   
   - **跨规则同编码去重（《规则》34.1.2 / 34.1.3）**：同一动作实例内，多条规则触发同一 `deduction_code`（如左弓步规则和右弓步规则均触发 `code="12"`），按起始帧排序，**仅首条违规规则保留 `effective_deduction_points = points, counted_events = 1`**；后续同编码违规全部标记 `effective_deduction_points = 0.0, counted_events = 0, deduplicated_by = <first_event_id>`。支持通过 `aggregation_policy = "per_code" | "strict_single_spec_cap"` 切换单式 E 组规格错误 `0.10` 分总封顶（《规则》34.1.1）。   
2. **动态失衡事件去重（`deduction_scope == "event"`，编码 `80~89`）**：   
   - 按时间窗口聚类：若两个失衡事件的帧区间重叠或间隔 `< 12 frames`，合并为同一物理失衡事件并取最高分值；若间隔 `>= 12 frames`，按《规则》第 34.2.6 条全额累加扣分。   

### 7.3 执行结果 JSON 实例（与 `violation_items` 完全对齐）

JSON

```
{
  "chapter_id": "yang_yema_fenzong",
  "chapter_instance_id": "yang_yema_fenzong#1",
  "aggregation_policy": "per_code",
  "chapter_status": "COMPLETED",
  "total_e_deduction": 0.10,
  "total_d_deduction": 0.00,
  "rule_results": [
    {
      "rule_id": "yema_left_bow_spec_e",
      "chapter_id": "yang_yema_fenzong",
      "chapter_instance_id": "yang_yema_fenzong#1",
      "phase": "hold_left_bow",
      "frame_range": [45, 90],
      "result": "VIOLATION",
      "triggered_items": ["bow_left_rear_leg_bent"],
      "item_traces": [
        {
          "item_id": "bow_left_rear_leg_bent",
          "reason_zh": "左弓步后腿明显弯曲",
          "logic": "ALL",
          "state": "T",
          "clause_traces": [
            {
              "primitive": "KNEE_BEND",
              "args": { "side": "rear" },
              "actual_value": 27.4,
              "op": ">",
              "target": 20.0,
              "unit": "deg",
              "confidence": 0.96,
              "source": "skeleton_3d",
              "proxy": false,
              "state": "T"
            }
          ]
        },
        {
          "item_id": "bow_left_front_knee_over_toe",
          "reason_zh": "左弓步前腿膝部超出脚尖",
          "logic": "ALL",
          "state": "V",
          "clause_traces": [
            {
              "primitive": "V_KNEE_OVER_TOE",
              "args": { "side": "front" },
              "actual_value": null,
              "op": "==",
              "target": true,
              "unit": "bool",
              "confidence": null,
              "source": "vision_2d",
              "proxy": false,
              "state": "V"
            }
          ]
        }
      ],
      "proxy_used": false,
      "vision_required": false,
      "explanation": "经骨骼优先短路求值：子项 bow_left_rear_leg_bent 实测后腿屈膝角 27.4deg > 20.0deg（状态 T），直接确认编码 12 违规，免除唤醒视觉模型",
      "vision_request": null,
      "event_id": "yang_yema_fenzong#1:12:68",
      "deduction_code": "12",
      "score_group": "E",
      "deduction_scope": "technique",
      "raw_deduction_points": 0.10,
      "effective_deduction_points": 0.10,
      "counted_events": 1,
      "deduplicated_by": null
    }
  ]
}
```