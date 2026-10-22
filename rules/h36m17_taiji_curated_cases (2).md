# H36M-17 太极拳混合型动作规约语言：典型规则案例库（v3.0 精选版）

> 本文件与《核心语法规范（v3.0 扁平 JSON + 内联微公式版）》配套使用。根据《国际太极拳竞赛规则》调研，太极拳的所有裁判判罚可归纳为四大正交原型：**基础步型与下沉深度**、**静态平衡与时序保持（`HOLD`）**、**腾空旋转跳跃与不可判定项（`unresolvable`）**、**骨骼优先短路求值与章节级去重输出报告**。以下精选 4 个最具代表性的标准案例。

## 案例一：基础步型规格与难度下沉深度（杨式左右野马分鬃 `100A`）

* **规则调研与混合表达优势**：
  * **E 组规格错误（表-8 编码 `12`）**：左弓步定式期内，后腿明显弯曲（`KNEE_BEND(rear) > 20.0deg`）、前膝超过脚尖（`V_KNEE_OVER_TOE(front) == true`）或后脚跟离地（`V_HEEL_LIFT(rear) == true`）任一发生即扣 `0.10` 分。通过内联 `@item_id:` 微公式列表，既免除了将同一弓步拆成 3 个重复 JSON 块的冗余，又保留了每个具体错误原因的独立追踪 ID。
  * **D 组难度不符（表-11 `D_STANCE_115`）**：弓步屈蹲腿大腿轴线与垂直轴线夹角 `>115°`，扣 `0.10` 分。

```json
{
  "dsl_version": "H36M17-TAICHI-HYBRID-3.0",
  "input_spec": { "skeleton": "h36m-17", "fps": 25, "vision_mode": "demand_driven" },
  "chapter": { "chapter_id": "yang_yema_fenzong", "action_name": "杨式左右野马分鬃", "action_code": "100A" },
  "rules": [
    {
      "rule_id": "yema_left_bow_spec_e12",
      "phase": "hold_left_bow",
      "frame_window": [45, 90],
      "stance": { "front": "left", "rear": "right", "support": "left" },
      "logic": "ANY",
      "expr": [
        "@bow_left_rear_knee_bent: KNEE_BEND(rear) > 20.0deg",
        "@bow_left_front_knee_over_toe: V_KNEE_OVER_TOE(front) == true",
        "@bow_left_rear_heel_lifted: V_HEEL_LIFT(rear) == true"
      ],
      "deduction": { "code": "12", "points": 0.10, "group": "E", "scope": "technique" },
      "vision_fallback": {
        "target_parts": ["front_knee", "front_toe", "rear_heel"],
        "frame_window": [45, 90],
        "instruction": "检测 45..90 帧左弓步定式：左膝前端水平投影是否超过左脚尖、右脚跟是否离地拔跟"
      },
      "unknown_reason": "左脚尖或右脚跟被遮挡，或右腿三维关键点缺失，无法完整判定弓步规格错误"
    },
    {
      "rule_id": "yema_left_bow_depth_d115",
      "phase": "hold_left_bow",
      "frame_window": [45, 90],
      "stance": { "front": "left", "rear": "right", "support": "left" },
      "logic": "ALL",
      "expr": [
        "@bow_left_thigh_above_115: THIGH_VERTICAL_ANGLE(front) > 115.0deg"
      ],
      "deduction": { "code": "D_STANCE_115", "points": 0.10, "group": "D", "scope": "technique" },
      "vision_fallback": null,
      "unknown_reason": "左髋或左膝三维关键点置信度不足，无法计算左弓步大腿与垂直轴夹角"
    }
  ]
}
```

## 案例二：静态平衡姿态与 `NOT HOLD` 时序保持（陈式左右金鸡独立 `1118A`）

* **规则调研与原版 DSL 对齐**：
  * **E 组规格错误（表-8 编码 `03`）**：提膝独立时提腿膝部未过腰（严格对齐原版 DSL：`KNEE_LIFT_HEIGHT(right) <= 0.0norm`，即右膝高度不高于右髋高度），扣 `0.10` 分。
  * **E 组其它错误（表-9 编码 `87`）**：平衡静止时间不足 2 秒。直接采用内联时序微公式 `NOT HOLD(BALANCE_STILL() == true, 2000ms)`，无需在外层 JSON 中构造多层 `NOT -> HOLD -> CLAUSE` 递归树。

