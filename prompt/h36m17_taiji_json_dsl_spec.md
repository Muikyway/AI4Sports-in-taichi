# H36M-17 太极拳神经符号动作规约语言（JSON-AST 规范版 v2.2）

> 本规范针对徒手太极拳竞赛规则（剔除器械与剑法条款），采用**“表层形式化语法（Surface DSL，用于学术论文呈现）+ 底层强类型抽象语法树（JSON-AST，用于大模型受限解码与代码直接求值）”**的双层同构架构。骨骼输入固定为 MotionBERT 输出的 `h36m-17` 三维序列；涉及手型、脚法、足部朝向或触地关系时，按需触发图像模型结构化视觉证据。

## 1. 目标、边界与双坐标系约定

### 1.1 系统边界
本语言规约四类核心计算内容：
1. **三维骨骼几何**：基于 `H36M-17` 的 17 个三维关节点空间向量、角度与相对高度。
2. **太极姿态与步型代理**：屈膝、提膝、踢腿高度、步型（弓/马/仆/虚/跌叉）、身型（弓背/翻臀/伸髋/斜身）、重心投影与站距比例。
3. **时序模态与运动学事件**：指定动作阶段（Phase）内的净位移、最大水平漂移、累计转体度数、往返摇晃角、连续静止保持（Hold）与失稳倒地。
4. **按需视觉证据（Active Vision Evidence）**：仅在骨骼无法独立判定的细粒度部位（掌拳勾手型、击拍脚法、脚尖内扣/外展、拔跟、全脚掌着地、脚掌滑动/碾转、非预期触地）唤醒图像模型。

### 1.2 双坐标系约定（适配 MotionBERT 预处理）
每帧输入为 `P[frame][joint][x,y,z]`，三维长度使用身高归一化单位 `norm`，二维图像距离使用 `image_norm`（`0..1`），角度使用 `deg`，比例使用 `ratio`，时间使用 `frame` 或 `ms`。
为避免下蹲或重心平移时产生虚假位移，所有计算通过预处理转换到以下两个坐标系：
1. **地面世界坐标系（Arena World Frame, `W`）**：
   - 利用起势直立帧标定真实重力反方向为 `+up`（消除相机俯仰角），并以非腾空帧双踝最低点锚定水平地面为 `z = 0`（`up = 0`）基准平面。
   - 凡涉及**绝对高度**（`HEIGHT`、`COM_POS(up)`）、**支撑期脚踝漂移**（`MAX_DRIFT`）、**净位移**（`DISPLACEMENT`）及**水平累计转角**（`YAW_ROTATION`），必须在地面世界坐标系 `W` 下计算三维轨迹，再投影至动作阶段朝向轴。
2. **解剖学朝向坐标系（Body Heading Frame, `B`）**：
   - 由骨盆与双肩水平投影确定表演者瞬时或阶段朝向：`up` 竖直向上，`left` 指表演者左侧，`front` 指表演者身体正前方。
   - 若坐标系标定或地面拟合失败，相关原语必须返回 `UNKNOWN`。

## 2. H36M-17 原始对象与派生对象

### 2.1 H36M-17 原始关节对象（闭合枚举）
仅以下 17 个小写规范名为合法原始关节对象：

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

### 2.2 几何与生物力学派生对象

| 派生对象名 | 计算公式定义 | 类型标识 |
| :--- | :--- | :--- |
| `hip_center` | `(left_hip + right_hip) / 2` | 几何派生 (`proxy=false`) |
| `shoulder_center` | `(left_shoulder + right_shoulder) / 2` | 几何派生 (`proxy=false`) |
| `body_axis` | 向量 `hip_center -> shoulder_center` | 几何派生 (`proxy=false`) |
| `pelvis_heading` | 向量 `right_hip -> left_hip` 绕 `+up` 顺时针旋转 `90deg` 的水平朝向向量 | 几何派生 (`proxy=false`) |
| `foot_len_est` | 双侧小腿长均值乘人体统计比例系数（默认 `0.68`） | 代理量 (`proxy=true`) |
| `com_est` | 按固定人体分段质量权重计算的整体重心三维坐标 | 代理量 (`proxy=true`) |
| `support_side` | 由 `com_est` 地面投影与双踝坐标推断的主承重侧（`left/right/both`） | 代理量 (`proxy=true`) |

## 3. 原语算子库（Primitives Specification）

所有原语在输入点缺失或置信度低于阈值时统一返回 `UNKNOWN`。每个原语均绑定唯一的**参数结构（Args Schema）**与**返回单位（Unit）**。

### 3.1 空间位置、相对高度与时序运动原语

| 原语名称 | 参数结构 (`args`) | 返回单位 (`unit`) | 严格定义与对应规则场景 |
| :--- | :--- | :--- | :--- |
| `POS` | `{object, axis}` | `norm` | 对象在 `up/left/front` 轴上的坐标 |
| `DIST` | `{a, b}` | `norm` | 同帧两点三维欧氏距离（可用于正踢腿脚踝与 `head/nose` 距离判定） |
| `HORIZONTAL_DIST` | `{a, b}` | `norm` | 地面水平面（忽略 `up`）上的两点距离 |
| `HEIGHT` | `{object}` | `norm` | 对象在地面世界坐标系 `W` 中的垂直高度 |
| `KNEE_LIFT_HEIGHT` | `{side}` | `norm` | `HEIGHT(side.knee) - HEIGHT(hip_center)`；正值表示提膝高于髋腰基准（覆盖编码 `03` 提膝未过腰） |
| `ANKLE_REL_HEIGHT` | `{side, ref}` | `norm` | `HEIGHT(side.ankle) - HEIGHT(ref)`；`ref` 取 `shoulder_center / hip_center / belly / head`（覆盖编码 `60/61/70/50`，`proxy=true`） |
| `DISPLACEMENT` | `{object, axis}` | `norm` | 阶段窗口末帧减首帧在地面世界坐标系下沿初始 `axis` 轴的净位移 |
| `MAX_DRIFT` | `{object}` | `norm` | 阶段窗口内对象在地面水平面偏离窗口首帧位置的最大欧氏距离（检测支撑期踝漂移 `82`） |
| `SPEED` | `{object}` | `norm/frame` | 相邻帧在地面世界坐标系下的三维速度幅值 |
| `STEP_COUNT` | `{}` | `count` | 阶段窗口内双踝交替触地迈步的次数（覆盖腾空飞脚/正踢腿“助跑超过 1 步”，`proxy=true`） |
| `LANDING_TIME_DIFF` | `{}` | `ms` | 跳跃接跌叉落地阶段，左右腿首次触地帧的时间差绝对值（覆盖“两腿依次落地”，`proxy=true`） |

