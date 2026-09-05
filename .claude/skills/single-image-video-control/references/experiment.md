# 运行与实验

## 本地控制素材

CPU示例依赖：Python 3.12、ffmpeg/ffprobe、PyTorch CPU、torchvision、Pillow、NumPy、Transformers与OpenCV。先检查磁盘，为隔离环境和Small模型至少预留2GB；环境和缓存放在任务可写目录，避免改全局Python。

```bash
python3 -m venv TASK_DIR/venv
TASK_DIR/venv/bin/pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
TASK_DIR/venv/bin/pip install --no-cache-dir transformers==4.51.3 opencv-python-headless==4.11.0.86
TASK_DIR/venv/bin/python SKILL_DIR/scripts/build_control.py --source INPUT.png --out DEMO_DIR
TASK_DIR/venv/bin/python SKILL_DIR/scripts/verify_bundle.py DEMO_DIR
```

包版本是本次已用组合，不代表最低版本或未来最佳版本。首次联网下载模型；复现时传记录中的 `--model-revision`。`--render-only` 复用深度，不重新推理；参数包含 `--width`、`--height`、`--num-frames`、`--fps`、`--camera-x`、`--camera-z`、`--fov`。这是小范围、固定朝向相机的示例，超出其范围应换完整3D渲染器，不能把拒绝参数的检查删掉就当能力扩大。

纯侧移使用 `--camera-z 0`。需要分段安排相机时，可传 `--camera-keyframes PATH.json`，JSON为按帧排序的 `[{"frame":0,"xyz":[0,0,0]},{"frame":360,"xyz":[0.04,0,0.16]}]`，覆盖0到末帧，坐标为假定单位。相邻键之间用smoothstep插值；重复位置表示停留。这个文件安排相机，不会给人物或纸张自动生成动作。

输出：

- `素材/original.png`、`first_frame.png`：原图和准备后的首帧。
- `素材/relative_inverse_depth.npy`、`depth16.png`：原始相对深度；亮=近。
- `素材/scene.ply`：普通彩色点云，不是3D高斯模型。
- `素材/depth_control.mp4`：供模型编码的控制片。
- `给人看/reprojection_preview.mp4`：确定性几何预览，不是AI成片。
- `给人看/coverage_mask.mp4`：白色代表原始投影缺口；不是本次已确认可直接交给任何模型的inpaint mask。
- `机器文件/camera_path.json`、`depth_provenance.json`：相机假设、逐帧缺口、模型来源、原图hash。

没有AI生成结果的情况下，以上输出只能证明控制素材链可运行。

## A/B安排

先确定目标情境与验收点，并冻结测试输入。A为当前图生视频基线，B加入控制。尽量同模型同pipeline；无法同pipeline时按“两个工作流对照”报告。记录基础模型/适配器/代码revision、prompt散列、seed、fps、frame count、分辨率、各级控制分辨率、所有额外参数。

一个 seed 的一对输出不能估计首轮成功率，也不能证明所有镜头都改善。后续可按空场运镜、单人动作、双人遮挡分层，每类预先选多个镜头与多个seed。统计所有首轮输出，禁止只挑最好看的结果。

## 审查

1. 对照目标情境判断内容是否仍正确，而不只逐字匹配生成提示词。
2. 同时观察原图、控制RGB预览、深度片和生成视频，抽取首、中、尾帧与运动变化处。
3. 测前中后景至少各一个地标。相机右移时，静态点一般左移；如果叠加向前运动，右侧近景也可能右移，方向需由已记录投影路径计算。
4. 仅背景有像素变化不等于真实运镜。检查不同深度的相对位移、遮挡关系和新增区域合理性。
5. 光流只当辅助：低纹理、遮挡和模型新细节会让跟踪错误。报告有效点数、失效点，不能让一个光流分数自动决定影视质量。
6. 看边缘熔化、家具尺寸、纹理闪烁、人物身份/动作/接触。没有人物或音频的实验就把这些维度标“未测”。
7. 清楚区分投影缺口的填补与真实观察到的内容。大范围未知区先缩小运镜或补场景，不无限换seed。

## 报告和观看入口

`python SKILL_DIR/scripts/build_viewer.py DEMO_DIR` 可生成无需外部网络的 `给人看/演示首页.html`，包含实际存在的原图、点云、控制片与A/B视频。报告默认链接到 `DEMO_DIR/可行性报告.md`；将实际结果摘要写入 `机器文件/viewer_summary.txt` 后重建页面。该脚本只展示已有文件，缺失成片会显示尚未生成。

报告至少包含：任务与结论边界、路线比较与官方链接、选型理由、真实运行配置、结果与失败、费用和资源停止状态、后续能改变结论的实验。

观看入口并排放输入图、几何预览、控制视频、A/B成片，提供原视频下载；生成未完成就显示未完成。片段文件检查通过不代表内容验收通过。需要高清润色时单列额外生成步骤和成本，不把多阶段流程说成一次模型推理。


## 复用本次15秒相机安排

`assets/camera_15s.json` 安排0–6秒小幅右移/前移、6–13秒继续前移、13–15秒停稳。适用于与本例相近的单图视差测试；新图片的深度和遮挡仍须重新验收。

```bash
TASK_DIR/venv/bin/python SKILL_DIR/scripts/build_control.py --source INPUT.png --out DEMO_DIR --num-frames 361 --fps 24 --camera-keyframes SKILL_DIR/assets/camera_15s.json
```

镜头卡另由原视频技能装配，时长必须同为361帧/24fps。`assets/weights.example.json` 仅是字段模板，把每个路径改为已核验的真实checkpoint，不能直接拿占位路径执行。A/B同一任务分别调用推理入口，结果目录中的视频名可直接接观看页生成器。

## 2026-09-05 实测边界

矿场空办公室单图，512×896、361帧、24fps，A/B同seed且各一次成功输出。B更接近小幅运镜和末段停稳，但日照变化、纸张动作幅度仍偏离情境；A大幅推进且结尾不停。该结果支持继续研究结构控制，不能保证首轮高质量或外推到人物。深度只控制静态空间，纸张动作仍由文字驱动；要改进动态物体，应考虑实际动画/轨迹而不只追加形容词。

正式两路采用A100 PCIe80GB+CPU卸载，单路约4.3分钟；这些数字只对应当次模型/VAE/输出尺寸。此前发生两次加载OOM和一次遗漏推理上下文的技术失败，都应计入工程成本。不可将失败抹去后宣传整条链路“第一次就成功”。