```json
{
  "dsl_version": "H36M17-TAICHI-HYBRID-3.0",
  "input_spec": { "skeleton": "h36m-17", "fps": 25, "vision_mode": "demand_driven" },
  "chapter": { "chapter_id": "chen_jinji_duli", "action_name": "陈式左右金鸡独立", "action_code": "1118A" },
  "rules": [
    {
      "rule_id": "jinji_right_knee_below_waist_e03",
      "phase": "balance_hold_left_support",
      "frame_window": [120, 185],
      "stance": { "front": "none", "rear": "none", "support": "left" },
      "logic": "ALL",
      "expr": [
        "@right_knee_below_right_hip: KNEE_LIFT_HEIGHT(right) <= 0.0norm"
      ],
      "deduction": { "code": "03", "points": 0.10, "group": "E", "scope": "technique" },
      "vision_fallback": null,
      "unknown_reason": "右膝或右髋三维关键点缺失，无法判定提膝高度是否高于同侧髋"
    },
    {
      "rule_id": "jinji_hold_under_2s_e87",
      "phase": "balance_hold_left_support",
      "frame_window": [120, 185],
      "stance": { "front": "none", "rear": "none", "support": "left" },
      "logic": "ALL",
      "expr": [
        "@balance_still_less_than_2s: NOT HOLD(BALANCE_STILL() == true, 2000ms)"
      ],
      "deduction": { "code": "87", "points": 0.10, "group": "E", "scope": "event" },
      "vision_fallback": null,
      "unknown_reason": "平衡阶段有效帧不足 50 帧或关节点抖动缺失，无法判定连续 2000ms 静止保持"
    }
  ]
}
```

## 案例三：腾空旋转跳跃与不可判定规则声明（旋风脚 360° 接提膝独立 `735E+3`）

* **规则调研依据**：
  * **E 组跳跃规格错误（表-8 编码 `70`）**：击拍落空（`V_FOOT_SLAP_HIT(right) == false`）或击响腿脚尖未过肩（`ANKLE_REL_HEIGHT(right, shoulder_center) < 0.0norm`），扣 `0.10` 分。
  * **D 组跳跃难度未完成（表-11 `D_JUMP_EFG`）**：空中转体不足 360°（`YAW_ROTATION(pelvis) < 330.0deg` 或 `V_FOOT_ROTATION(right) < 330.0deg`）或击响腿未过腰，扣 `0.20` 分。
  * **不可判定规则显式声明（`unresolvable: true`）**：若规则涉及“支撑脚五趾抓地力道不足”等在 H36M-17 与常规视觉下均不可观测的条款，显式标记 `"unresolvable": true, "expr": []`，执行器直接返回 `"UNRESOLVABLE"`。

```json
{
  "dsl_version": "H36M17-TAICHI-HYBRID-3.0",
  "input_spec": { "skeleton": "h36m-17", "fps": 25, "vision_mode": "demand_driven" },
  "chapter": { "chapter_id": "xuanfengjiao_360_tixi", "action_name": "旋风脚360度接提膝独立", "action_code": "735E+3" },
  "rules": [
    {
      "rule_id": "tornado_360_slap_or_height_e70",
      "phase": "airborne_peak",
      "frame_window": [200, 220],
      "stance": { "front": "none", "rear": "none", "support": "airborne" },
      "logic": "ANY",
      "expr": [
        "@tornado_foot_below_shoulder: ANKLE_REL_HEIGHT(right, shoulder_center) < 0.0norm",
        "@tornado_slap_missed: V_FOOT_SLAP_HIT(right) == false"
      ],
      "deduction": { "code": "70", "points": 0.10, "group": "E", "scope": "technique" },
      "vision_fallback": {
        "target_parts": ["left_hand", "right_foot"],
        "frame_window": [200, 220],
        "instruction": "检测 200..220 帧腾空最高点：左手掌是否准确击拍右脚面"
      },
      "unknown_reason": "腾空期手脚高速运动模糊或遮挡，无法确认是否击拍落空"
    },
    {
      "rule_id": "tornado_360_rotation_insufficient_d",
      "phase": "takeoff_to_landing",
      "frame_window": [195, 225],
      "stance": { "front": "none", "rear": "none", "support": "airborne" },
      "logic": "ANY",
      "expr": [
        "@tornado_pelvis_yaw_under_330: YAW_ROTATION(pelvis) < 330.0deg",
        "@tornado_foot_rot_under_330: V_FOOT_ROTATION(right) < 330.0deg"
      ],
      "deduction": { "code": "D_JUMP_EFG", "points": 0.20, "group": "D", "scope": "technique" },
      "vision_fallback": {
        "target_parts": ["right_heel", "right_toe"],
        "frame_window": [195, 225],
        "instruction": "检测 195 帧起跳瞬时与 225 帧落地瞬时右脚尖-脚跟连线的水平旋转夹角是否不足 330 度"
      },
      "unknown_reason": "起跳或落地帧脚部被遮挡，无法判定旋风脚 360 度转体角度"
    },
    {
      "rule_id": "landing_toe_grip_pressure_unresolvable",
      "phase": "landing_hold",
      "frame_window": [225, 275],
      "stance": { "front": "none", "rear": "none", "support": "left" },
      "unresolvable": true,
      "logic": "ANY",
      "expr": [],
      "deduction": { "code": "15", "points": 0.10, "group": "E", "scope": "technique" },
      "vision_fallback": null,
      "unknown_reason": "五趾抓地足底压力分布超出 H36M-17 骨骼与单目 RGB 视觉可观测边界，标记为 UNRESOLVABLE"
    }
  ]
}
```