### 3.2 角度、步型深度、身型与旋转原语

| 原语名称 | 参数结构 (`args`) | 返回单位 (`unit`) | 严格定义与对应规则场景 |
| :--- | :--- | :--- | :--- |
| `KNEE_ANGLE` | `{side}` | `deg` | `ANGLE(side.hip, side.knee, side.ankle)`，直腿为 `180deg` |
| `KNEE_BEND` | `{side}` | `deg` | `180deg - KNEE_ANGLE(side)`，直腿为 `0deg`，屈膝首选算子（覆盖 `12/14/60/61/71`） |
| `THIGH_VERTICAL_ANGLE` | `{side}` | `deg` | 大腿向量 `side.hip -> side.knee` 与向上竖直轴 `+up` 的夹角；直立为 `180deg`，水平蹲平为 `90deg`（对齐表-11 弓马步 `>115deg`、虚步 `>135deg`） |
| `THIGH_SPLIT_ANGLE` | `{}` | `deg` | `ANGLE(left_knee, hip_center, right_knee)`；两大腿展开夹角（覆盖编码 `01` 跌叉夹角 `<=45deg`） |
| `TRUNK_TILT` | `{axis}` | `deg` | `axis=up` 为 `body_axis` 与 `+up` 夹角；`axis=left/front` 为对应平面倾角（覆盖斜身/后仰 `16`） |
| `SPINE_BEND` | `{}` | `deg` | `180deg - ANGLE(hip_center, belly, neck)`；直背为 `0deg`，正值衡量含胸驼背/弓背（覆盖编码 `16`） |
| `HIP_ANGLE` | `{side}` | `deg` | `ANGLE(belly, side.hip, side.knee)`；衡量髋部折叠、翻臀与伸髋（覆盖编码 `16`） |
| `ELBOW_ANGLE` | `{side}` | `deg` | `ANGLE(side.shoulder, side.elbow, side.wrist)`（覆盖编码 `17` 直臂） |
| `SHOULDER_SHRUG` | `{side}` | `norm` | `HEIGHT(side.shoulder) - HEIGHT(neck)`（覆盖编码 `17` 耸肩） |
| `ELBOW_RAISE` | `{side}` | `norm` | `HEIGHT(side.elbow) - HEIGHT(side.wrist)`；结合肘高于肩腕连线衡量抬肘（覆盖编码 `17` 抬肘） |
| `YAW_ROTATION` | `{target}` | `deg` | 窗口内 `target`（取 `pelvis` 或 `support_ankle`）在水平面累计旋转角度绝对值（覆盖跳跃转体 `180..540deg` 及独立转体，`proxy=true`） |

### 3.3 站距、重心与平衡摇晃原语

| 原语名称 | 参数结构 (`args`) | 返回单位 (`unit`) | 严格定义与对应规则场景 |
| :--- | :--- | :--- | :--- |
| `STANCE_WIDTH` | `{}` | `norm` | `HORIZONTAL_DIST(left_ankle, right_ankle)` |
| `STANCE_FOOT_RATIO` | `{}` | `ratio` | `STANCE_WIDTH / foot_len_est`；双脚横向间距与本人脚长比值（覆盖编码 `13` 马步 `>3.5 ratio`，`proxy=true`） |
| `KNEE_FORWARD_OFFSET` | `{side}` | `norm` | 膝点相对同侧踝在 `front` 轴有符号投影距离（弓步前膝过冲粗筛，`proxy=true`） |
| `KNEE_MEDIAL_OFFSET` | `{side}` | `norm` | 膝点相对同侧髋踝连线向身体中线内扣的偏移距离（虚步/上步膝内扣粗筛，`proxy=true`） |
| `SWAY_ANGLE` | `{}` | `deg` | 稳定支撑期内躯干在竖直平面内**双向或多向往返摆动**的最大角位移（`1..45deg` 小晃动 `80`，`>45deg` 大晃动 `81`） |
| `BALANCE_STILL_MS` | `{}` | `ms` | 平衡动作自首次进入全身静止状态起，连续保持静止的毫秒时长（覆盖编码 `87` 平衡不足 `2000ms`） |
| `FALL_SUSPECTED` | `{}` | `bool` | `COM_POS(up)` 快速跌落、`TRUNK_TILT(up) > 65deg` 且失稳（覆盖编码 `84` 倒地粗筛，`proxy=true`） |

### 3.4 图像模型视觉原语（`V_*`，仅徒手太极拳）

| 原语名称 | 参数结构 (`args`) | 返回单位 (`unit`) | 目标值类型 (`target`) | 视觉语义与对应规则编码 |
| :--- | :--- | :--- | :--- | :--- |
| `V_HAND_FORM` | `{side}` | `label` | `palm / fist / hook / other` | 手型分类（覆盖编码 `10/11`） |
| `V_HAND_DEFECT` | `{side}` | `label` | `uneven_fist / finger_gap / bent_finger / convex_palm / none` | 手型细粒度错误标签（直接对应编码 `10` 与 `11`） |
| `V_FOOT_SLAP_HIT` | `{side}` | `bool` | `true / false` | 摆莲、拍脚、飞脚、旋风脚中手掌是否准确击中脚面（覆盖编码 `61/70` 击拍落空） |
| `V_FOOT_OUTTURN` | `{side}` | `deg` | `float` | 脚尖相对身体前进方向的有符号水平夹角：正值为外展，负值为内扣（覆盖跌叉 `01` 与仆步 `14` 内扣） |
| `V_KNEE_OVER_TOE` | `{side}` | `bool` | `true / false` | 膝盖前端在水平投影上明显超过同侧脚尖（覆盖编码 `12` 弓步前膝过脚尖） |
| `V_KNEE_TOE_ALIGNED` | `{side}` | `bool` | `true / false` | 支撑膝弯曲方向与同侧脚尖朝向对正（覆盖虚步 `15`、上步 `18`） |
| `V_HEEL_LIFT` | `{side}` | `bool` | `true / false` | 脚跟明显离地而脚前掌着地（`true` 触发弓步后脚跟离地 `12`；`false` 触发虚步前脚跟着地 `15`） |
| `V_FULL_FOOT_GROUNDED` | `{side}` | `bool` | `true / false` | 全脚掌完整贴地（`false` 触发仆步未全脚掌着地 `14`） |
| `V_FOOT_SLIDE` | `{side}` | `bool` | `true / false` | 支撑期脚掌与地面接触时发生平移滑动（覆盖编码 `82` 移动） |
| `V_FOOT_PIVOT` | `{side}` | `bool` | `true / false` | 支撑期或跳跃落地后脚跟/脚尖发生碾转（覆盖编码 `82` 及连接难度落地碾动） |
| `V_FOOT_RECOVERY_STEP` | `{side}` | `bool` | `true / false` | 单脚独立失稳时非支撑脚提前下落迈步（覆盖编码 `82` 移动与连接失败） |
| `V_FOOT_SKIP` | `{side}` | `bool` | `true / false` | 支撑期或落地时脚短暂离地跳动（覆盖编码 `83` 跳动） |
| `V_GROUND_CONTACT` | `{part}` | `bool` | `true / false` | 指定部位与地面可见接触（覆盖跌叉前脚掌触地 `01`、后插腿触地 `51`、倒地 `84`） |
| `V_UNEXPECTED_SUPPORT` | `{part}` | `bool` | `true / false` | 失衡时手、肘、膝、头或非支撑脚触地借力（覆盖编码 `83` 附加支撑） |
| `V_OUT_OF_BOUNDS` | `{}` | `bool` | `true / false` | 身体任何一部分触及场地白线外地面（覆盖编码 `88` 出界） |
| `V_FOOT_ROTATION` | `{side}` | `deg` | `float` | 跳跃起跳瞬间至落地瞬间，起跳脚/落地脚（脚跟-脚尖连线）的水平转体夹角 |

