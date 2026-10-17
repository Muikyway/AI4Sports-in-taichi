# H36M-17 太极拳动作 DSL（规范版）

> 本文件为当前唯一规范。骨骼输入为 MotionBERT 输出的 `h36m-17` 三维序列；涉及掌法、脚法、足部朝向或触地关系时，额外接入图像模型的结构化视觉证据。   

## 1. 目标与边界

DSL 描述四类内容：

1. **三维几何**：H36M-17 的 17 个三维关节及其空间几何关系。   
2. **太极姿态与步型**：屈膝、提膝、步型（弓/马/仆/虚）、身型（弓背/翻臀/伸髋/倾斜）、重心、站距与左右协调。   
3. **时序与事件**：帧区间内的位移、持续静止、摇晃、倒地与证据输出。   
4. **视觉证据**：图像模型提供的掌法、脚法、脚部运动（滑动/碾转/拔跟/内扣外展）和触地事件。   

DSL 不把图像分类结果当作三维关节，也不把几何代理或图像判断当作真实地面接触力。   

- **数据单位**：每帧输入为 `P[frame][joint][x,y,z]`，关节数固定为 17。三维距离使用 `norm`（相对身高归一化距离），二维画面距离使用 `image_norm`（`0..1`），比例使用 `ratio`，角度使用 `deg`，时间使用 `frame` 或 `ms`。   
- **坐标约定**：计算前先转换到表演者解剖学身体坐标系：`up` 向上，`left` 指表演者左侧，`front` 指表演者身体前方。若转换失败，相关规则返回 `UNKNOWN`。   

## 2. H36M-17 原始对象

以下名称是唯一合法的原始关节对象（新规则必须使用小写规范名，兼容别名：`pelvis = root`、`torso = belly..neck`）：   

| **对象**      | **下标** | **含义**                          | **对象**         | **下标** | **含义** |
| ------------- | -------- | --------------------------------- | ---------------- | -------- | -------- |
| `root`        | 0        | 骨盆根节点                        | `nose`           | 9        | 鼻部     |
| `right_hip`   | 1        | 右髋                              | `head`           | 10       | 头部     |
| `right_knee`  | 2        | 右膝                              | `left_shoulder`  | 11       | 左肩     |
| `right_ankle` | 3        | 右踝                              | `left_elbow`     | 12       | 左肘     |
| `left_hip`    | 4        | 左髋                              | `left_wrist`     | 13       | 左腕     |
| `left_knee`   | 5        | 左膝                              | `right_shoulder` | 14       | 右肩     |
| `left_ankle`  | 6        | 左踝                              | `right_elbow`    | 15       | 右肘     |
| `belly`       | 7        | 腹部/骨盆与胸部中间点（腰部基准） | `right_wrist`    | 16       | 右腕     |
| `neck`        | 8        | 颈部基点                          |                  |          |          |

### 2.1 `side` 参数展开与 `STANCE` 绑定

`side` 可取 `left`、`right`、`front` 或 `rear`；`front`、`rear` 必须由当前窗口的 `STANCE front = left rear = right`（或相反声明）绑定到具体左右腿。按 `side.<joint>`（支持 `hip/knee/ankle/shoulder/elbow/wrist`）展开为 `left_*` 或 `right_*`。`other(side)` 表示取另一侧（`other(left)=right`）。   

### 2.2 明确不存在的对象

H36M-17 没有手掌、手指、脚、脚趾、脚跟、眼睛、耳朵和真实地面接触点。踝关节仅作为下肢骨骼末端代理；手、脚及触地状态只能由第 4.5 节的 `V_*` 视觉原语提供。   

## 3. 派生对象

派生对象不增加输入关节，只由固定公式计算：   

