# 太极动作白盒评估系统

本项目把太极视频转换为可追溯的动作评分结果：

```text
视频
  -> AlphaPose / Halpe-26 二维关键点
  -> MotionBERT / H36M-17 三维姿态（可选）
  -> 运动学事实与时间证据
  -> YAML 规则验证
  -> 固定扣分、复核标记和评分报告
```

项目的核心原则是：模型负责姿态提取和三维提升，规则引擎负责测量解释、违规判定和扣分，LLM（如果启用）只负责规则 DSL 生成或把已经生成的证据翻译成报告。LLM 不直接观看视频，也不直接猜分数。

本文档是当前仓库的统一启动说明。原有的 [README_PROJECT_SUMMARY.md](README_PROJECT_SUMMARY.md)、[README_MOTIONBERT_3D.md](README_MOTIONBERT_3D.md) 和各子目录 README 保留，分别用于项目背景、MotionBERT 细节和模块级说明。

## 1. 当前完成情况

### 已实现

- AlphaPose Halpe-26 视频推理入口和批量处理脚本。
- Halpe-26 到 MotionBERT H36M-17 的官方关节点映射。
- 本地 MotionBERT 3D 推理，支持 `best_epoch.bin`。
- 单视频和 TaiChi 目录批量推理。
- 按文件存在性跳过已完成结果，支持断点续跑。
- 三维骨架 `X3D.npy` 的 MP4 渲染。
- AlphaPose JSON 到运动学 `evidence.json` 的转换。
- YAML 白盒规则解析、阈值判定、固定扣分和三种评分模式。
- `score.json` 和 Markdown 评分报告生成。
- Qwen3-8B 本地 SFT 代码；模型下载脚本使用 ModelScope，不依赖 Hugging Face 下载 API。

### 尚未完成

- 自动识别动作阶段；当前阶段可由 `--phase-start/--phase-end` 指定。
- `X3D.npy` 到三维证据的适配器；当前 `pose_to_evidence.py` 主要处理 AlphaPose 2D JSON。
- 真实世界坐标系、相机标定和米制地面高度。
- 正式裁判规则的专家审核和大规模标注验证。
- PPO/RLAIF；当前应先完成规则 DSL 的 SFT、规则执行评估和证据质量评估。

## 2. 目录结构

```text
D:/program/test/
├─ AlphaPose/                         # Halpe-26 姿态模型和推理代码
│  ├─ configs/halpe_26/resnet/
│  └─ pretrained_models/
├─ MotionBERT/                        # MotionBERT 源码、配置和 checkpoint
│  ├─ configs/pose3d/
│  └─ checkpoint/
├─ TaiChi/                            # 待处理的视频（avi/mp4/mov）
├─ rules/                             # YAML 评分规则
│  ├─ rules.yaml
│  └─ yema_fenzong_test.yaml
├─ rule_scoring/                      # 白盒评分器
│  ├─ engine.py
│  ├─ io.py
│  └─ __main__.py
├─ scripts/
│  ├─ evaluate_video.py                # 2D 一键评分
│  ├─ pose_to_evidence.py              # 姿态 JSON -> evidence.json
│  ├─ run_motionbert_3d.py             # 单视频 2D -> 3D
│  ├─ run_motionbert_3d.sh             # Bash 单视频入口
│  ├─ run_taichi_3d.ps1                # Windows 批量 AlphaPose + MotionBERT
│  ├─ run_taichi_3d.sh                 # Bash 批量入口
│  ├─ render_motionbert_3d.py          # 单个 X3D.npy -> MP4
│  ├─ render_taichi_3d.ps1             # 批量渲染 3D 骨架 MP4
│  └─ generate_report.py               # score.json -> report.md
├─ outputs/                            # 视频级结果
├─ schemas/evidence.schema.json        # 证据格式约束
└─ llm_sft/                            # 本地模型 SFT 代码和样例数据
```

## 3. 环境和模型

建议使用已经配置好的 `alphapose` conda 环境。至少需要 PyTorch、NumPy、PyYAML、OpenCV、`imageio`、`imageio-ffmpeg`，以及 AlphaPose 和 MotionBERT 各自的依赖。

AlphaPose 权重默认位置：