## 4. 扣分编码与分值注册表（Deduction Registry）

Schema 校验器在运行时强制核对 `(code, group, points, scope)` 四元组必须与下表完全一致：

| 编码 (`code`) | 评分组 (`group`) | 分值 (`points`) | 去重作用域 (`scope`) | 规则名称与扣分含义 |
| :--- | :--- | :--- | :--- | :--- |
| `10` | `E` | `0.10` | `technique` | **拳型错误**：拳面不平 |
| `11` | `E` | `0.10` | `technique` | **掌型错误**：指间隙过大、手指明显弯曲或掌心外凸 |
| `12` | `E` | `0.10` | `technique` | **弓步规格错误**：前腿膝部超出脚尖；后腿明显弯曲或脚跟离地 |
| `13` | `E` | `0.10` | `technique` | **马步/偏马步错误**：两脚横向间距过大（超过本人脚长 3.5 倍） |
| `14` | `E` | `0.10` | `technique` | **仆步规格错误**：仆腿未伸直；仆腿全脚掌未内扣着地（脚掌掀起或踝角 `>90deg`） |
| `15` | `E` | `0.10` | `technique` | **虚步规格错误**：支撑腿膝与脚尖未对正；前脚跟着地 |
| `16` | `E` | `0.10` | `technique` | **身型错误**：翻臀弓背；伸髋后仰 |
| `17` | `E` | `0.10` | `technique` | **手法错误**：直臂、耸肩、抬肘 |
| `18` | `E` | `0.10` | `technique` | **上步错误**：上步时支撑腿膝与脚尖未对正 |
| `01` | `E` | `0.10` | `technique` | **跌叉错误**：前脚掌内扣触地；两大腿夹角 `<=45deg` |
| `03` | `E` | `0.10` | `technique` | **提膝独立错误**：提腿膝部未过腰 |
| `50` | `E` | `0.10` | `technique` | **前举腿低势平衡错误**：前举腿低于水平 |
| `51` | `E` | `0.10` | `technique` | **后插腿低势平衡错误**：插出腿脚触地 |
| `60` | `E` | `0.10` | `technique` | **蹬脚/分脚错误**：支撑腿明显弯曲；上举腿未伸直 |
| `61` | `E` | `0.10` | `technique` | **摆莲/拍脚错误**：摆腿弯曲；击拍落空；脚低于肩 |
| `70` | `E` | `0.10` | `technique` | **腾空飞脚/旋风脚/腾空摆莲规格错误**：击拍落空；击响腿脚尖未过肩 |
| `71` | `E` | `0.10` | `technique` | **腾空正踢腿规格错误**：悬垂腿弯曲 |
| `80` | `E` | `0.10` | `event` | **小晃动**：支撑状态上体双向或多向位移 `<=45deg` |
| `81` | `E` | `0.20` | `event` | **大晃动**：支撑状态上体位移 `>45deg` |
| `82` | `E` | `0.10` | `event` | **脚碾动、移动**：双脚支撑位移、脚底碾转，或单脚重心不稳非支撑脚下落移动 |
| `83` | `E` | `0.20` | `event` | **跳动、附加支撑**：失去平衡跳动，或手、肘、膝、头、非支撑脚触地借力 |
| `84` | `E` | `0.30` | `event` | **倒地**：双手、上臂、肩背、臀部、躯干触地 |
| `87` | `E` | `0.10` | `event` | **平衡时间不足**：平衡动作静止保持时间不足 2 秒（`<2000ms`） |
| `88` | `E` | `0.10` | `event` | **出界**：身体任何一部分触及场地线外地面 |
| `89` | `E` | `0.10` | `event` | **遗忘**：套路动作遗忘一次 |
| `D_STANCE_115` | `D` | `0.10` | `technique` | **弓/马/偏马步难度不符**：屈蹲腿大腿轴线与垂直轴线夹角 `>115deg` |
| `D_STANCE_135` | `D` | `0.10` | `technique` | **虚步/上步难度不符**：支撑腿大腿轴线与垂直轴线夹角 `>135deg` |
| `D_SQUAT_INCOMPLETE` | `D` | `0.10` | `technique` | **仆步/前举腿平衡难度不符**：屈蹲支撑腿未全蹲 |
| `D_BALANCE_51` | `D` | `0.15` | `technique` | **后插腿平衡难度不符**：支撑腿大腿高于水平 |
| `D_KICK_LOW` | `D` | `0.10` | `technique` | **蹬脚/分脚/摆莲难度不符**：上举腿脚跟或摆腿脚低于肩 |
| `D_JUMP_CD` | `D` | `0.15` | `technique` | **C/D级跳跃难度未完成**：助跑超1步、起跳前停顿/移步、未过腰/未触额、转体不足（180°） |
| `D_JUMP_EFG` | `D` | `0.20` | `technique` | **E/F/G级跳跃难度未完成**：起跳不符规定、击响腿未过腰、转体度数不足（360°/450°/540°） |