| **对象**                 | **定义**                                                     | **类型**              |
| ------------------------ | ------------------------------------------------------------ | --------------------- |
| `hip_center`             | `(left_hip + right_hip) / 2`                                 | 几何派生              |
| `shoulder_center`        | `(left_shoulder + right_shoulder) / 2`                       | 几何派生              |
| `body_axis`              | 向量 `hip_center -> shoulder_center`                         | 几何派生              |
| `left_leg` / `right_leg` | 折线 `side.hip -> side.knee -> side.ankle`                   | 几何派生              |
| `left_arm` / `right_arm` | 折线 `side.shoulder -> side.elbow -> side.wrist`             | 几何派生              |
| `base`                   | 左右踝在地面平面的线段                                       | 几何派生              |
| `foot_len_est`           | 双侧小腿长均值乘人体统计比例系数（默认 `0.68`），估算本人脚长 | 代理量 (`proxy=true`) |
| `com_est`                | 按固定人体段权重估计的整体重心                               | 代理量 (`proxy=true`) |
| `support_side`           | 由 `com_est` 地面投影和双踝位置推断的承重侧                  | 代理量 (`proxy=true`) |

## 4. 原语分类

缺失点或置信度低于输入阈值时返回 `UNKNOWN`；凡涉及代理量（重心、承重、踝代脚等）的结果必须在输出证据中标记 `proxy=true`。   

### 4.1 点、距离与时序位移

| **原语**                     | **返回**      | **含义**                                                     |
| ---------------------------- | ------------- | ------------------------------------------------------------ |
| `POS(object, axis)`          | `norm`        | 对象在 `up/left/front` 轴上的坐标                            |
| `DIST(a, b)`                 | `norm`        | 同帧两点三维欧氏距离                                         |
| `HORIZONTAL_DIST(a, b)`      | `norm`        | 忽略 `up` 后的地面平面距离                                   |
| `HEIGHT(a)`                  | `norm`        | `POS(a, up)`；相对身体坐标系原点高度                         |
| `KNEE_LIFT_HEIGHT(side)`     | `norm`        | `HEIGHT(side.knee) - HEIGHT(side.hip)`；膝相对同侧髋的有符号高度，正值表示膝高于髋（覆盖编码 `03` 提膝过腰，若需对比腰部中点可用 `HEIGHT(belly)`） |
| `LEG_LIFT_HEIGHT(side)`      | `norm`        | `HEIGHT(side.ankle) - HEIGHT(other(side).ankle)`；双踝有符号高度差（标记 `proxy=true`；确认脚掌腾空需结合 `V_FOOT_AIRBORNE`） |
| `DISPLACEMENT(object, axis)` | `norm`        | 区间内末帧减首帧在指定轴上的净位移（`front > 0` 为上步，`< 0` 为退步） |
| `MAX_DRIFT(object)`          | `norm`        | 区间内对象在水平面（忽略 `up`）偏离初始位置的最大欧氏距离（检测支撑期脚踝平移或骨盆漂移） |
| `SPEED(object)`              | `norm/frame`  | 相邻帧位移速度                                               |
| `ACC(object)`                | `norm/frame2` | 速度的一阶差分                                               |

### 4.2 角度与身型

| **原语**                   | **返回** | **含义**                                                     |
| -------------------------- | -------- | ------------------------------------------------------------ |
| `ANGLE(a, b, c)`           | `deg`    | 以 `b` 为顶点的夹角，范围 `0..180`                           |
| `KNEE_ANGLE(side)`         | `deg`    | `ANGLE(side.hip, side.knee, side.ankle)`                     |
| `KNEE_BEND(side)`          | `deg`    | `180deg - KNEE_ANGLE(side)`；直腿为 `0deg`，**表达“屈膝”的首选原语** |
| `THIGH_HEIGHT_ANGLE(side)` | `deg`    | `side.hip -> side.knee` 相对地面平面的有符号夹角；`0deg` 水平，正值表示膝高于髋 |
| `LEG_TILT(side, axis)`     | `deg`    | `side.hip -> side.ankle` 与指定轴的夹角（覆盖编码 `50` 前举腿低于水平） |
| `THIGH_SPLIT_ANGLE`        | `deg`    | `ANGLE(left_knee, hip_center, right_knee)`；两大腿夹角（覆盖编码 `01` 跌叉夹角 `<= 45deg`） |
| `TRUNK_TILT(axis)`         | `deg`    | `axis=up` 为 `body_axis` 与竖直轴夹角；`axis=left/front` 为对应竖直平面内倾角（覆盖后仰/斜身） |
| `SPINE_BEND`               | `deg`    | `180deg - ANGLE(hip_center, belly, neck)`；直背为 `0deg`，正值衡量**弓背/含胸驼背**（覆盖编码 `16`） |
| `HIP_ANGLE(side)`          | `deg`    | `ANGLE(belly, side.hip, side.knee)`；衡量髋部折叠与**翻臀、伸髋**（覆盖编码 `16`） |
| `ELBOW_ANGLE(side)`        | `deg`    | `ANGLE(side.shoulder, side.elbow, side.wrist)`（覆盖编码 `17` 直臂） |
| `SHOULDER_SHRUG(side)`     | `norm`   | `HEIGHT(side.shoulder) - HEIGHT(neck)`；衡量**耸肩**（覆盖编码 `17`） |
| `ARM_HEIGHT(side)`         | `norm`   | `HEIGHT(side.wrist)`；配合 `HEIGHT(side.elbow)` 衡量抬肘（覆盖编码 `17`） |