```text
AlphaPose/pretrained_models/halpe26_fast_res50_256x192.pth
AlphaPose/detector/yolo/data/yolov3-spp.weights
```

MotionBERT 3D 权重默认按以下顺序查找：

```text
MotionBERT/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin
MotionBERT/checkpoint/best_epoch.bin
```

当前代码使用：

```text
AlphaPose 配置：configs/halpe_26/resnet/256x192_res50_lr1e-3_1x.yaml
MotionBERT 配置：configs/pose3d/MB_ft_h36m_global_lite.yaml
```

模型权重不应提交到 Git。Windows 下如果 AlphaPose 的编译依赖无法安装，优先使用 WSL2/Ubuntu；如果 conda 路径不是默认值，请在 PowerShell 命令中传 `-CondaExe`。

## 4. 关键数据格式

### 4.1 AlphaPose Halpe-26

AlphaPose JSON 是数组，每条记录对应一帧中的一个人：

```json
{
  "image_id": "frame_000120.jpg",
  "category_id": 1,
  "keypoints": [x0, y0, c0, x1, y1, c1],
  "score": 0.941,
  "idx": 0
}
```

`keypoints` 必须有 78 个数，即 26 个点的 `x,y,confidence`。Halpe-26 关键点顺序为：

```text
0 Nose       1 LEye       2 REye       3 LEar       4 REar
5 LShoulder  6 RShoulder  7 LElbow     8 RElbow     9 LWrist
10 RWrist    11 LHip      12 RHip      13 LKnee     14 RKnee
15 LAnkle    16 RAnkle    17 Head      18 Neck      19 Hip
20 LBigToe   21 RBigToe   22 LSmallToe 23 RSmallToe 24 LHeel 25 RHeel
```

### 4.2 MotionBERT H36M-17

MotionBERT 不能直接使用 Halpe-26 的前 17 个点，代码会调用官方 `halpe2h36m()` 映射，输出：

```text
0 root       1 right_hip  2 right_knee 3 right_ankle
4 left_hip   5 left_knee  6 left_ankle 7 belly
8 neck       9 nose      10 head      11 left_shoulder
12 left_elbow 13 left_wrist 14 right_shoulder 15 right_elbow 16 right_wrist
```

当前输出 `X3D.npy` 的形状是 `[T, 17, 3]`。

### 4.3 坐标系限制

默认 MotionBERT 输出是模型坐标系下的归一化/尺度不确定 3D 姿态。它不是直接带真实米制单位的世界坐标。`--pixel` 只把二维 `x/y` 对齐回视频像素，不能把 `z` 变成真实深度。

因此当前可以可靠计算三维相对角度和相对距离，但不能直接声称“膝盖离地 0.32 米”。真实离地高度还需要地面平面、重力方向和尺度标定。

## 5. 单视频：AlphaPose 到 MotionBERT 3D

如果已有 AlphaPose JSON：

```powershell
cd D:\program\test
conda run -n alphapose python scripts\run_motionbert_3d.py `
  --pose-json outputs\yema_fenzong\alphapose-results.json `
  --video D:\data\yema_fenzong.mp4 `
  --motionbert-dir MotionBERT `
  --config MotionBERT\configs\pose3d\MB_ft_h36m_global_lite.yaml `
  --checkpoint MotionBERT\checkpoint\best_epoch.bin `
  --output-dir outputs\yema_fenzong\motionbert_3d `
  --primary-person `
  --render
```

主要参数：

| 参数 | 作用 |
|---|---|
| `--pose-json` | AlphaPose Halpe-26 JSON |
| `--video` | 原视频，用于 FPS 和尺寸 |
| `--checkpoint` | MotionBERT 3D 权重 |
| `--focus ID` | 多人时固定选择指定 `idx` |
| `--primary-person` | 单人视频逐帧保留最高置信度的人 |
| `--pixel` | 输出像素对齐的二维 x/y，z 仍不是米制 |
| `--render` | 同时生成 `X3D.mp4` |

输出：

```text
outputs/yema_fenzong/motionbert_3d/
├─ X3D.npy
└─ X3D.metadata.json
```

## 6. TaiChi 批量处理和断点续跑