## 5. 扩展强克林四值逻辑（Strong Kleene $\mathcal{L}_4$）与骨骼优先求值语义

为保证不同执行器在面对缺失数据和按需视觉唤醒时产生 100% 确定性的相同结果，本语言严格采用**扩展强克林四值逻辑（Extended Strong Kleene Four-Valued Logic, $\mathcal{L}_4$）**。

### 5.1 原子条件（Clause）的四值真值域
每个原子条件 `c` 求值后返回四值集合 $\mathcal{L}_4 = \{\mathbf{T}, \mathbf{F}, \mathbf{V}, \mathbf{U}\}$ 中的唯一状态：
1. $\mathbf{T}$（`TRUE`）：违规条件已确认命中（如实测 `KNEE_BEND(rear) = 28deg > 20deg`）。
2. $\mathbf{F}$（`FALSE`）：违规条件确认未发生（动作合乎规范）。
3. $\mathbf{V}$（`NEEDS_VISION`）：该子条件为 `V_*` 视觉原语，当前处于第一阶段纯骨骼推理，视觉证据尚未接入，但唤醒图像模型后可求解。
4. $\mathbf{U}$（`UNKNOWN`）：骨骼关键点缺失/低置信度，或视觉模型已接入但因遮挡/出画仍无法判定的**不可恢复未知状态**。

### 5.2 逻辑组合真值表与吸收优先级（`ALL` / `ANY` / `NOT`）

- **一元取反算子 `NOT`（$\neg$）**：
  $$\neg \mathbf{T} = \mathbf{F}, \quad \neg \mathbf{F} = \mathbf{T}, \quad \neg \mathbf{V} = \mathbf{V}, \quad \neg \mathbf{U} = \mathbf{U}$$

- **合取算子 `ALL`（`AND`, $\land$ —— 所有子条件同时满足才构成违规）**：
  - **短路吸收律**：$\mathbf{F}$ 为绝对零元（只要有一个条件确认不违规，整条 `ALL` 规则绝无可能违规，直接判定 `PASS`）。
  - **不可恢复优先律**：在无 $\mathbf{F}$ 时，$\mathbf{U}$ 吸收 $\mathbf{V}$（因为已有一个必需条件永久不可知 $\mathbf{U}$，即便花算力去跑视觉模型把 $\mathbf{V}$ 变成 $\mathbf{T}$，最终合取结果依然是 $\mathbf{U}$，故直接返回 `UNKNOWN`，不发起无效视觉请求）。

| `ALL` ($a \land b$) | $\mathbf{T}$ | $\mathbf{V}$ (`NEEDS_VISION`) | $\mathbf{U}$ (`UNKNOWN`) | $\mathbf{F}$ |
| :--- | :---: | :---: | :---: | :---: |
| $\mathbf{T}$ | $\mathbf{T}$ | $\mathbf{V}$ | $\mathbf{U}$ | $\mathbf{F}$ |
| $\mathbf{V}$ (`NEEDS_VISION`) | $\mathbf{V}$ | $\mathbf{V}$ | $\mathbf{U}$ | $\mathbf{F}$ |
| $\mathbf{U}$ (`UNKNOWN`) | $\mathbf{U}$ | $\mathbf{U}$ | $\mathbf{U}$ | $\mathbf{F}$ |
| $\mathbf{F}$ | $\mathbf{F}$ | $\mathbf{F}$ | $\mathbf{F}$ | $\mathbf{F}$ |

- **析取算子 `ANY`（`OR`, $\lor$ —— 任一子条件满足即构成违规）**：
  - **短路吸收律**：$\mathbf{T}$ 为绝对零元（只要有一个子条件确认违规，如骨骼已测出后腿弯曲，无论其余视觉条件是 $\mathbf{V}$ 还是 $\mathbf{U}$，整条规则立即判定 `VIOLATION`）。
  - **可恢复唤醒优先律**：在无 $\mathbf{T}$ 时，$\mathbf{V}$ 吸收 $\mathbf{U}$（只要还有一个视觉条件 $\mathbf{V}$ 有望通过唤醒图像模型测出 $\mathbf{T}$ 从而触发扣分，就优先返回 `NEEDS_VISION` 唤醒视觉，而非提前放弃为 `UNKNOWN`）。

| `ANY` ($a \lor b$) | $\mathbf{T}$ | $\mathbf{V}$ (`NEEDS_VISION`) | $\mathbf{U}$ (`UNKNOWN`) | $\mathbf{F}$ |
| :--- | :---: | :---: | :---: | :---: |
| $\mathbf{T}$ | $\mathbf{T}$ | $\mathbf{T}$ | $\mathbf{T}$ | $\mathbf{T}$ |
| $\mathbf{V}$ (`NEEDS_VISION`) | $\mathbf{T}$ | $\mathbf{V}$ | $\mathbf{V}$ | $\mathbf{V}$ |
| $\mathbf{U}$ (`UNKNOWN`) | $\mathbf{T}$ | $\mathbf{V}$ | $\mathbf{U}$ | $\mathbf{U}$ |
| $\mathbf{F}$ | $\mathbf{T}$ | $\mathbf{V}$ | $\mathbf{U}$ | $\mathbf{F}$ |

### 5.3 骨骼优先短路求值协议（Skeletal-First Evaluation Protocol）
执行器在评估单条 `RuleNode` 时，必须按以下确定性顺序执行：
1. **子条件重排**：将 `evaluation.clauses` 内部按 **[三维骨骼原语 $\to$ 已缓存视觉原语 $\to$ 待请求视觉原语]** 排序后依次求值。
2. **短路裁剪**：
   - 在 `ANY` 规则中，一旦骨骼原语求值为 $\mathbf{T}$，立即短路返回规则级 `result = "VIOLATION"`，不再触发后续视觉原语的 `REQUEST_VISION`。
   - 在 `ALL` 规则中，一旦骨骼原语求值为 $\mathbf{F}$，立即短路返回 `result = "PASS"`；一旦骨骼原语求值为 $\mathbf{U}$，立即短路返回 `result = "UNKNOWN"`，均不触发无效视觉调用。