## 案例四：骨骼优先短路求值与同章节去重输出报告（`ChapterEvalReport`）

* **场景说明**：在“杨式左右野马分鬃（`yang_yema_fenzong#1`）”中：
  1. 左弓步规则 `yema_left_bow_spec_e12` 的第一条骨骼子项 `@bow_left_rear_knee_bent` 实测 `27.4deg > 20.0deg`（状态 `T`），在 `ANY` 逻辑下直接短路判定 `VIOLATION`，免除了对 `@bow_left_front_knee_over_toe` 的视觉模型调用（其状态保留为未唤醒的 `V`）。
  2. 右弓步规则 `yema_right_bow_spec_e12` 同样触发编码 `12` 违规，被章节聚合器按 `scope="technique"` 自动去重吸收（`effective_deduction_points = 0.0`），并记录 `deduplicated_by = "yang_yema_fenzong#1:12:68"`。

```json
{
  "chapter_id": "yang_yema_fenzong",
  "chapter_instance_id": "yang_yema_fenzong#1",
  "aggregation_policy": "per_code",
  "chapter_status": "COMPLETED",
  "total_e_deduction": 0.10,
  "total_d_deduction": 0.00,
  "rule_results": [
    {
      "rule_id": "yema_left_bow_spec_e12",
      "chapter_id": "yang_yema_fenzong",
      "chapter_instance_id": "yang_yema_fenzong#1",
      "phase": "hold_left_bow",
      "frame_range": [45, 90],
      "result": "VIOLATION",
      "triggered_items": ["bow_left_rear_knee_bent"],
      "item_traces": [
        {
          "item_id": "bow_left_rear_knee_bent",
          "formula": "KNEE_BEND(rear) > 20.0deg",
          "actual_values": { "KNEE_BEND(rear)": 27.4 },
          "unit": "deg",
          "confidence": 0.96,
          "source": "skeleton_3d",
          "proxy": false,
          "state": "T"
        },
        {
          "item_id": "bow_left_front_knee_over_toe",
          "formula": "V_KNEE_OVER_TOE(front) == true",
          "actual_values": {},
          "unit": "bool",
          "confidence": null,
          "source": "vision_2d",
          "proxy": false,
          "state": "V"
        }
      ],
      "proxy_used": false,
      "vision_required": false,
      "explanation": "经骨骼优先短路求值（ANY 规则）：子项 @bow_left_rear_knee_bent 实测右腿屈膝角 27.4deg > 20.0deg（状态 T），直接确认违规，免除视觉调用",
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
      "rule_id": "yema_right_bow_spec_e12",
      "chapter_id": "yang_yema_fenzong",
      "chapter_instance_id": "yang_yema_fenzong#1",
      "phase": "hold_right_bow",
      "frame_range": [110, 155],
      "result": "VIOLATION",
      "triggered_items": ["bow_right_rear_knee_bent"],
      "item_traces": [
        {
          "item_id": "bow_right_rear_knee_bent",
          "formula": "KNEE_BEND(rear) > 20.0deg",
          "actual_values": { "KNEE_BEND(rear)": 24.1 },
          "unit": "deg",
          "confidence": 0.94,
          "source": "skeleton_3d",
          "proxy": false,
          "state": "T"
        }
      ],
      "proxy_used": false,
      "vision_required": false,
      "explanation": "子项 @bow_right_rear_knee_bent 实测后腿屈膝角 24.1deg > 20.0deg，因同章节实例内编码 12 已扣分，按 scope=technique 去重吸收",
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