### 4.3 步型、站姿与重心

| **原语**                    | **返回**        | **含义**                                                     |
| --------------------------- | --------------- | ------------------------------------------------------------ |
| `STANCE_WIDTH`              | `norm`          | `HORIZONTAL_DIST(left_ankle, right_ankle)`                   |
| `STANCE_LENGTH`             | `norm`          | 双踝在 `front` 轴上的距离绝对值                              |
| `STANCE_FOOT_RATIO`         | `ratio/UNKNOWN` | `STANCE_WIDTH / foot_len_est`；双脚间距相对本人脚长的估计倍数（标记 `proxy=true`，覆盖马步编码 `13` 大于本人脚长 3.5 倍） |
| `COM_POS(axis)`             | `norm`          | `com_est` 在指定轴的位置（`proxy=true`）                     |
| `COM_SPEED`                 | `norm/frame`    | `com_est` 的速度（`proxy=true`）                             |
| `COM_OVER(side)`            | `bool/UNKNOWN`  | 重心投影是否落在该侧踝的容许区域内（`proxy=true`）           |
| `COM_BETWEEN_ANKLES`        | `bool/UNKNOWN`  | 重心投影是否在双踝支撑线段及其容许带内（`proxy=true`）       |
| `SUPPORT(side)`             | `bool/UNKNOWN`  | 根据重心投影推断该侧是否为主要承重侧（`proxy=true`）         |
| `SUPPORT_RATIO(side)`       | `0..1/UNKNOWN`  | 承重侧代理比例，非真实力学测量（`proxy=true`）               |
| `KNEE_OVER_ANKLE(side)`     | `bool/UNKNOWN`  | 膝点在地面平面是否位于同侧髋踝方向的容许范围（`proxy=true`） |
| `KNEE_FORWARD_OFFSET(side)` | `norm/UNKNOWN`  | 膝点相对同侧踝点在 `front` 轴的有符号距离；正值表示膝超过踝（`proxy=true`） |
| `KNEE_MEDIAL_OFFSET(side)`  | `norm/UNKNOWN`  | 膝点相对同侧髋踝线向身体中线偏移的距离；正值表示膝内跪（`proxy=true`） |

### 4.4 对称、摇晃、平衡与倒地