3. **规则级状态映射**：最终组合真值 $\mathbf{T} \mapsto \text{"VIOLATION"}$，$\mathbf{F} \mapsto \text{"PASS"}$，$\mathbf{V} \mapsto \text{"NEEDS\_VISION"}$，$\mathbf{U} \mapsto \text{"UNKNOWN"}$。

## 6. 新型 JSON-AST 语言结构与必要条目设计

### 6.1 顶层与各层级必要字段说明

| 层级 | 字段名 | 类型 | 必填 | 设计目的与强类型约束说明 |
| :--- | :--- | :--- | :--- | :--- |
| **Root** | `dsl_version` | `string` | 是 | 固定为 `"H36M17-TAICHI-JSON-2.0"` |
| **Root** | `input_spec` | `InputSpec` | 是 | 含 `skeleton: "h36m-17"`, `fps > 0`, `vision_mode: "demand_driven" \| "full"` |
| **Root** | `chapter` | `ChapterSpec` | 是 | 含 `chapter_id`（正则校验）、`action_name`、`action_code` |
| **Root** | `rules` | `List[RuleNode]` | 是 | 章节内规则列表；校验器强制校验 `rule_id` 与 `deduction.item_id` 全局唯一 |
| **Rule** | `rule_id` | `string` | 是 | 章节内唯一英文语义 ID（如 `"bow_left_front_knee_over_toe"`） |
| **Rule** | `phase` | `string` | 是 | 动作阶段名（如 `"step_in"`, `"hold_left_bow"`, `"takeoff"`, `"landing_hold"`） |
| **Rule** | `frame_window` | `[int, int]` | 是 | 闭区间 `[start, end]`，强制校验 `0 <= start <= end` |
| **Rule** | `stance_binding` | `StanceBinding` | 是 | 显式绑定 `front`, `rear`, `support`；校验器强制拦截 `front == rear` 或 `airborne` 下绑定前后腿等矛盾状态 |
| **Rule** | `evaluation` | `EvaluationSpec` | 是 | 含 `logic`（`"ALL"` 或 `"ANY"`）及基于 `primitive` 判别联合（Discriminated Union）的 `clauses` |
| **Clause** | `primitive` | `Literal[...]` | 是 | 作为 Discriminated Union 判别键，决定该 Clause 专属的 `args`、`op`、`target` 和 `unit` 类型 |
| **Clause** | `args` | `StrictModel` | 是 | 按原语精确匹配专属参数模型（如 `SideArgs`, `AxisArgs`, `AnkleRelHeightArgs`），无兜底 `str` 且 `extra="forbid"` |
| **Clause** | `op`, `target`, `unit` | 原语专属绑定 | 是 | 数值原语禁止比较 `bool`；`BETWEEN` 强制要求 `[low, high]` 且 `low <= high`；`IN` 仅限枚举标签列表 |
| **Rule** | `deduction` | `DeductionSpec` | 是 | 强制对照第 4 节注册表校验 `(code, group, points, scope)` 四元组一致性 |
| **Rule** | `uncertainty` | `UncertaintySpec` | 是 | 若 `clauses` 含 `V_*` 原语，强制要求配置 `on_unavailable` 且其 `frame_window` 与规则窗口一致 |

### 6.2 完整输入规则 JSON-AST 实例

```json
{
  "dsl_version": "H36M17-TAICHI-JSON-2.0",
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
      "rule_id": "yema_left_bow_knee_over_toe_e",
      "phase": "hold_left_bow",
      "frame_window": [45, 90],
      "stance_binding": {
        "front": "left",
        "rear": "right",
        "support": "left"
      },
      "evaluation": {
        "logic": "ANY",
        "clauses": [
          {
            "primitive": "V_KNEE_OVER_TOE",
            "args": { "side": "front" },
            "op": "==",
            "target": true,
            "unit": "bool"
          },
          {
            "primitive": "KNEE_BEND",
            "args": { "side": "rear" },
            "op": ">",
            "target": 20.0,
            "unit": "deg"
          },
          {
            "primitive": "V_HEEL_LIFT",
            "args": { "side": "rear" },
            "op": "==",
            "target": true,
            "unit": "bool"
          }
        ]
      },
      "deduction": {
        "item_id": "bow_left_stance_spec_error",
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

为确保前端展示一致、事件去重可审计、多规则触发同一扣分项时计分唯一，规则引擎输出严格分为**单条规则求值结果（`RuleEvalResult`）**与**章节级聚合报告（`ChapterEvalReport`）**两级结构。

### 7.1 单条规则求值结果字段规范（`RuleEvalResult`）

| 字段名 | 类型 | 必填 | 含义与取值约束 |
| :--- | :--- | :--- | :--- |
| `rule_id` | `string` | 是 | 对应输入规则的唯一 ID |
| `chapter_id`, `chapter_instance_id` | `string` | 是 | 动作章节标识与当前套路中的动作实例唯一 ID（如 `"yang_yema_fenzong#1"`） |
| `item_id` | `string` | 是 | 规则对应的扣分小项 ID |
| `phase`, `frame_range` | `string`, `[int, int]` | 是 | 判定阶段名与帧区间 `[start, end]` |
| `result` | `Literal` | 是 | `"VIOLATION" \| "PASS" \| "NEEDS_VISION" \| "UNKNOWN" \| "UNRESOLVABLE"` |
| `clause_traces` | `List[ClauseTrace]` | 是 | 记录每个原子条件的实测值 `actual_value`、单位、目标阈值、置信度、数据源（`skeleton_3d/vision_2d`）、是否代理量及单条件四值状态（`T/F/V/U`） |
| `proxy_used`, `vision_required` | `bool` | 是 | 本次判定是否依赖了生物力学代理量、是否依赖了视觉证据 |
| `explanation` | `Optional[str]` | 条件 | 当 `result` 为 `UNKNOWN/NEEDS_VISION/UNRESOLVABLE/VIOLATION` 时必填的自然语言诊断说明 |
| `vision_request` | `Optional[VisionRequestSpec]` | 条件 | 当 `result == "NEEDS_VISION"` 时必填，含 `target_parts`、`frame_window`、`instruction` |
| `event_id` | `Optional[str]` | 条件 | 仅 `result == "VIOLATION"` 时生成（格式：`<chapter_instance_id>:<code_or_item>:<peak_frame>`） |
| `deduction_code`, `score_group`, `deduction_scope` | `string` | 是 | 对应注册表的 `code`、`group`（`E/D`）与 `scope`（`technique/event`） |
| `raw_deduction_points` | `float` | 是 | 未去重前的原始触发扣分值（仅 `VIOLATION` 时 `>0`，其余状态恒为 `0.0`） |
| `effective_deduction_points` | `float` | 是 | **经章节级去重聚合后的实际生效扣分值**（被去重吸收时为 `0.0`） |
| `counted_events` | `int` | 是 | 经去重后计入总扣分的有效事件数（`0` 或 `>=1`） |
| `deduplicated_by` | `Optional[str]` | 否 | 若本条违规被同章节内另一条同编码/同类别规则去重吸收，记录吸收方的 `event_id` |

### 7.2 多规则触发同一扣分项的去重与计分聚合算法

对照《国际太极拳竞赛规则》第 34 条，章节聚合器（Aggregator）对同一 `chapter_instance_id` 下所有 `result == "VIOLATION"` 的规则执行以下两级去重：

1. **按动作单式去重（`deduction_scope == "technique"`，覆盖编码 `01~71` 及 `D_*`）**：
   - **同编码去重（《规则》34.1.2 / 34.1.3）**：在一个动作实例（如一次“左右野马分鬃” `yang_yema_fenzong#1`）内，无论多少条规则触发同一个 `deduction_code`（例如左弓步和右弓步均触发 `code="12"`，或同一弓步中同时触发前膝过脚尖与后腿弯曲），按 `frame_range` 起始帧排序，**仅第一条触发的违规规则保留 `effective_deduction_points = points, counted_events = 1`**；后续所有相同 `deduction_code` 的违规规则全部标记 `effective_deduction_points = 0.0, counted_events = 0, deduplicated_by = <first_event_id>`。
   - **单式多规格错误封顶（《规则》34.1.1“一个动作中出现多种规格错误，只扣 0.10 分”）**：在单个动作实例内，所有属于 `E` 组规格错误（编码 `01~71`）的有效扣分总和上限封顶为 `0.10` 分（若需严格按 34.1.1 单式封顶，聚合器将第二个及之后的规格编码同样标记 `deduplicated_by` 首条规格错误事件；可通过 `aggregation_policy = "per_code" | "strict_single_spec_cap"` 配置切换）。