将视频放在 `TaiChi/` 后运行：

```powershell
cd D:\program\test
powershell -ExecutionPolicy Bypass -File scripts\run_taichi_3d.ps1 `
  -InputDir D:\program\test\TaiChi `
  -OutputDir D:\program\test\outputs\TaiChi `
  -CondaEnv alphapose `
  -PrimaryPerson
```

脚本对每个视频执行：

```text
TaiChi/video.avi
  -> outputs/TaiChi/video/alphapose-results.json
  -> outputs/TaiChi/video/motionbert_3d/X3D.npy
  -> outputs/TaiChi/video/motionbert_3d/X3D.metadata.json
```

已有且非空的 AlphaPose JSON 和 `X3D.npy` 会跳过，因此可以直接重复执行。只补齐已有 JSON 的 3D 结果：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_taichi_3d.ps1 `
  -InputDir D:\program\test\TaiChi `
  -OutputDir D:\program\test\outputs\TaiChi `
  -CondaEnv alphapose `
  -MotionBertCheckpoint D:\program\test\MotionBERT\checkpoint\best_epoch.bin `
  -PrimaryPerson `
  -Only3D
```

如果多人视频中已经确认了某个 AlphaPose `idx`，可使用 `-Focus <ID>`；单人太极视频优先使用 `-PrimaryPerson`。运行日志位于 `outputs/TaiChi/batch_taichi_3d.log`。

Bash/WSL 入口：

```bash
bash scripts/run_taichi_3d.sh --input-dir D:/program/test/TaiChi \
  --output-dir D:/program/test/outputs/TaiChi \
  --primary-person
```

## 7. 3D 骨架视频渲染

对所有已有 `X3D.npy` 批量渲染：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\render_taichi_3d.ps1 `
  -OutputDir D:\program\test\outputs\TaiChi `
  -CondaEnv alphapose
```

该脚本默认跳过已有且非空的 `X3D.mp4`。强制重渲染：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\render_taichi_3d.ps1 `
  -OutputDir D:\program\test\outputs\TaiChi `
  -CondaEnv alphapose `
  -Overwrite
```

单个视频：

```powershell
conda run -n alphapose python scripts\render_motionbert_3d.py `
  --pose-3d outputs\TaiChi\v_TaiChi_g01_c01\motionbert_3d\X3D.npy `
  --metadata outputs\TaiChi\v_TaiChi_g01_c01\motionbert_3d\X3D.metadata.json `
  --output outputs\TaiChi\v_TaiChi_g01_c01\motionbert_3d\X3D.mp4
```

渲染结果是骨架检查视频，用来检查左右肢体、拓扑和时间连续性，不是叠加在原视频上的真实世界 AR 画面。

批量检查数量：

```powershell
Get-ChildItem outputs\TaiChi -Recurse -Filter X3D.npy | Measure-Object
Get-ChildItem outputs\TaiChi -Recurse -Filter X3D.mp4 | Measure-Object
```

## 8. 2D 规则评分闭环

### 8.1 生成证据

```powershell
python scripts\pose_to_evidence.py `
  --pose-json outputs\yema_fenzong\alphapose-results.json `
  --rules rules\yema_fenzong_test.yaml `
  --output outputs\yema_fenzong\evidence.json `
  --action 野马分鬃 `
  --phase 第二阶段 `
  --phase-start 120 `
  --phase-end 220
```

当前内置 2D 物理量：

```text
Right_Knee / joint_angle
Torso / torso_tilt
Feet / foot_distance_ratio
Right_Wrist / wrist_height_ratio
Phase / phase_duration
```

证据事实的最小结构：

```json
{
  "frame_range": [146, 150],
  "phase": "第二阶段",
  "body_part": "Right_Knee",
  "metric": "joint_angle",
  "value": 118.0,
  "unit": "degree",
  "confidence": 0.94,
  "source": "alphapose-json"
}
```

### 8.2 运行评分器

```powershell
python -m rule_scoring `
  --rules rules\yema_fenzong_test.yaml `
  --evidence outputs\yema_fenzong\evidence.json `
  --output outputs\yema_fenzong\score.json `
  --mode strict
```

评分模式：