| **原语**                    | **返回**          | **含义**                                                     |
| --------------------------- | ----------------- | ------------------------------------------------------------ |
| `MIRROR_DIFF(feature)`      | 与 feature 同单位 | 左右对应特征的绝对差，仅限 `KNEE_BEND`、`ELBOW_ANGLE`、`ARM_HEIGHT`、`LEG_TILT` |
| `SHOULDER_LEVEL_DIFF`       | `norm`            | 左右肩 `up` 高度差绝对值                                     |
| `HIP_LEVEL_DIFF`            | `norm`            | 左右髋 `up` 高度差绝对值                                     |
| `BODY_SWAY(axis)`           | `norm`            | 区间内 `shoulder_center - hip_center` 在 `left/front` 轴上的最大值减最小值（躯干相对骨盆摆幅） |
| `COM_SWAY(axis)`            | `norm`            | 区间内 `com_est` 在 `left/front` 轴上的最大值减最小值（`proxy=true`，衡量骨盆位置或身体中心持续摆动） |
| `SWAY_ANGLE`                | `deg/UNKNOWN`     | 稳定支撑期内躯干在 `left/front` 竖直平面中**往返摆动**的最大角位移；必须检测到两个相反方向的位移（单向正常转体返回 `0deg`，用于编码 `80/81`） |
| `BALANCE_STILL`             | `bool/UNKNOWN`    | 已识别平衡动作中全身姿态进入静止状态；阈值由执行器版本化配置 |
| `HOLD(condition, duration)` | `bool/UNKNOWN`    | `condition` 从首次进入状态起连续成立至少 `duration`（用于编码 `87` 连续静止 `2000ms`） |
| `FALL_SUSPECTED`            | `bool/UNKNOWN`    | 骨骼倒地事件推断：`COM_POS(up)` 快速下降、躯干接近水平（`TRUNK_TILT(up) > 65deg`）且姿态持续失稳（标记 `proxy=true`，用于编码 `84`） |

### 4.5 图像模型原语

下列 `V_*` 原语**只读取图像模型输出**（须含 `frame_range`、`value`、`confidence`、`source`、`coverage`），不得由 H36M-17 坐标直接求值。遮挡、视角不足、置信度低或区间未完整检查时必须返回 `UNKNOWN`，严禁输出 `false`。   

| **原语**                     | **返回**                       | **视觉含义**                                                 |
| ---------------------------- | ------------------------------ | ------------------------------------------------------------ |
| `V_VISIBLE(part)`            | `bool/UNKNOWN`                 | 指定部位在画面中是否可见                                     |
| `V_POS(part, axis)`          | `image_norm/UNKNOWN`           | 部位二维图像位置（`axis` 取 `x/y`，不可见时返回 `UNKNOWN`）  |
| `V_HAND_FORM(side)`          | `palm/fist/hook/other/UNKNOWN` | 手型：掌、拳、勾或其他（覆盖编码 `10/11/31`）                |
| `V_HAND_TECHNIQUE(side)`     | `label/UNKNOWN`                | 掌法或握剑法类别，来自闭合类别表（覆盖编码 `30/32/33/34`）   |
| `V_FOOT_TECHNIQUE(side)`     | `label/UNKNOWN`                | 脚法或击拍类别，来自闭合类别表（覆盖编码 `61/70`）           |
| `V_FOOT_OUTTURN(side)`       | `deg/UNKNOWN`                  | 脚尖相对身体前进方向的有符号水平夹角：**正值为外展，负值为内扣**（覆盖跌叉 `01` 与仆步 `14` 内扣） |
| `V_KNEE_OVER_TOE(side)`      | `bool/UNKNOWN`                 | 膝盖前端在水平投影上明显超过同侧脚尖（覆盖弓步编码 `12`）    |
| `V_KNEE_TOE_ALIGNED(side)`   | `bool/UNKNOWN`                 | 支撑膝弯曲方向与同侧脚尖朝向对正（覆盖虚步 `15`、上步 `18`） |
| `V_HEEL_LIFT(side)`          | `bool/UNKNOWN`                 | 脚跟明显离地，同时脚前部仍接近地面（覆盖弓步 `12` 后脚跟离地、虚步 `15` 前脚跟着地判定） |
| `V_FULL_FOOT_GROUNDED(side)` | `bool/UNKNOWN`                 | 全脚掌完整接触地面（覆盖仆步 `14` 全脚掌着地）               |
| `V_FOOT_SLIDE(side)`         | `bool/UNKNOWN`                 | 脚掌与地面保持接触时出现平移滑动（覆盖编码 `82`）            |
| `V_FOOT_PIVOT(side)`         | `bool/UNKNOWN`                 | 脚掌与地面保持接触时出现碾转位移（覆盖编码 `82`）            |
| `V_FOOT_RECOVERY_STEP(side)` | `bool/UNKNOWN`                 | 单脚平衡失稳时，原抬起的非支撑脚落地并迈步恢复平衡（覆盖编码 `82`） |
| `V_FOOT_SKIP(side)`          | `bool/UNKNOWN`                 | 应稳定支撑时，脚短暂离地并再次落地形成跳动（覆盖编码 `83`）  |
| `V_FOOT_AIRBORNE(side)`      | `bool/UNKNOWN`                 | 指定脚短暂整体离地                                           |
| `V_FOOT_GROUND_GAP(side)`    | `image_norm/UNKNOWN`           | 脚部最低可见点到正下方局部地面的二维画面间隙（不可换算为 `norm`） |
| `V_GROUND_CONTACT(part)`     | `bool/UNKNOWN`                 | 身体部位或器械与地面可见接触（覆盖跌叉 `01`、插腿触地 `51`、倒地 `84`、器械触地 `85`） |
| `V_UNEXPECTED_SUPPORT(part)` | `bool/UNKNOWN`                 | 预期不承担支撑的部位出现可见触地借力；须提供阶段预期支撑配置（覆盖编码 `83`） |