2. **按独立时间事件去重（`deduction_scope == "event"`，覆盖其它错误 `80~89`）**：
   - 根据《规则》第 34.2.6 条“一个动作中连续出现两个以上其他错误，应累计扣分”：
   - 其它错误（晃动 `80/81`、脚碾动/移动 `82`、跳动/附加支撑 `83`、倒地 `84`）按时间窗口聚类：若两个同类失衡事件（如 `80` 与 `81`，或两次 `82`）的帧区间重叠或间隔小于合并阈值 `merge_gap_frames`（默认 `12 frames`），合并为同一个物理失衡事件，仅取其中最高分值（如同时触发小晃动 `0.10` 与大晃动 `0.20`，生效 `0.20` 分，低分项标记 `deduplicated_by` 高分项）；若帧间隔大于阈值，则作为多次独立失误全额累加。

### 7.3 执行结果 JSON 实例（含审计轨迹与去重标记）

```json
{
  "chapter_id": "yang_yema_fenzong",
  "chapter_instance_id": "yang_yema_fenzong#1",
  "aggregation_policy": "per_code",
  "chapter_status": "COMPLETED",
  "total_e_deduction": 0.10,
  "total_d_deduction": 0.10,
  "rule_results": [
    {
      "rule_id": "yema_left_bow_knee_over_toe_e",
      "chapter_id": "yang_yema_fenzong",
      "chapter_instance_id": "yang_yema_fenzong#1",
      "item_id": "bow_left_stance_spec_error",
      "phase": "hold_left_bow",
      "frame_range": [45, 90],
      "result": "VIOLATION",
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
        },
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
      ],
      "proxy_used": false,
      "vision_required": false,
      "explanation": "经骨骼优先短路求值（ANY 规则）：后腿（右腿）屈膝角达 27.4deg > 20.0deg（状态 T），直接确认弓步后腿弯曲违规，无需唤醒视觉模型",
      "vision_request": null,
      "event_id": "yang_yema_fenzong#1:12:68",
      "deduction_code": "12",
      "score_group": "E",
      "deduction_scope": "technique",
      "raw_deduction_points": 0.10,
      "effective_deduction_points": 0.10,
      "counted_events": 1,
      "deduplicated_by": null
    },
    {
      "rule_id": "yema_right_bow_knee_over_toe_e",
      "chapter_id": "yang_yema_fenzong",
      "chapter_instance_id": "yang_yema_fenzong#1",
      "item_id": "bow_right_stance_spec_error",
      "phase": "hold_right_bow",
      "frame_range": [110, 155],
      "result": "VIOLATION",
      "clause_traces": [
        {
          "primitive": "KNEE_BEND",
          "args": { "side": "rear" },
          "actual_value": 24.1,
          "op": ">",
          "target": 20.0,
          "unit": "deg",
          "confidence": 0.94,
          "source": "skeleton_3d",
          "proxy": false,
          "state": "T"
        }
      ],
      "proxy_used": false,
      "vision_required": false,
      "explanation": "右弓步定式期后腿（左腿）屈膝角 24.1deg > 20.0deg，但因同章节实例内编码 12 已扣分，按 scope=technique 去重吸收",
      "vision_request": null,
      "event_id": "yang_yema_fenzong#1:12:132",
      "deduction_code": "12",
      "score_group": "E",
      "deduction_scope": "technique",
      "raw_deduction_points": 0.10,
      "effective_deduction_points": 0.00,
      "counted_events": 0,
      "deduplicated_by": "yang_yema_fenzong#1:12:68"
    }
  ]
}
```

## 8. 完整强类型 Pydantic v2 Schema（含输入 AST、输出结果与四值求值器）

