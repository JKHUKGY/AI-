# 镜01 → MiniMax Design 手动生成包

这一包是把 `h3_jobs.json` 里的 `ep01_镜01+1` 搬到 **MiniMax Design**
（design.minimax.io 的官方桌面/网页 Harness，云端跑 H3、按 credits 计费）
手动生成用的。模型跟自建那条一样是 H3 ref2va，**所以提示词不用改写、直接粘**。

## 包里有什么

| 文件 | 用途 |
|---|---|
| `prompt.txt` | 六段 ref2va 提示词，2437 字符，整段粘进 Design 的 prompt 框 |
| `Picture1_ep01_镜01_00.png` | 参考图，941×1672（9:16）。**必须是第 1 张上传的图**，提示词里叫 `<Picture 1>` |

## Design 里怎么填

1. 模式选 **Ref2VA / omni-reference**（不是 Image to Video）。
   提示词是按 ref2va 六段格式装的，`retention_analysis` 段写的是
   `partially_preserved`——首帧是**构图参考不是焊死的第 0 帧**。
   要首帧焊死就得走 FL2VA，那要重装提示词（见下面"另一条路"）。
2. 参考图只上传 `Picture1_*.png` 这一张，顺序第一。
3. 画幅 **9:16**。
4. 时长选 **6 秒**（自建那条算出来是 141 帧 @24fps = 5.875s，Design 只给整秒档，取 6）。
   ⚠️ 别想着只生成镜01：镜01 自己只有 3.375s，**低于 H3 的 4 秒下限**，
   所以上游 `group_h3_units.py` 已经把镜01+镜02 并成了一条、内部在 00:03.375 切一刀。
5. 分辨率能开到 **1080p 或 2K**。自建那条锁 768 短边是因为开源权重原生只有 768p，
   云端 API 支持到 2K——这是走 Design 的净收益，别沿用 768。
6. **seed 填不了**：Design 不暴露 seed，`seed=714203` 在这条路上无效。
   复现靠不了随机种，只能多抽几条挑一条。

## 验收看什么

- 00:03.375 那一刀有没有真的切成背影反打（[Shot 2]），还是从头到尾一个机位。
  这是这条并镜最可能失败的地方——**镜02 自己的关键帧没作为 `<Picture 2>` 传进去**，
  第二个 shot 全靠文字描述撑（装配器把手填的 `references` 映射成 `<Subject N>` 而不是
  `<Picture N>`，要真给第二刀配底板得改 `build_h3_prompt.py`）。
- 江砚的脸/发型/洗白浅蓝衬衫有没有中途换人。
- 右手那只透明塑料袋还在不在（档案写左手、以图为准是右手）。
- H3 原生出 32kHz 立体声，**要听**：门轴干响 → 水泥地两声脚步 → 一声闷的土地脚步。

## 另一条路：FL2VA 首帧焊死

Design 的 Image to Video 走 FL2VA，首帧是真的第 0 帧、构图最稳，
但提示词得重装（`--keyframe-role first_frame` + `--task fl2va`）：

```
python3 .claude/skills/short-drama-video-gen/scripts/build_h3_prompt.py \
    "output/出狱后我成为了非洲矿王_v2/videos/ep01/shot_cards.json" \
    --only ep01_镜01 --task fl2va --keyframe-role first_frame -o /tmp/fl2va.json
```
只是镜01 单独 3.375s 过不了 4 秒闸门，要么把卡里 `duration_sec` 拉到 ≥4，
要么还是并着镜02 跑。