- **合法 `part` 标签枚举**：`left_hand`, `right_hand`, `left_elbow`, `right_elbow`, `left_shoulder`, `right_shoulder`, `left_arm`, `right_arm`, `left_knee`, `right_knee`, `front_knee`, `rear_knee`, `left_foot`, `right_foot`, `front_foot`, `rear_foot`, `left_heel`, `right_heel`, `front_heel`, `rear_heel`, `left_toe`, `right_toe`, `front_toe`, `rear_toe`, `head`, `back`, `hip`, `equipment`（其中手、脚、脚跟、脚尖与器械为视觉标签，非 H36M-17 关节；`front_*/rear_*` 先由 `STANCE` 绑定）。   

### 4.7 十大规则关键词与 DSL 原语映射表

| **关键词**                          | **规则含义**                                 | **H36M-17 骨骼原语**                                         | **图像模型原语 (V_\*)**                                      | **关联编码**         |
| ----------------------------------- | -------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | -------------------- |
| **1. 屈膝、膝角**                   | 支撑腿弯曲程度、膝关节夹角                   | `KNEE_BEND(side)`, `KNEE_ANGLE(side)`                        | -                                                            | `12, 14, 60, 61, 71` |
| **2. 抬膝、提膝**                   | 膝盖是否抬高、是否超过髋部或腰部             | `KNEE_LIFT_HEIGHT(side)`, `THIGH_HEIGHT_ANGLE(side)`         | -                                                            | `03`                 |
| **3. 弓步、马步、仆步、虚步**       | 下肢姿态、双脚间距、髋膝关系                 | `STANCE_WIDTH`, `STANCE_LENGTH`, `STANCE_FOOT_RATIO`, `KNEE_FORWARD_OFFSET`, `KNEE_MEDIAL_OFFSET` | `V_KNEE_OVER_TOE`, `V_KNEE_TOE_ALIGNED`, `V_FULL_FOOT_GROUNDED` | `12, 13, 14, 15`     |
| **4. 脚尖方向、脚跟抬起、脚掌着地** | 脚尖朝向、脚跟/前脚掌是否接触地面            | -                                                            | `V_FOOT_OUTTURN`, `V_HEEL_LIFT`, `V_FULL_FOOT_GROUNDED`, `V_GROUND_CONTACT` | `01, 12, 14, 15, 18` |
| **5. 上步、退步、脚移动**           | 脚步是否移动、移动方向和距离                 | `DISPLACEMENT(side.ankle, axis)`, `MAX_DRIFT(side.ankle)`, `SPEED(side.ankle)` | `V_FOOT_SLIDE`, `V_FOOT_PIVOT`, `V_FOOT_RECOVERY_STEP`, `V_FOOT_SKIP` | `18, 82, 83`         |
| **6. 身型、躯干倾斜**               | 弓背、后仰、翻臀、伸髋、躯干不正             | `TRUNK_TILT(axis)`, `SPINE_BEND`, `HIP_ANGLE(side)`          | -                                                            | `16`                 |
| **7. 重心、承重、支撑**             | 重心位置、主要支撑腿、身体是否偏向一侧       | `COM_POS`, `COM_OVER`, `COM_BETWEEN_ANKLES`, `SUPPORT`, `SUPPORT_RATIO` | `V_UNEXPECTED_SUPPORT`                                       | `15, 83`             |
| **8. 身体摇晃、重心不稳**           | 躯干角度、骨盆位置或身体中心持续摆动         | `SWAY_ANGLE`, `BODY_SWAY(axis)`, `COM_SWAY(axis)`            | -                                                            | `80, 81`             |
| **9. 平衡保持不足 2 秒**            | 首次达到目标姿态后，未连续稳定保持 2 秒      | `BALANCE_STILL`, `HOLD(BALANCE_STILL, 2000ms)`               | -                                                            | `87`                 |
| **10. 摔倒、倒地**                  | 身体高度快速下降、躯干接近水平、姿态持续失稳 | `FALL_SUSPECTED`, `COM_POS(up)`, `TRUNK_TILT(up)`            | `V_GROUND_CONTACT(hip/back/shoulder/head)`                   | `84`                 |

