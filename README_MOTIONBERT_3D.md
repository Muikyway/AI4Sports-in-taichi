# MotionBERT 三维姿态流水线

这一步把 AlphaPose 输出的 Halpe-26 二维骨骼送入 MotionBERT，生成 H36M-17 三维骨骼。脚本复用 MotionBERT 官方 `WildDetDataset` 和 `halpe2h36m` 映射，不会把 Halpe-26 的前 17 个点错误地当作 H36M-17。

## 输入

- AlphaPose JSON：数组格式，每条记录对应一个人，必须有 `image_id` 和长度为 78 的 `keypoints`（26 个点，每点 `x,y,confidence`）。
- 原始视频：用于读取 FPS、分辨率，以及可选的三维结果渲染。
- MotionBERT checkout：默认目录为项目根目录下的 `MotionBERT/`。
- 3D checkpoint：默认查找 `MotionBERT/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin`。当前仓库未包含权重，需要自行下载并放到该路径，或通过 `--checkpoint` 指定实际路径。

## 运行环境

请在已经配置好的 MotionBERT 环境中运行，环境至少需要 MotionBERT 依赖、PyTorch、NumPy、`imageio` 和 `imageio-ffmpeg`。脚本使用 `num_workers=0`，适合 Windows/WSL，避免官方示例在 Windows 多进程 DataLoader 下的启动问题。

## 推荐启动命令

在 Git Bash、WSL 或 Linux shell 中执行：

```bash
bash scripts/run_motionbert_3d.sh \
  --pose-json outputs/yema_fenzong/alphapose-results.json \
  --video D:/data/yema_fenzong.mp4 \
  --motionbert-dir MotionBERT \
  --config MotionBERT/configs/pose3d/MB_ft_h36m_global_lite.yaml \
  --checkpoint MotionBERT/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin \
  --output-dir outputs/motionbert_3d \
  --focus 0 \
  --render
```

也可以直接调用 Python 脚本：

```bash
python scripts/run_motionbert_3d.py \
  --pose-json outputs/yema_fenzong/alphapose-results.json \
  --video D:/data/yema_fenzong.mp4 \
  --checkpoint MotionBERT/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin \
  --output-dir outputs/motionbert_3d
```

在 PowerShell 中可以直接使用第二条命令，把路径改成 Windows 路径；`.sh` 包装器需要 Git Bash、WSL 或其他 Bash 环境。

## 参数

| 参数 | 必需 | 作用 |
| --- | --- | --- |
| `--pose-json` | 是 | AlphaPose Halpe-26 JSON |
| `--video` | 是 | 原始视频 |
| `--motionbert-dir` | 否 | MotionBERT 源码目录 |
| `--config` | 否 | 3D 配置，默认 global lite |
| `--checkpoint` | 是（需存在） | 3D 模型权重 |
| `--output-dir` | 否 | 输出目录 |
| `--focus` | 多人时必需 | 选择 AlphaPose 的 `idx` |
| `--clip-len` | 否 | 推理窗口，默认 243 |
| `--pixel` | 否 | 保留与原视频像素对齐的二维 x/y |
| `--render` | 否 | 额外生成 `X3D.mp4` |

如果同一 `image_id` 出现多条记录，说明该帧检测到多人。脚本会要求显式传入 `--focus <idx>`，避免把不同人的骨骼混合评分。

## 输出

成功后 `outputs/motionbert_3d/` 中包含：

- `X3D.npy`：形状为 `[帧数, 17, 3]` 的 H36M-17 三维骨骼，点顺序由 MotionBERT 定义。
- `X3D.metadata.json`：输入文件、配置、权重、FPS、帧数、坐标系和输出形状等元数据。
- `X3D.mp4`：仅在传入 `--render` 时生成的三维可视化视频。

默认输出是 MotionBERT 的 root-relative、归一化三维坐标，不是带真实米制尺度的世界坐标。`--pixel` 会按官方实现把输出 x/y 转回视频像素坐标，但 z 仍是模型尺度，不能当作真实米制深度。

## 与规则评分的衔接

这一步的终点是 `X3D.npy`。现有 `scripts/pose_to_evidence.py` 面向 AlphaPose 二维 JSON；要让规则评分使用三维关节角，还需要增加一个 `X3D.npy -> evidence.json` 适配器，并在规则 YAML 中声明三维指标（例如 `joint_angle_3d`）。因此不要直接把 `X3D.npy` 当作 AlphaPose JSON 传给 `pose_to_evidence.py`。