- `strict`：谓词成立即扣规则的固定分。
- `review`：边界不确定或置信度低时标记 `manual_review`。
- `soft`：额外输出透明的 `soft_violation_score`，但当前不改变正式扣分。

正式分数为：

```text
final_score = max(0, base_score - sum(triggered fixed penalties))
```

当前的软指标是白盒数学函数：

```text
soft_violation_score = clamp(sigmoid(signed_margin / tolerance) * confidence, 0, 1)
```

它用于表达阈值附近的风险，不是黑盒神经网络，也不会在 `strict` 模式下偷偷改变分数。

### 8.3 生成报告

```powershell
python scripts\generate_report.py `
  --score outputs\yema_fenzong\score.json `
  --output outputs\yema_fenzong\report.md
```

报告会列出规则状态、实际值、证据帧、扣分、置信度和待人工复核建议。

### 8.4 2D 一键流程

```powershell
python scripts\evaluate_video.py `
  --video D:\data\yema_fenzong.mp4 `
  --rules rules\yema_fenzong_test.yaml `
  --workdir outputs\yema_fenzong `
  --action 野马分鬃 `
  --phase 第二阶段 `
  --phase-start 120 `
  --phase-end 220 `
  --mode strict
```

该脚本依次运行 AlphaPose、证据转换、规则评分和报告生成。它目前是 2D 评分入口，不会自动调用 MotionBERT。

## 9. 评分规则书写方式

规则文件是 YAML，必须包含 `rubric` 和 `rules`：

```yaml
rubric:
  id: taichi-yema-fenzong-v1
  name: 野马分鬃第二阶段评分
  version: "1.0"
  base_score: 10.0

rules:
  - id: YMZ-P2-KNEE-001
    name: 第二阶段右膝屈曲不足
    action: 野马分鬃
    phase: 第二阶段
    enabled: true
    predicate:
      metric: joint_angle
      body_part: Right_Knee
      operator: ">"
      threshold: 115.0
      unit: degree
      tolerance: 8.0
      uncertainty: 3.0
      min_confidence: 0.70
      duration_frames: 1
    penalty:
      max_points: 1.0
      severity: fixed
```

规则匹配键是：

```text
(action, phase, predicate.body_part, predicate.metric)
```

支持的 `operator` 是 `>`、`>=`、`<`、`<=` 和 `between`。`threshold` 用于单阈值，`range: [lower, upper]` 用于区间。`tolerance` 是软概率平滑尺度，`uncertainty` 和 `min_confidence` 用于复核标记，`penalty.max_points` 是触发规则时的固定扣分。

新增物理量时，先在 `scripts/pose_to_evidence.py` 的 `body_metrics()` 实现计算，再在 YAML 中引用；只修改 YAML 不能自动产生新的运动学量。

## 10. 地面高度规划

当前版本尚未输出真实米制地面高度。推荐增加独立的 `GroundHeightEstimator`，不要把 MotionBERT 的某一轴直接当作离地高度：

```text
X3D.npy
  -> 坐标旋转、尺度恢复
  -> 地面平面 n^T X + d = 0
  -> 每个节点 h = n^T P + d
  -> ground_heights.npy / ground_height.json
```

需要支持的输入：

```text
X3D.npy                 [T,17,3]
X3D.metadata.json
calibration.json        可选，相机内外参和地面平面
subject_height_m        可选，人体真实身高
```

输出建议：

```text
X3D_world.npy
joint_heights.npy       [T,17]
ground_plane.json
ground_height.metadata.json
```

有相机标定时，地面平面可由标定板、ArUco、三个地面点或已知相机高度获得；没有标定时，可用低速度、低高度的左右脚踝估计相对地面高度，但只能得到相对单位，不能保证米制精度。后续多任务模型可预测 `3D pose + scale + gravity + foot contact + ground plane`，但最终高度仍应由显式几何公式计算，以保持可解释性。

三维规则可扩展为：

```yaml
  - id: YMZ-P2-KNEE-HEIGHT-001
    name: 右膝离地高度
    action: 野马分鬃
    phase: 第二阶段
    predicate:
      metric: joint_height
      body_part: right_knee
      reference: ground
      operator: between
      range: [0.30, 0.65]
      unit: meter
      tolerance: 0.03
    penalty:
      max_points: 0.5
      severity: fixed
```