## 5. 值、比较与三值逻辑

- **字面量与运算符**：`number deg`、`number norm`、`number image_norm`、`number ratio`、`number frame`、`number ms`、`true`、`false`。比较符：`== != < <= > >=`；区间：`BETWEEN(low, high)`；逻辑：`AND OR NOT`。`norm` 与 `image_norm` 不能直接比较。   
- **三种未决状态**（规则条件采用三值逻辑，缺少必需数据不得默认通过或扣分）：   

| **情况**                                                 | **DSL 写法**                           | **执行状态**   | **自然语言内容要求**                                       |
| -------------------------------------------------------- | -------------------------------------- | -------------- | ---------------------------------------------------------- |
| 规则需要视觉证据，但视觉输入未接入                       | `ON_UNAVAILABLE REQUEST_VISION("...")` | `NEEDS_VISION` | 明确需要检测的手/脚部位、事件、帧区间和视角                |
| 骨骼或视觉已接入，但数据缺失、遮挡、低置信度或区间不完整 | `ON_UNKNOWN EXPLAIN("...")`            | `UNKNOWN`      | 明确无法确定的量、原因类别和补充证据要求，并追加运行时诊断 |
| 目标量不能由本 DSL 的骨骼与视觉数据可靠判断              | `UNRESOLVABLE RULE ...`                | `UNRESOLVABLE` | 明确不可判定的内容及需要的外部传感器/标注                  |

## 6. 最小语法

```
DSL H36M17-TAICHI 1
INPUT skeleton = h36m-17
INPUT fps = 25
INPUT vision = optional
STANCE front = left rear = right
CHAPTER <chapter_id> ACTION "<action_name>"

RULE <name> IN <chapter_id> [ON <phase>] [WITHIN <start>..<end>] :
  <condition>
  => VIOLATION ELSE PASS
  [DEDUCT item=<item_id> code=<code> points=<decimal> group=E scope=<event|technique>]
  [ON_UNAVAILABLE REQUEST_VISION(<quoted_instruction>)]
  ON_UNKNOWN EXPLAIN(<quoted_reason>)

UNRESOLVABLE RULE <name> [ON <phase>] :
  EXPLAIN(<quoted_reason>)
  REQUIRE(<quoted_external_data>)
```

- 上游动作分段须提供 `chapter_instance_id`、`chapter_id`、起止帧、阶段区间（`ON <phase>`）及预期支撑配置；缺失边界时返回 `UNKNOWN`，不得回退到全视频搜索。   
- 正式扣分规则固定写成 `=> VIOLATION ELSE PASS` 并附带 `DEDUCT`；`UNKNOWN`、`NEEDS_VISION`、`UNRESOLVABLE` 均不产生扣分。   