## 检查命令

```bash
python scripts/run_motionbert_3d.py --help
python -m py_compile scripts/run_motionbert_3d.py
```

## TaiChi 批量处理

项目根目录下的 `scripts/run_taichi_3d.ps1` 会扫描 `TaiChi/` 下的 `.avi/.mp4/.mov`，在 `alphapose` conda 环境中逐个运行 AlphaPose，并按视频名写入 `outputs/TaiChi/<视频名>/alphapose-results.json`。如果默认 MotionBERT checkpoint 存在，它会继续写入每个目录下的 `motionbert_3d/X3D.npy`；不存在时只生成二维 JSON，并在 `batch_taichi_3d.log` 中记录原因。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\run_taichi_3d.ps1 `
  -InputDir D:\\program\\test\\TaiChi `
  -OutputDir D:\\program\\test\\outputs\\TaiChi `
  -CondaEnv alphapose `
  -Render
```

等价的 Bash 入口为 `scripts/run_taichi_3d.sh`。批处理支持断点续跑，已有且非空的 `alphapose-results.json` 会被跳过。

推理前应确认：AlphaPose JSON 非空、每条 `keypoints` 长度为 78、视频可被 FFmpeg 读取、配置文件存在、checkpoint 文件存在。

### 使用项目根目录下的 `best_epoch.bin`

`run_taichi_3d.ps1` 会自动依次查找以下两个位置：

1. `MotionBERT/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin`
2. `MotionBERT/checkpoint/best_epoch.bin`

因此你当前放置在第 2 个位置的权重可直接使用。该权重是 DataParallel 格式，脚本会自动去掉 `module.` 前缀。对应配置使用 `MB_ft_h36m_global_lite.yaml`。

### 仅运行 MotionBERT（断点续跑）

当 AlphaPose JSON 已经存在时，使用 `-Only3D` 可跳过视频解析：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\run_taichi_3d.ps1 `
  -InputDir D:\\program\\test\\TaiChi `
  -OutputDir D:\\program\\test\\outputs\\TaiChi `
  -CondaEnv alphapose `
  -MotionBertCheckpoint D:\\program\\test\\MotionBERT\\checkpoint\\best_epoch.bin `
  -PrimaryPerson `
  -Only3D
```

每个视频的 3D 结果位于 `outputs/TaiChi/<video>/motionbert_3d/`：`X3D.npy` 形状为 `[T,17,3]`，`X3D.metadata.json` 记录输入、配置和坐标系统。

`-PrimaryPerson` 适用于单人太极视频。某些帧会有低质量的重复检测，而这些检测在当前 AlphaPose JSON 中可能共享同一个 `idx`；该参数会在每一帧保留 `score` 最高的人体，并将实际使用的序列保存为 `motionbert_3d/alphapose-primary-person.json`。元数据中的 `primary_selection_frames` 给出发生选择的帧数。多人比赛或主角频繁遮挡时，不应使用它，应先实现跨帧人体跟踪后再送入 MotionBERT。

### 生成 3D 骨架视频

对已生成的 `X3D.npy`，无需再次运行 3D 推理。以下命令会生成每个视频对应的 `motionbert_3d/X3D.mp4`，已有且非空的 MP4 默认跳过：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\render_taichi_3d.ps1 `
  -OutputDir D:\\program\\test\\outputs\\TaiChi `
  -CondaEnv alphapose
```

单个视频也可单独渲染：

```powershell
conda run -n alphapose python scripts\\render_motionbert_3d.py `
  --pose-3d D:\\program\\test\\outputs\\TaiChi\\v_TaiChi_g01_c01\\motionbert_3d\\X3D.npy `
  --metadata D:\\program\\test\\outputs\\TaiChi\\v_TaiChi_g01_c01\\motionbert_3d\\X3D.metadata.json `
  --output D:\\program\\test\\outputs\\TaiChi\\v_TaiChi_g01_c01\\motionbert_3d\\X3D.mp4
```

该 MP4 是 MotionBERT 归一化三维坐标的骨架动画，用于检查骨架拓扑、左右肢体和时间连续性；它不表示真实世界米制尺度，也不是叠加在原始视频上的 AR 画面。