```python
from typing import Annotated, Dict, List, Literal, Optional, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator

# ==========================================
# Part A: 基础闭合枚举与扣分注册表
# ==========================================
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

# ==========================================
# Part B: 强类型输入规则 AST Schema
# ==========================================
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class EmptyArgs(StrictModel):
    pass

class SideArgs(StrictModel):
    side: SideLiteral

class AxisArgs(StrictModel):
    axis: AxisLiteral

class ObjectArgs(StrictModel):
    object: ObjectLiteral

class ObjectAxisArgs(StrictModel):
    object: ObjectLiteral
    axis: AxisLiteral

class PairObjectArgs(StrictModel):
    a: ObjectLiteral
    b: ObjectLiteral

class AnkleRelHeightArgs(StrictModel):
    side: SideLiteral
    ref: RefPartLiteral

class YawRotationArgs(StrictModel):
    target: YawTargetLiteral

class VisionPartArgs(StrictModel):
    part: VisionPartLiteral

NumericScalar = Union[StrictFloat, StrictInt]
NumericTarget = Union[NumericScalar, List[NumericScalar]]
NumericOp = Literal["==", "!=", "<", "<=", ">", ">=", "BETWEEN"]

class NumericClauseBase(StrictModel):
    op: NumericOp
    target: NumericTarget

    @model_validator(mode="after")
    def check_numeric_op_target(self) -> "NumericClauseBase":
        if self.op == "BETWEEN":
            if not isinstance(self.target, list) or len(self.target) != 2:
                raise ValueError("BETWEEN 运算符的 target 必须是长度为 2 的数值数组 [low, high]")
            if self.target[0] > self.target[1]:
                raise ValueError(f"BETWEEN 区间下界 {self.target[0]} 不能大于上界 {self.target[1]}")
        else:
            if isinstance(self.target, list):
                raise ValueError(f"运算符 {self.op} 的 target 必须是单个数值，不能是数组")
        return self

class BoolClauseBase(StrictModel):
    op: Literal["==", "!="]
    target: StrictBool
    unit: Literal["bool"]

class SideDegClause(NumericClauseBase):
    primitive: Literal[
        "KNEE_ANGLE", "KNEE_BEND", "THIGH_VERTICAL_ANGLE",
        "HIP_ANGLE", "ELBOW_ANGLE", "V_FOOT_OUTTURN", "V_FOOT_ROTATION"
    ]
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
    primitive: Literal[
        "KNEE_LIFT_HEIGHT", "SHOULDER_SHRUG", "ELBOW_RAISE",
        "KNEE_FORWARD_OFFSET", "KNEE_MEDIAL_OFFSET"
    ]
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
    primitive: Literal[
        "V_FOOT_SLAP_HIT", "V_KNEE_OVER_TOE", "V_KNEE_TOE_ALIGNED",
        "V_HEEL_LIFT", "V_FULL_FOOT_GROUNDED", "V_FOOT_SLIDE",
        "V_FOOT_PIVOT", "V_FOOT_RECOVERY_STEP", "V_FOOT_SKIP"
    ]
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

    @model_validator(mode="after")
    def check_label_op(self) -> "HandFormLabelClause":
        if self.op == "IN" and not isinstance(self.target, list):
            raise ValueError("IN 运算符的 target 必须是枚举标签列表")
        if self.op in ("==", "!=") and isinstance(self.target, list):
            raise ValueError(f"{self.op} 运算符的 target 必须是单个枚举标签")
        return self

class HandDefectLabelClause(StrictModel):
    primitive: Literal["V_HAND_DEFECT"]
    args: SideArgs
    op: Literal["==", "!=", "IN"]
    target: Union[HandDefectLabel, List[HandDefectLabel]]
    unit: Literal["label"]

    @model_validator(mode="after")
    def check_defect_op(self) -> "HandDefectLabelClause":
        if self.op == "IN" and not isinstance(self.target, list):
            raise ValueError("IN 运算符的 target 必须是枚举标签列表")
        if self.op in ("==", "!=") and isinstance(self.target, list):
            raise ValueError(f"{self.op} 运算符的 target 必须是单个枚举标签")
        return self

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

class StanceBinding(StrictModel):
    front: Literal["left", "right", "none"]
    rear: Literal["left", "right", "none"]
    support: Literal["left", "right", "both", "airborne"]

    @model_validator(mode="after")
    def check_stance_consistency(self) -> "StanceBinding":
        if (self.front == "none") != (self.rear == "none"):
            raise ValueError("front 与 rear 必须同时为 'none'，或分别为 'left' 和 'right'")
        if self.front != "none" and self.front == self.rear:
            raise ValueError(f"front 与 rear 不能同为 '{self.front}'")
        if self.support == "airborne" and self.front != "none":
            raise ValueError("当 support='airborne'（腾空期）时，front 和 rear 必须为 'none'")
        return self

class EvaluationSpec(StrictModel):
    logic: Literal["ALL", "ANY"]
    clauses: List[ClauseUnion] = Field(min_length=1)

class DeductionSpec(StrictModel):
    item_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    code: DeductionCodeLiteral
    points: Literal[0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    group: Literal["E", "D"]
    scope: Literal["technique", "event"]

    @model_validator(mode="after")
    def check_registry_alignment(self) -> "DeductionSpec":
        exp_group, exp_points, exp_scope = DEDUCTION_REGISTRY[self.code]
        if (self.group, self.points, self.scope) != (exp_group, exp_points, exp_scope):
            raise ValueError(
                f"编码 {self.code} 的扣分配置必须为 group='{exp_group}', points={exp_points}, scope='{exp_scope}'"
            )
        return self

class VisionRequestSpec(StrictModel):
    action: Literal["REQUEST_VISION"] = "REQUEST_VISION"
    target_parts: List[VisionPartLiteral] = Field(min_length=1)
    frame_window: List[StrictInt] = Field(min_length=2, max_length=2)
    instruction: str = Field(min_length=5)

class UncertaintySpec(StrictModel):
    on_unavailable: Optional[VisionRequestSpec] = None
    on_unknown: str = Field(min_length=10)

class RuleNode(StrictModel):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    phase: str = Field(min_length=1)
    frame_window: List[StrictInt] = Field(min_length=2, max_length=2)
    stance_binding: StanceBinding
    evaluation: EvaluationSpec
    deduction: DeductionSpec
    uncertainty: UncertaintySpec

    @model_validator(mode="after")
    def check_rule_semantics(self) -> "RuleNode":
        start_f, end_f = self.frame_window
        if start_f < 0 or start_f > end_f:
            raise ValueError(f"frame_window 必须满足 0 <= start <= end，当前为 {self.frame_window}")

        uses_vision = False
        uses_front_rear = False
        for c in self.evaluation.clauses:
            if c.primitive.startswith("V_"):
                uses_vision = True
            args_dict = c.args.model_dump()
            for val in args_dict.values():
                if isinstance(val, str) and (val in ("front", "rear") or val.startswith(("front_", "rear_"))):
                    uses_front_rear = True

        if uses_front_rear and self.stance_binding.front == "none":
            raise ValueError(f"规则 {self.rule_id} 的原语使用了 front/rear，但 stance_binding 未绑定前后腿")

        if uses_vision and self.uncertainty.on_unavailable is None:
            raise ValueError(f"规则 {self.rule_id} 使用了 V_* 视觉原语，必须配置 uncertainty.on_unavailable")

        if self.uncertainty.on_unavailable is not None:
            if self.uncertainty.on_unavailable.frame_window != self.frame_window:
                raise ValueError("on_unavailable.frame_window 必须与规则的 frame_window 一致")

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
    dsl_version: Literal["H36M17-TAICHI-JSON-2.0"] = "H36M17-TAICHI-JSON-2.0"
    input_spec: InputSpec
    chapter: ChapterSpec
    rules: List[RuleNode] = Field(min_length=1)

    @model_validator(mode="after")
    def check_uniqueness(self) -> "RootSpec":
        rule_ids = [r.rule_id for r in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError(f"章节内存在重复的 rule_id: {rule_ids}")
        item_ids = [r.deduction.item_id for r in self.rules]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError(f"章节内存在重复的 deduction.item_id: {item_ids}")
        return self

# ==========================================
# Part C: 强克林四值逻辑求值器与执行结果 Schema
# ==========================================
def combine_kleene_l4(logic: Literal["ALL", "ANY"], states: List[TruthStateLiteral]) -> EvalResultLiteral:
    """严格按照第 5.2 节扩展强克林四值逻辑表合成规则级结果"""
    if logic == "ANY":
        if "T" in states:
            return "VIOLATION"
        if "V" in states:
            return "NEEDS_VISION"
        if "U" in states:
            return "UNKNOWN"
        return "PASS"
    else:  # logic == "ALL"
        if "F" in states:
            return "PASS"
        if "U" in states:
            return "UNKNOWN"
        if "V" in states:
            return "NEEDS_VISION"
        return "VIOLATION"

class ClauseTrace(StrictModel):
    primitive: str
    args: Dict[str, str]
    actual_value: Optional[Union[float, int, bool, str]] = None
    op: str
    target: Union[float, int, bool, str, List[float], List[str]]
    unit: str
    confidence: Optional[float] = None
    source: Literal["skeleton_3d", "vision_2d"]
    proxy: bool
    state: TruthStateLiteral

class RuleEvalResult(StrictModel):
    rule_id: str
    chapter_id: str
    chapter_instance_id: str
    item_id: str
    phase: str
    frame_range: List[StrictInt] = Field(min_length=2, max_length=2)
    result: EvalResultLiteral
    clause_traces: List[ClauseTrace]
    proxy_used: bool
    vision_required: bool
    explanation: Optional[str] = None
    vision_request: Optional[VisionRequestSpec] = None
    event_id: Optional[str] = None
    deduction_code: DeductionCodeLiteral
    score_group: Literal["E", "D"]
    deduction_scope: Literal["technique", "event"]
    raw_deduction_points: float = Field(ge=0.0)
    effective_deduction_points: float = Field(ge=0.0)
    counted_events: StrictInt = Field(ge=0)
    deduplicated_by: Optional[str] = None

    @model_validator(mode="after")
    def check_result_invariants(self) -> "RuleEvalResult":
        if self.result == "VIOLATION":
            if self.raw_deduction_points <= 0 or self.event_id is None:
                raise ValueError("VIOLATION 状态下 raw_deduction_points 必须 > 0 且必须生成 event_id")
        else:
            if self.raw_deduction_points != 0.0 or self.effective_deduction_points != 0.0 or self.counted_events != 0:
                raise ValueError(f"非 VIOLATION 状态（{self.result}）不得产生任何扣分或计次")
        if self.result == "NEEDS_VISION" and self.vision_request is None:
            raise ValueError("NEEDS_VISION 状态必须附带 vision_request")
        if self.result in ("NEEDS_VISION", "UNKNOWN", "UNRESOLVABLE") and not self.explanation:
            raise ValueError(f"未决状态 {self.result} 必须提供 explanation 诊断说明")
        return self

class ChapterEvalReport(StrictModel):
    chapter_id: str
    chapter_instance_id: str
    aggregation_policy: Literal["per_code", "strict_single_spec_cap"] = "per_code"
    chapter_status: Literal["COMPLETED", "PENDING_VISION", "INCOMPLETE_UNKNOWN"]
    total_e_deduction: float = Field(ge=0.0)
    total_d_deduction: float = Field(ge=0.0)
    rule_results: List[RuleEvalResult]
```







