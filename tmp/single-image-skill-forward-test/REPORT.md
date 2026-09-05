# 单图可控视频技能：独立前向测试

测试时间：2026-09-05。被测技能：`.claude/skills/single-image-video-control/SKILL.md`。未修改技能源文件。

## 结论

技能足够指导执行一个单图→相对深度→2.5D相机侧移→可解码控制视频的真实CPU演示。没有调用付费服务、没有租GPU、没有操作真实Pod。此次运行**没有AI生成成片**，不能据此声称“一次生成高质量视频”或首轮成功率提高。

测试只使用128×256、17帧、24fps；实际媒体长0.708333秒，采样首尾跨度0.666667秒。这是缩小规模的软件前向验证，**不是用户要求的5秒完整视频，也没有完成真实模型A/B实验**。

## 模拟请求与执行选择

模拟用户要求：有一张矿场办公室图，希望一次指令得到5秒侧移视频，先做控制demo并回答能否保证一次成功，本次禁止租GPU。

依技能选择单图估深与2.5D小幅运镜。情境是静态矿场办公室，相机向右平移，桌子、矿样箱、墙上地图保持静止。相机x从0变为0.06任意单位，z保持0，固定朝向。验收看：媒体可解码、三片参数一致、首帧对齐、静物左移且近景移动较快、缺口明确披露；人物、音频与AI画质均未测。

素材来源：`output/单图可控视频_Demo/素材/original.png`。SHA256：`bc07c026f071bf62f9d418435d28827d05aba38c24e088da0fd602f64958294b`。

使用已存在隔离环境：`tmp/single-image-demo-venv`。真实调用：

```bash
tmp/single-image-demo-venv/bin/python .claude/skills/single-image-video-control/scripts/build_control.py --source output/单图可控视频_Demo/素材/original.png --out tmp/single-image-skill-forward-test --width 128 --height 256 --num-frames 17 --camera-x 0.06 --camera-z 0
tmp/single-image-demo-venv/bin/python .claude/skills/single-image-video-control/scripts/verify_bundle.py tmp/single-image-skill-forward-test --out tmp/single-image-skill-forward-test/verification.json
```

两条命令退出码均为0。Small深度模型revision为`5426e4f0f36572d16453bbda7a8389317b1bef99`，CPU推理记录3.76秒。该数值不包含依赖安装、模型下载和视频渲染。

## 实测结果

- 三片均实际解码为128×256、17帧、24fps、0.708333秒。
- 首帧编码深度与输入相对深度MAE为0.979/255，完整性检查通过。
- 最大原始投影缺口为3.555%，已输出mask且验收器准确报告最近邻补洞不等于隐藏几何重建。
- 验收器准确报告`A_baseline.mp4`、`B_depth_control.mp4`缺失；没有将文件完整性通过写成画质通过。
- 独立抽取第0、8、16帧并观察联系表：场景与矿样箱/桌/地图布局维持，侧移方向可辨，画面右缘有新增未知区域和补洞痕迹。低分辨率和短时长无法证明高质量影视观感。
- 选定近景箱(116,166)、中景桌(49,162)、后墙图(63,86)，按记录的深度与投影公式得到尾帧水平位移约-5.18、-4.89、-4.19像素。这是模型几何预测，不是假装来自视频光流的实测精度；抽帧视觉变化与该方向一致。

## 实际发现的问题

1. **自定义尺寸来源记录不正确。** `depth_provenance.json`的width/height正确写128/256，但`image_preparation`硬编码为“center crop to 4:7; Lanczos resize to 512x896”。本次实际裁切比例为1:2。应动态记录裁切比例与尺寸；否则可复现资料内部矛盾。已告知主agent。
2. **默认抽帧索引不适应可调帧数。** 脚本只自动抽0/30/60/90/120帧，本次17帧只留下第0帧。依技能的首中尾审查要求，我另外抽了0/8/16帧；建议自动索引按N产生。这个问题不阻止视频生成，但会让短测试的自动审查素材不完整。
3. **默认并非纯侧移。** 脚本默认同时x=.06、z=.08，本次明确传`--camera-z 0`满足纯侧移语义。参数和运动记录足够理解，但最好在文档提供“纯侧移”命令实例，减少直接照抄默认值造成语义偏差。这是易用性建议，不是执行错误。

未遇到安装依赖错误、模型加载错误、编码失败、数据shape错误或验证器误报AI结果存在。

## 措辞与授权合理性审查

技能明确区分一次操作、一次推理和首轮质量通过；不会合理导出“可保证一次成功”的结论。它明确仅研究/预览不启动计费资源，符合本次禁租GPU要求。生成与审查角色仅在实际AI出片时要求独立agent，本次只控制素材不需要额外租卡或冒充成片。

本次直接云GPU/API成本为0，使用本地CPU和免费公开模型下载；既未创建也未接管Pod，资源停止状态应为“不适用”，不应伪造关机证据。

观看入口：`index.html`；实测验证：`verification.json`；抽帧：`给人看/contact_sheet.png`；投影地标计算：`landmarks.json`。