在三维证据适配器完成前，不要把这类规则接入正式评分。

## 11. LLM SFT 和后续训练路线

LLM 的职责是：

```text
自然语言规则 -> 合法 YAML/DSL
结构化 Evidence Graph -> 专业报告文本
```

不应让 LLM 直接从视频预测关键点、物理量或最终分数。

Qwen3-8B 的本地 SFT 代码位于 `llm_sft/`。模型下载使用 ModelScope：

```powershell
pip install -r llm_sft\requirements-qwen3.txt
python llm_sft\download_qwen3_model.py `
  --model Qwen/Qwen3-8B-Base `
  --local-dir D:\models\Qwen3-8B-Base
```

本地训练：

```powershell
python llm_sft\train_qwen3_sft.py `
  --model-dir D:\models\Qwen3-8B-Base `
  --train-file llm_sft\data\train.jsonl `
  --eval-file llm_sft\data\valid.jsonl `
  --output-dir outputs\qwen3-rule-sft `
  --epochs 2 `
  --batch-size 1 `
  --gradient-accumulation-steps 16 `
  --max-length 2048 `
  --bf16
```

建议训练顺序：

1. 规则 DSL SFT：自然语言规则、合法 YAML、字段校验和错误修正。
2. Evidence-to-report SFT：只输入 evidence/score，输出不增加事实的裁判报告。
3. 规则执行评估：测试 DSL 编译成功率、规则字段准确率和证据引用准确率。
4. PPO/RLAIF：奖励来自规则执行链的分数误差、DSL 可执行性和证据一致性，而不是 LLM 自己给奖励。

训练数据应包含规则版本、动作、阶段、阈值、单位、扣分、正例、反例、无证据例和非法 DSL 修正例。原始视频不直接作为 LLM SFT 文本输入。

## 12. 数据来源和实验评价

- 规则：来自裁判规程、技术规范、教练/裁判访谈，人工整理为 `rules/*.yaml`。
- 视频：用户授权的本地 `TaiChi/` 或其他输入目录。
- 2D 姿态：本地 AlphaPose Halpe-26 推理结果。
- 3D 姿态：本地 MotionBERT checkpoint 推理结果。
- 证据标注：人工标注动作阶段、违规帧区间、身体部位、物理量和真实分数。

建议报告以下指标：

```text
关键点质量：检测置信度、缺失率、抖动率
规则质量：predicate accuracy、precision、recall
证据质量：Temporal IoU、部位准确率、数值误差
评分质量：MAE、RMSE、SRCC、人工复核率
泛化能力：新动作、新规则、新拍摄角度的 zero-shot 结果
```

## 13. 推荐操作顺序

```text
1. 确认 AlphaPose 和 MotionBERT 权重路径
2. 单视频运行 AlphaPose，检查 Halpe-26 JSON
3. 单视频运行 MotionBERT，检查 X3D.npy 和 X3D.mp4
4. 批量运行 scripts/run_taichi_3d.ps1
5. 批量渲染并人工检查骨架拓扑、左右侧和时间连续性
6. 用 pose_to_evidence.py 生成 evidence.json
7. 用 rule_scoring 生成 score.json
8. 用 generate_report.py 生成 report.md
9. 标注真实分数和证据，评估规则准确率
10. 最后进行 Qwen3 SFT，再考虑 PPO/RLAIF
```

快速自检：

```powershell
python scripts\run_motionbert_3d.py --help
python scripts\render_motionbert_3d.py --help
python scripts\pose_to_evidence.py --help
python -m rule_scoring --help
python -m py_compile scripts\run_motionbert_3d.py scripts\render_motionbert_3d.py scripts\pose_to_evidence.py rule_scoring\engine.py
```

本项目目前最可靠的可运行闭环是“AlphaPose 2D -> 2D 运动学证据 -> YAML 白盒评分 -> 报告”。MotionBERT 3D 和地面高度属于正在扩展的测量层；在完成世界坐标标定和三维证据适配器前，三维结果应作为检查和研究数据使用，不应直接当作正式米制裁判依据。