## 9、优势：

#### 1. EMNLP 2024：强制严格 JSON 格式导致推理准确率暴跌 10%～15%

- **论文**：[Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models](https://aclanthology.org/2024.emnlp-industry.91/) (Tam et al., 2024)
- **核心发现**：研究系统评测了模型在自由生成、自然文本与强制 JSON/YAML/XML 输出约束下的表现。实验表明，**当强制 LLM 以严格 JSON 模式输出符号推理、数学逻辑和多步推导任务时，模型准确率普遍出现 10%～15% 的显著退化**。
- **机理剖析**：自回归 Transformer 依赖前文生成的 Token 作为思维链（Chain of Thought）。强制要求输出 JSON 语法符号（如键名引号、缩进、转义符、嵌套闭合括号）会**强制打断模型的自然推理轨迹，消耗其自注意力头的表征预算去“维持 JSON 语法的合法性”，而非专注于“逻辑真值条件的判断”**。

#### 2. ICML 2024：可执行代码/表达式形态远胜 JSON

- **论文**：[Executable Code Actions Elicit Better LLM Agents (CodeAct)](https://proceedings.mlr.press/v235/wang24h.html) (Wang et al., ICML 2024)
- **核心发现**：在复杂动作生成、工具调用与多条件决策任务（如 M³ToolEval）中，让模型生成类似 Python 表达式/代码的行为，比生成 JSON 格式的成功率提升了 **15%～20% 以上**。
- **预训练先验差异**：LLM 在海量预训练数据中接触过数万亿 Token 的代码（C++、Python、数学公式），对**中缀操作符优先级（`>`, `<=`, `AND`, `OR`）与函数调用（`HOLD(...)`）具有极其强大的归纳偏置（Inductive Bias）**；相反，将 `(A > 20) AND (B == true)` 人工拆解为 JSON 字典树的形式在自然代码中极少出现，属于反直觉的“数据分布外（OOD）”生成。