## 7. 执行结果格式

| **字段**                                                     | **含义**                                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| `rule`、`chapter_id`、`chapter_instance_id`、`item_id`       | 规则、动作章节、章节实例及章节内唯一扣分小项 ID              |
| `phase`、`frame_range`                                       | 章节内阶段和判定帧区间                                       |
| `result`                                                     | `PASS`、`VIOLATION`（或 `FAIL`）、`NEEDS_VISION`、`UNKNOWN`、`UNRESOLVABLE` |
| `values`                                                     | 原语实际值、单位、阈值、置信度、数据来源及代理配置名         |
| `explanation`                                                | 无法判定的自然语言原因加运行时诊断；未决状态必填             |
| `request`、`required_primitives`                             | 缺少视觉输入时需要检测的内容及原语                           |
| `required_external_data`                                     | 骨骼和视觉都无法判定时所需的外部数据                         |
| `proxy`、`vision_required`                                   | 是否使用几何代理量、是否需要视觉证据                         |
| `event_id`、`deduction_code`、`deduction_points`、`score_group` | 扣分事件编号、PDF 编码、固定扣分值（仅 `VIOLATION` 时 `>0`）和评分组 |
| `deduction_scope`、`counted_events`                          | 按事件或动作去重作用域、最终计数的事件数量                   |





## 8. LLM 生成规则时的硬约束

1. 先检查输入声明是否为 `h36m-17`，不匹配则停止生成规则。
2. 只能从第 2、3 节选择骨骼对象，从第 4 节选择原语；视觉部位只使用第 4.5 节的闭合标签表。
3. 手、脚、脚跟和脚尖只能用第 4.5 节定义的视觉标签与 `V_*` 原语，不能当作 H36M-17 关节；不得创造真实压力或接触力原语。
4. 掌法、脚法、脚尖朝向、拔跟、滑动、转动、腾空和触地使用 `V_*` 原语，并添加 `ON_UNAVAILABLE REQUEST_VISION("...")`。
5. 表达屈膝使用 `KNEE_BEND(side)`；表达提膝使用 `KNEE_LIFT_HEIGHT(side)`；表达马步间距比使用 `STANCE_FOOT_RATIO`；表达弓背与翻臀伸髋使用 `SPINE_BEND` 与 `HIP_ANGLE(side)`；表达重心与摇晃使用 `COM_*`、`SUPPORT_*`、`SWAY_ANGLE` 或 `COM_SWAY`。
6. 重心、承重、脚长比、双踝高差和骨骼倒地推断结果必须标记 `proxy=true`；视觉相关结果必须标记 `vision_required=true`。
7. 所有数字必须带单位（`deg`、`norm`、`image_norm`、`ratio`、`frame`、`ms`）。
8. 每条可执行规则都要写 `ON_UNKNOWN EXPLAIN("无法判断什么；还需要什么")`，不得只写 `ON_UNKNOWN UNKNOWN`。
9. 正式扣分规则必须映射第 4.6 节登记的编码、固定分值与 `scope`，按章节实例和事件区间去重，不能跨章节或逐帧累扣。
10. **防呆约束 1（参数实例化）**：严禁在生成的代码中直接输出字面量 `side`。遇到带 `side` 的原语时，必须结合当前的步型和 `STANCE` 声明，将其显式替换为具体的 `front`、`rear`、`left` 或 `right`（例如：不能写 `KNEE_BEND(side)`，必须写 `KNEE_BEND(rear)`）。
11. **防呆约束 2（ID 唯一性）**：`item` 参数必须是具有语义的唯一英文字符串（例如 `item=bow_rear_knee_bent`），严禁直接使用数字编码（如 `item=12`）或在同一章节内使用重复的标识符。`code` 参数用于填写对应的数字编码。
12. **防呆约束 3（架构细分）**：必须按真实的太极动作名称细分 `CHAPTER`（如 `CHAPTER yema_fenzong`），严禁将所有规则塞入一个全局通用章节。

