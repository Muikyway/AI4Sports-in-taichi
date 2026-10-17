# 动作视频规则评分系统：代码与启动总览

本文件是新增的项目汇总说明，不替换其他说明文档。现有的 README.md、README_USAGE.md 和 README_LLM_RULE_PIPELINE.md 保持不变。

## 1. 系统能做什么

系统将动作视频转换为可审计的规则评分结果：

~~~text
视频 -> AlphaPose/Halpe-26 姿态关键点 -> 运动学特征
     -> YAML 规则解析 -> 白盒规则验证与扣分
     -> Evidence JSON -> Markdown 专业评分报告
~~~

当前示例项目为“野马分鬃”第二阶段。当前代码的正式扣分公式是：

~~~text
strict/review/soft:
  final_score = max(0, base_score - sum(fixed_penalty for triggered rules))
~~~

规则判断、数值计算和扣分由 Python 白盒代码完成。soft 模式额外输出 sigmoid 研究指标，但不会把概率乘进最终扣分；这样可以保持当前裁判规则的可解释性和复现性。LLM（如果启用）只把结构化证据翻译成报告，不直接观看视频或猜分数。

## 2. 代码结构

~~~text
D:/program/test/
├─ AlphaPose/
│  ├─ configs/halpe_26/resnet/         # Halpe-26 配置
│  ├─ pretrained_models/               # 姿态模型权重
│  └─ scripts/demo_inference.py        # AlphaPose 推理入口
├─ rules/
│  └─ yema_fenzong_test.yaml           # 野马分鬃测试规则
├─ rule_scoring/
│  ├─ engine.py                        # 条件、阈值、扣分和证据计算
│  ├─ io.py                            # YAML/JSON 读写及校验
│  ├─ __main__.py                      # python -m rule_scoring
│  └─ report.py                        # 评分汇总
├─ scripts/
│  ├─ pose_to_evidence.py              # pose 序列 -> 运动学证据
│  ├─ evaluate_video.py                # AlphaPose + 判分一键流程
│  └─ generate_report.py               # Evidence/score -> Markdown
├─ examples/run_yema_fenzong_test.ps1  # Windows 示例脚本
├─ data/pose/                          # AlphaPose 输出
├─ data/evidence/                      # 运动学证据
├─ data/annotations/                   # 人工标注和真实分数
├─ outputs/                            # 运行结果
└─ llm_sft/
   ├─ download_qwen3_model.py          # ModelScope 本地下载
   ├─ train_qwen3_sft.py               # Qwen3 LoRA/SFT
   └─ data/*.jsonl                     # 规则编译训练样本
~~~

## 3. 数据格式

### 3.1 AlphaPose/Halpe-26 原始输出

AlphaPose 输出是 JSON 数组，每一项代表某一帧中的一个人：

~~~json
[
  {
    "image_id": "frame_000120.jpg",
    "category_id": 1,
    "keypoints": [x0, y0, c0, x1, y1, c1],
    "score": 0.941,
    "idx": 0
  }
]
~~~

Halpe-26 的 keypoints 长度为 78（26 个点，每个点为 x、y、confidence）。score 是整个人体置信度，idx 是人员跟踪编号，image_id 用于排序和分组。某些 AlphaPose 版本还会输出 bbox 或 box_score；本项目评分链不依赖它们。

本项目使用的 Halpe-26 语义索引如下，规则中的 body_part 必须使用这些名称：

~~~text
0 Nose       1 Left_Eye       2 Right_Eye      3 Left_Ear       4 Right_Ear
5 LShoulder  6 RShoulder      7 LElbow        8 RElbow        9 LWrist
10 RWrist    11 LHip          12 RHip          13 LKnee        14 Right_Knee
15 LAnkle    16 RAnkle        17 Head          18 Neck          19 Hip
20 LBigToe   21 RBigToe       22 LSmallToe     23 RSmallToe     24 LHeel
25 RHeel
~~~

pose_to_evidence.py 按 image_id 的自然顺序读取记录；默认每帧取 score 最高的人，传入 --track-id 时取 idx 等于该值的人。关键点缺失、置信度低于 --min-keypoint-confidence 或无法求出人体尺度时，该帧不会生成对应物理量。

如果接入 MotionBERT，必须先按其官方 halpe2h36m() 映射将 Halpe-26 转成 H36M-17；不要直接截取前 17 个点。官方映射会重排髋部、膝部、踝部、脊柱/胸部、头部和双臂，并丢弃面部与脚趾扩展点。

### 3.2 运动学证据（evidence.json）

转换器输出的是可被评分器直接匹配的 facts 列表：

~~~json
{
  "performance_id": "alphapose-results",
  "action": "野马分鬃",
  "facts": [
    {
      "frame_range": [146, 150],
      "duration_frames": 5,
      "phase": "第二阶段",
      "body_part": "Right_Knee",
      "metric": "joint_angle",
      "value": 118.0,
      "unit": "degree",
      "confidence": 0.94,
      "source": "alphapose-json"
    }
  ],
  "metadata": {
    "pose_json": "outputs/yema_fenzong/alphapose-results.json",
    "frame_count": 101,
    "phase": "第二阶段",
    "phase_range": [120, 220]
  }
}
~~~

fact 的 frame_range 是连续片段，duration_frames 是片段长度，phase/body_part/metric 是规则匹配键，value/unit 是测量结果，confidence 是关键点置信度聚合值，source 标明数据来源。当前内置物理量为：

- Right_Knee / joint_angle：RHip-RKnee-RAnkle 三点夹角，单位 degree。
- Torso / torso_tilt：肩中心到髋中心相对竖直方向的倾角，单位 degree。
- Feet / foot_distance_ratio：双踝距离除以人体高度，单位 ratio。
- Right_Wrist / wrist_height_ratio：右腕相对髋部的高度除以人体高度，单位 ratio。
- Phase / phase_duration：由 --phase-start 和 --phase-end 产生的阶段帧数，单位 frame。

同一阶段、部位和 metric 的连续帧会被合并，并保留最能代表规则边界的帧。因此 evidence 是“关键点 -> 物理量 -> 时间锚点”的中间层，而非关键点 JSON 的简单复制。

### 3.3 评分输出（score.json）

python -m rule_scoring 输出如下结构：

~~~json
{
  "performance_id": "alphapose-results",
  "rubric": {
    "id": "taichi-yema-fenzong-test-v1",
    "name": "野马分鬃研究用测试规则",
    "version": "1.0.0",
    "base_score": 10.0
  },
  "mode": "strict",
  "base_score": 10.0,
  "total_deduction": 1.0,
  "final_score": 9.0,
  "items": [
    {
      "rule_id": "YMZ-P2-KNEE-001",
      "rule_name": "第二阶段右膝屈曲不足",
      "status": "violation",
      "violation": true,
      "deduction": 1.0,
      "review_required": false,
      "evidence": {
        "frame_range": [146, 150],
        "phase": "第二阶段",
        "body_part": "Right_Knee",
        "metric": "joint_angle",
        "value": 118.0,
        "unit": "degree",
        "confidence": 0.94,
        "source": "alphapose-json"
      }
    }
  ]
}
~~~

每条启用且动作匹配的规则对应一个 item。没有同阶段、同部位、同 metric 证据时，status 为 no_evidence 且 deduction 为 0。total_deduction 是固定扣分之和，final_score = max(0, base_score - total_deduction)。review_required 只表示需要人工复核，不等于自动违规。

## 4. 评分器规则如何书写

规则文件必须是 YAML 顶层对象，评分器实际读取的顶层键是 rubric 和 rules。下面的模板可以直接复制后修改：

~~~yaml
rubric:
  id: yema-fenzong-test
  name: 野马分鬃第二阶段测试评分
  version: "1.0"
  base_score: 10.0
  note: 仅用于算法联调，正式阈值需专家审核

rules:
  - id: YMZ-P2-KNEE-001
    name: 右膝屈曲角度
    action: 野马分鬃
    phase: 第二阶段
    enabled: true
    predicate:
      metric: joint_angle
      body_part: Right_Knee
      operator: ">"
      threshold: 115.0
      unit: degree
      tolerance: 5.0
      uncertainty: 2.0
      min_confidence: 0.50
      duration_frames: 1
    aggregation:
      type: max_probability
    penalty:
      max_points: 1.0
      severity: major
    evidence:
      required: [frame_range, body_part, metric, value, confidence]

  - id: YMZ-P2-FEET-001
    name: 两脚距离
    action: 野马分鬃
    phase: 第二阶段
    enabled: true
    predicate:
      metric: foot_distance_ratio
      body_part: Feet
      operator: between
      range: [0.80, 1.40]
      unit: ratio
      tolerance: 0.05
      min_confidence: 0.50
    penalty:
      max_points: 0.5
      severity: minor
~~~

字段与代码的对应关系：

- id 必须唯一；name 用于 score.json 和 report.md；action、phase 必须与 evidence.json 完全一致。
- predicate.metric 和 predicate.body_part 必须使用 3.2 中的名称。新增物理量时，先在 scripts/pose_to_evidence.py 的 body_metrics() 中实现，再写 YAML。
- operator 只支持 ">"、">="、"<"、"<="、between。前四种使用 threshold，between 使用 [lower, upper] 的 range。
- 对 ">" 和 ">="，实际值超过阈值即违规；对 "<" 和 "<="，实际值低于阈值即违规；between 表示落在区间外才违规。
- tolerance 是软概率的平滑尺度；uncertainty 决定边界是否需要复核；min_confidence 决定低置信度是否需要复核；duration_frames 要求证据片段至少持续指定帧数。
- penalty.max_points 是规则触发时的固定扣分。aggregation.type 和 evidence.required 当前只记录规则意图，engine.py 尚未据此改变聚合或执行逻辑。

评分器通过三元组 (phase, body_part, metric) 找候选 fact，再按该规则的 predicate 计算违规。写新规则时，至少准备 pass、violation、no_evidence 三条证据单元测试，并检查单位、左右侧命名和帧区间。

### 4.1 当前示例规则

rules/yema_fenzong_test.yaml 已包含野马分鬃第二阶段的五条测试规则：右膝 joint_angle > 115 degree（扣 1.0）、Torso torso_tilt > 20 degree（扣 0.5）、Feet foot_distance_ratio < 0.80（扣 0.5）、Right_Wrist wrist_height_ratio < 0.85（扣 0.5）、Phase phase_duration < 20 frame（扣 0.5）。它是联调样例，不代表正式裁判规程。

### 4.2 评分器的执行算法

rule_scoring/engine.py 对每条规则按以下顺序执行：

1. 跳过 enabled: false 的规则，并要求 rule.action 与 evidence.action 相同（rule.action 为空时表示适用于所有动作）。
2. 在 facts 中筛选 phase、body_part、metric 都相同的候选证据；没有候选就输出 no_evidence。
3. 对每个候选计算 rule_violation(value, predicate)，并检查 duration_frames >= predicate.duration_frames。
4. 计算透明的软指标：soft_violation_score = clamp(sigmoid(signed_margin / tolerance) * confidence, 0, 1)。其中 signed_margin 对 > 为 value-threshold，对 < 为 threshold-value，对 between 为区间外距离。
5. 选择 (violation, soft_violation_score) 最大的候选作为该规则的代表证据。
6. 若 violation 为真，扣除 penalty.max_points；否则扣 0。所有规则处理完后得到 final_score。

三种 mode 的差异：

- strict：输出确定性的 pass/violation，固定扣分；仍会计算 review_required 供查看。
- review：当距离阈值不超过 uncertainty 或置信度低于 min_confidence 时，把状态改为 manual_review，供裁判复核。
- soft：保留 strict 的固定扣分，同时在 item 中增加 soft_violation_score；该值目前不参与 final_score。

因此“软概率”是白盒数学函数，不是黑盒神经网络。它只对测量噪声提供连续的风险刻度；如果研究需要概率加权扣分，应在独立实验分支中明确修改 engine.py，并同步更新评分协议和测试。

## 5. 安装依赖

建议使用 Python 3.9/3.10 和独立虚拟环境。

~~~powershell
cd D:\program\test\AlphaPose
pip install easydict six terminaltables scipy opencv-python matplotlib visdom tqdm tensorboardx pyyaml halpecocotools munkres timm==0.1.20 natsort cython
cd D:\program\test
pip install pyyaml numpy opencv-python
~~~

如果使用 GPU，请先按本机 CUDA 版本安装匹配的 PyTorch。Windows 下编译 AlphaPose 依赖失败时，建议使用 WSL2/Ubuntu。

## 6. 模型放置

手工下载模型后放到：

~~~text
D:\program\test\AlphaPose\pretrained_models\halpe26_fast_res50_256x192.pth
D:\program\test\AlphaPose\detector\yolo\data\yolov3-spp.weights
~~~

前者是 Halpe-26 姿态权重，后者是 YOLO 检测器权重。模型文件不要提交到 Git。

## 7. 一键视频评分

evaluate_video.py 将四步串起来：调用 AlphaPose 生成 alphapose-results.json，调用 pose_to_evidence.py 生成 evidence.json，调用 engine.py 生成 score.json，最后调用 generate_report.py 生成 report.md。以下命令使用人工指定的第二阶段帧范围：

~~~powershell
cd D:\program\test
python scripts\evaluate_video.py --video D:\data\yema_fenzong.mp4 --rules rules\yema_fenzong_test.yaml --workdir outputs\yema_fenzong --action 野马分鬃 --phase 第二阶段 --phase-start 120 --phase-end 220 --mode strict
~~~

结果通常位于：

~~~text
outputs/yema_fenzong/
├─ alphapose-results.json
├─ evidence.json
├─ score.json
└─ report.md
~~~

phase-start 和 phase-end 是从 0 开始的视频帧号；当前版本允许人工指定阶段范围。

如果只想查看边界风险而不改变固定扣分，可把 mode 改为 soft；如果希望边界或低置信度项直接标记为 manual_review，使用 review。多人视频可用 --track-id 选择 AlphaPose 输出中 idx 对应的人。

## 8. 分步运行

只运行 AlphaPose：

~~~powershell
cd D:\program\test\AlphaPose
python scripts\demo_inference.py --cfg configs\halpe_26\resnet\256x192_res50_lr1e-3_1x.yaml --checkpoint pretrained_models\halpe26_fast_res50_256x192.pth --video D:\data\yema_fenzong.mp4 --outdir D:\program\test\outputs\yema_fenzong
~~~

运行后先检查 JSON 是否为数组、是否包含 78 个 keypoint 数值/人，以及 image_id 是否覆盖目标阶段。若视频中有多个人，先用 score 或 idx 确认要评分的对象，再决定是否传 --track-id。

姿态 JSON 转证据：

~~~powershell
cd D:\program\test
python scripts\pose_to_evidence.py --pose-json outputs\yema_fenzong\alphapose-results.json --rules rules\yema_fenzong_test.yaml --output outputs\yema_fenzong\evidence.json --action 野马分鬃 --phase 第二阶段 --phase-start 120 --phase-end 220
~~~

单独判分：

~~~powershell
python -m rule_scoring --rules rules\yema_fenzong_test.yaml --evidence outputs\yema_fenzong\evidence.json --output outputs\yema_fenzong\score.json --mode strict
~~~

生成报告：

~~~powershell
python scripts\generate_report.py --score outputs\yema_fenzong\score.json --output outputs\yema_fenzong\report.md
~~~

示例脚本：

~~~powershell
powershell -ExecutionPolicy Bypass -File examples\run_yema_fenzong_test.ps1
~~~

分步命令中的参数名是 --output；--out 不是本项目脚本支持的别名。所有输出目录会自动创建，但输入的规则文件、视频和 checkpoint 路径必须真实存在。

## 9. 数据来源

- 规则知识：由裁判规程、项目技术规范和教练/裁判访谈整理为 rules/*.yaml；系统不会自动抓取或臆造规则。
- 视频数据：来自用户授权的本地视频目录，例如 D:\data\；同时保存视频元数据、动作阶段和真实分数。
- 姿态数据：由本地 AlphaPose/Halpe-26 推理生成，不需要上传视频。
- 证据标注：人工标注帧区间、身体部位、物理量和违规类型，用于验证 Temporal IoU、规则准确率和分数误差。
- LLM 训练数据：由“自然语言规则 -> 合法 DSL -> 证据解释”组成的本地 JSONL，不把原始视频直接作为 LLM 输入。

示例训练样本：

~~~json
{"instruction":"将规则转换为评分器 YAML","input":"野马分鬃第二阶段右膝角度不得超过115度，违规扣1分。","output":"{\"rubric\":{\"id\":\"demo\",\"name\":\"demo\",\"version\":\"1.0\",\"base_score\":10.0},\"rules\":[{\"id\":\"DEMO-KNEE-001\",\"name\":\"右膝角度\",\"action\":\"野马分鬃\",\"phase\":\"第二阶段\",\"enabled\":true,\"predicate\":{\"metric\":\"joint_angle\",\"body_part\":\"Right_Knee\",\"operator\":\">\",\"threshold\":115.0,\"unit\":\"degree\",\"tolerance\":8.0,\"uncertainty\":3.0,\"min_confidence\":0.7},\"penalty\":{\"max_points\":1.0,\"severity\":\"fixed\"}}]}"}
~~~

## 10. Qwen3-8B 本地 SFT（可选）

Qwen3 只用于规则 DSL 生成或证据报告语言化，不参与姿态测量和最终扣分。

~~~powershell
cd D:\program\test
pip install -r llm_sft\requirements-qwen3.txt
python llm_sft\download_qwen3_model.py --model Qwen/Qwen3-8B-Base --local-dir D:\models\Qwen3-8B-Base
python llm_sft\train_qwen3_sft.py --model-dir D:\models\Qwen3-8B-Base --train-file llm_sft\data\train.jsonl --eval-file llm_sft\data\valid.jsonl --output-dir outputs\qwen3-rule-sft --epochs 2 --batch-size 1 --gradient-accumulation-steps 16 --max-length 2048 --bf16
~~~

下载脚本使用 ModelScope 保存本地模型，不调用 Hugging Face API。训练集应覆盖规则字段、单位、比较运算、阶段条件、证据引用和非法输出纠正；验证集应包含未见过的规则表述和其他动作项目。

## 11. 当前限制

1. 阶段范围目前可手工指定，尚未实现稳定的自动动作分段。
2. 2D 姿态受摄像机角度、遮挡和关键点抖动影响，不能直接等同于真实 3D 关节角。
3. yema_fenzong_test.yaml 是测试规则，不代表正式裁判规程；正式使用前必须由专家审核阈值和扣分。
4. 低于 min_confidence 的姿态应标记为待复核，而不是强行扣分。
5. Qwen3 在 CPU 上不适合高效训练；建议使用 GPU，并保留规则编译器、schema 校验和沙箱执行。

## 12. 推荐执行顺序

1. 准备授权视频和 Halpe-26/YOLO 权重。
2. 单独运行 AlphaPose，确认 alphapose-results.json 非空且关键点顺序正确。
3. 运行 pose_to_evidence.py，抽查角度、帧号、部位和置信度。
4. 审核 YAML 规则，再运行 rule_scoring 生成确定性分数。
5. 对照真实分数，评估规则命中率、Temporal IoU 和分数误差。
6. 最后训练 Qwen3 SFT；若引入 PPO/RLAIF，奖励应来自规则验证链，而不是 LLM 自己判断视频。
