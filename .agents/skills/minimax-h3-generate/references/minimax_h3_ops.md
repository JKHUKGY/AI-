# MiniMax-H3 实操参考

H3 跟 LTX-2.5 是两套完全不同的东西，别把 LTX 的经验直接套过来。这份文档记
两件事：**官方规格里会咬人的硬约束**，和**我们这条流水线接它时的具体做法**。

来源：`MiniMaxAI/MiniMax-H3` 仓库的 `README.md`、
`docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md`、
`docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md`、
`scripts/readme/reproducible-768p-*.sh`，以及 **diffusers 官方文档
`api/pipelines/minimax_h3`**（2026-09-04 通读）。

> ⚠️ **两处官方口径不一致的地方，本文档一律取严的**，并标出来源。
> 遇到冲突别自己折中。

---

## 0. 本仓库的既定选择

**只用 `ref2va`。**（2026-09-04 定）

所以：**不需要 FL2VA 那 144GB**，卷也不用为它扩容。Ref2VA 已经下好在
`/workspace/MiniMax-H3`（135GiB）。

`build_h3_prompt.py` 按这个决定装配**六段格式**，关键帧当 `<Picture 1>` 用
（ref guide §2.2 明确允许参考图充当某镜的首帧/构图锚点），角色三视图当
`<Subject N>` 用。

## 1. 规格：会咬人的几条

| 项 | 值 | 对我们的影响 |
|---|---|---|
| **输出时长** | **4–15 或 5–15，看走哪条路** | ⚠️ **最咬人的一条**，详见下面「时长下限到底是 4 还是 5」 |
| **帧数粒度** | `num_frames` 吸附到下一个 **`17n+5`** | video VAE 的解码粒度。**判窗口要拿吸附后的值判**，官方原话是 "the resulting duration has to stay in that window" |
| 输出帧率 | 24 FPS | 跟我们一致 |
| 输出音频 | **32kHz 立体声，原生** | H3 会**自己把台词读出来**。LTX 那条链是无声的——这是选 H3 的最大理由 |
| 分辨率 | 短边默认 768，**宽高必须是 32 的倍数** | 注意不是 LTX 的 64。开源只有 768p，2K 要走官方 `H3-Regenerate-2K`，**没开源** |
| 画幅 | 21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16 等 | 用 `aspect_ratio` 字符串，不是像素尺寸。我们的 704×1280 会被吸附成 `9:16` |
| 台词语言 | 稳定支持 11 种（含中文） | 语言写在 `<d>[Chinese] …</d>` 标签里 |
| **guidance** | **蒸馏进权重里了** | diffusers 原话：no guider、**no `negative_prompt`**、no `guidance_scale`，每步只跑一次前向。跟 LTX distilled 同理——**否定句只会把概念注入编码器** |
| 随机性 | 一个 generator **三次抽样**（条件噪声→视频噪声→音频噪声） | 同一 generator 状态跑两次，视频和声音都一样 |

### 时长下限到底是 4 还是 5

**看你走哪个框架，不是模型本身的限制。**

| 框架 | 文档原话 | 下限 |
|---|---|---|
| **SGLang**（我们走的） | "targets a 768-pixel short edge at 24 fps for **4–15 seconds**" | **4 秒** |
| README「System Overview」 | 4–15 秒 | 4 秒 |
| vLLM recipes | Output duration 4… | 4 秒 |
| diffusers | "24 fps, **5 to 15 seconds**" | 5 秒 |

**只有 diffusers 是 5 秒**，三家说 4 秒。`build_h3_prompt.py --min-duration`
默认 **4.0**（我们走 SGLang serve），改走 diffusers 再传 5.0。

而且差别比看上去小得多，因为帧数只能取 `17n+5`（24fps），下限附近可达时长
是离散的：

```
n=5   90 帧  3.750s
n=6  107 帧  4.458s   ← 4 秒派和 5 秒派之争，只差这一个档
n=7  124 帧  5.167s
n=8  141 帧  5.875s
```

在《出狱后》v2 ep01 的 40 个单元上：下限 4 秒拦 16 个，5 秒拦 19 个，**只多 3 个**。

⚠️ **判窗口必须拿吸附后的时长判，不是原始时长**。4.71s 会吸附成 5.167s——
拿原始值判会把这种本来合法的单元误拦。（2026-09-04 写校验时踩过，
第一版拦 20 个，改对后 19 个。）

## 2. checkpoint 布局：两套布局别搞混

同一个 HF 仓库里**并排放着两种布局**：

| 布局 | 目录 | 谁用 |
|---|---|---|
| **原始 checkpoint** | `FL2VA/`、`Ref2VA/`，各自**自带完整**的 text_encoder/transformer/vae，各约 144GB | SGLang、vLLM |
| **diffusers 转换版** | 顶层 `transformer/`（t2va+fl2va）、`transformer_ref/`（ref2va），**其余组件全部共享只存一份** | diffusers |

diffusers 那套里，video VAE、audio VAE、Qwen3-VL 条件编码器、tokenizer、
processor、两个 scheduler **都是共用的**，只有主干分两份。所以走 diffusers
时想同时支持三种任务，也只多一份主干，不是多一整套 144GB。

我们下的是**原始布局的 `Ref2VA/`**（走 SGLang 用它）。如果改走 diffusers，
`ModularPipeline.from_pretrained(..., workflow="ref2va")` 会自己去取
`transformer_ref/` 和共享组件，**不用手动下载**。

下载（`hf` 在 LTX 那个 venv 里已经有）：

```bash
hf download MiniMaxAI/MiniMax-H3 --include "Ref2VA/**" "model_index.json" \
  --local-dir /workspace/MiniMax-H3 --max-workers 4
```

⚠️ **通配符必须是 `Ref2VA/**`，写 `Ref2VA/*` 会静默只下顶层几个小文件**——
实测下完只有 9.9MB，`hf` 还打印 `✓ Downloaded`，很容易以为成功了。

验完整性别只看 `du`：

```bash
find /workspace/MiniMax-H3 -name '*.incomplete' | wc -l   # 必须是 0
```

`du -sh` 报 GiB、HF 页面标十进制 GB：**144.1GB ≈ 135GiB**，看到 135G 是对的。

实测下载速度约 **7GB/分钟**，144GB 约 25 分钟。**会抢 Network Volume 的 I/O**：
跟正在跑的生成任务并行会把生成从 2 分钟/镜拖到 5–7 分钟/镜，能错开就错开。

## 3. 显卡：单张 4090 就够，而且可以不量化

> ⚠️ 这一节 2026-09-04 **改过两次**，两次都是我判断错了，记在这里免得再犯：
> 第一次只看 README 的 4 卡命令，误判成"官方要 4 卡、$6/hr"；
> 第二次看了 diffusers 的低显存配方，改口成"便宜卡必须走 diffusers、
> 所以得吃 5 秒下限"——**也是错的**，因为我没去看 SGLang 自己的 cookbook。
> **教训：README 里的那条命令是"追求速度的拓扑"，不是显存门槛；
> 判断门槛要去看各框架自己的 cookbook/recipes，不要从一条示例命令外推。**

组件体量（SGLang/vLLM 口径，BF16）：两个 52-block 的联合视音频 DiT
**各 66.3GB**、共享的 Qwen3-VL layer-50 编码器 **51.5GB**、video VAE 约 10GB、
audio VAE 约 0.6GB。（diffusers 文档给的编码器数字是 62.1GB，口径略有出入。）

**只加载一个 DiT 能省一大块**——vLLM 文档明说：`--task-type fl2va` 或
`ref2va` 是"当硬件需要只load 一个 DiT 来省显存/内存时"用的。我们既定只用
ref2va，天然吃到这个好处。

### SGLang 实测验证过的配方（按便宜排）

**① 1× RTX 4090 24GB —— 最便宜，而且可以不量化**

```bash
sglang serve --model-path MiniMaxAI/MiniMax-H3 --model-variant ref2va \
  --attention-backend fa --performance-mode memory \
  --layerwise-offload-components dit,text_encoder \
  --dit-offload-prefetch-size 1 --dit-layerwise-resident-layers 0 \
  --enable-torch-compile false --port 30011
# 想再省一点可以加 --quantization kitchen_int8（需先 pip install comfy-kitchen）
```

官方原话两条关键的：

> The same flags work on `sglang serve`. Drop `--quantization` for the BF16
> baseline; everything else stays identical. **GPU peak stays about 18 GB
> either way** because streaming offload is set by the offload buffers and VAE
> decode, not the weight dtype.

也就是说：**量化是可选的，不是容量刚需**——BF16 峰值也就约 18GB。
所以默认**别量化**，先拿无损的跑。

> Keep `vae` out of `--layerwise-offload-components`: putting the VAE decoder
> in layerwise offload re-streams about 9 GiB on each of 167 decode tiles.

**VAE 千万别放进 offload 列表**，会在 167 个解码 tile 上各重新流 9GiB。

**② 2× RTX 5090 32GB —— 官方标的"最快的 32GB 无损工作点"**

```bash
sglang serve --model-path MiniMaxAI/MiniMax-H3 --model-variant ref2va \
  --num-gpus 2 --tp-size 2 --ulysses-degree 1 --encoder-parallel auto \
  --performance-mode memory \
  --layerwise-offload-components dit,text_encoder,vae \
  --dit-offload-prefetch-size 1 --dit-layerwise-resident-layers 20 \
  --enable-torch-compile false --port 30011
```

官方说 layerwise placement 是**无损的**（只改参数放置和搬运调度，不改
BF16/FP32 的去噪和 VAE 数学）。这条在 2× RTX 5090（32GB）+ 377GiB 宿主内存上
验证过，官方建议用 **384GiB 级别的机器**。

**③ 4×H100 / 4×H200** —— 追求速度才用，就是 README 里那条命令。

### 价格对照（RunPod 2026-09）

| 配置 | $/hr | 备注 |
|---|---|---|
| **1× RTX 4090 24GB** | **$0.34** | 最便宜，BF16 无损，峰值约 18GB |
| 1× RTX 5090 32GB | $0.69 | |
| 2× RTX 5090 32GB | $1.38 | 官方标的最快 32GB 无损工作点 |
| 1× A100 80GB | $1.19–1.59 | |
| 4× A100 80GB | 约 $6 | 只有追求速度才值 |

租卡用 `runpod_ops.py rent_cheapest --min-memory-gb 24`。

⚠️ **宿主内存是真正的隐藏门槛**：流式 offload 要把权重放在宿主内存里，
2×5090 那条官方点名要 384GiB 级。**租卡时要确认 Pod 的 RAM**，
别只看显存。（我们之前租的 A100 Pod 是 2TB RAM，没遇到过这个问题，
但便宜卡的 Pod 配的内存通常小得多——这条**还没实测**。）

### 还有一条路：diffusers

24–32GB 也有配方（int8 TorchAo 量化 + group offloading，约需 75GB 宿主内存），
但它是**另一套接口**（`ModularPipeline`，不是 HTTP 服务），
`h3_submit.py` 用不上，得另写远端脚本。**既然 SGLang 自己就能跑便宜卡，
没有理由为了省显存而换框架。**

**最大的提速杠杆是画布，不是显卡**：diffusers 文档说 `960x544` 每步比
`1344x768` 快约 2.3 倍，宽高只要 32 的倍数。先小画布跑通再上 768 短边。

## 4. 接口：两条路

### 4A. SGLang（原始 checkpoint，HTTP 服务）

这是跟 LTX 最大的结构性差别。LTX 是"每镜 ssh 跑一次 CLI、每次重装 67GB 权重"；
H3 是"起一个常驻服务，然后一条条 POST"。**权重只装一次**，第 2 条往后没有
装载开销——批量跑整集时这个优势很大。

```bash
sglang serve --model-path /workspace/MiniMax-H3 \
  --host 0.0.0.0 --port 30011 --model-variant ref2va
# 多卡才加 --num-gpus N --ulysses-degree N --performance-mode speed
```

```
POST /v1/videos                 提交，返回 {"id": ...}
GET  /v1/videos/{id}            查状态
GET  /v1/videos/{id}/content    下载 mp4
```

请求体（照抄官方 `reproducible-768p-ref2va-request.sh`）：

```json
{
  "task": "ref2va",
  "prompt": "<六段结构化提示词>",
  "conditions": [
    {"type": "image", "uri": "<url 或 data URL>", "role": "reference"}
  ],
  "target": {"short_edge": 768, "aspect_ratio": "9:16", "duration_seconds": 8},
  "seed": 0
}
```

我们的关键帧在本地，所以 `h3_submit.py` 把 PNG 读成 **base64 data URL** 直接
塞进请求体，省掉图床那一步。

**端口怎么连**：Pod 的 30011 不一定对公网开放，最稳的是 SSH 隧道：

```bash
ssh -N -L 30011:127.0.0.1:30011 -p <ssh_port> root@<ip> &
```

⚠️ 服务要 `setsid nohup` 起在后台（理由见 SKILL.md 第 4 节第 ⑤ 条）。

### 4B. diffusers（备选，我们不走）

diffusers 也有 24–32GB 的配方，但它是 `ModularPipeline` 的 Python 接口、
不是 HTTP 服务，`h3_submit.py` 用不上，要另写远端脚本。
**既然 SGLang 自己就能跑 1×4090，没有理由为省显存换框架**——
除非将来发现 SGLang 的某个能力缺失。

```python
pipe = ModularPipeline.from_pretrained("MiniMaxAI/MiniMax-H3", workflow="ref2va")
pipe.load_components(dtype=torch.bfloat16)
pipe.doc   # 打印这个 workflow 到底吃什么、吐什么
```

## 5. 提示词：为什么必须结构化装配

H3 官方系统有三个模块：**H3-Context-IR** → **H3-Base** → **H3-Regenerate-2K**。
中间那个是开源的，另外两个不是。

`H3-Context-IR` 专门把人写的自由输入改写成 H3-Base 认的结构化表示。
README 原话：

> **H3-Context-IR is critical to the quality of the final output**, so we
> strongly recommend incorporating it into your generation pipeline or
> following the "Prompting Guidance" to build your own context-processing system.

**它没有开源**。官方给的替代方案就是照着 Prompting Guidance 自己建一个——
`short-drama-video-gen/scripts/build_h3_prompt.py` 就是我们的 Context-IR。

所以**不要把镜头卡拼成一段散文丢给 H3**，那等于把官方明说"对最终质量至关
重要"的一步删掉。

### 六段格式（ref2va，我们用的）

顺序固定，一段都不能少：

| 段 | 写什么 |
|---|---|
| `subject_definitions` | 定义 `<Subject N>` / `<Picture N>` / `<Video N>` / `<Audio N>` 各指什么，一行一个 |
| `summary` | 一段话概括，开头带方括号任务类型前缀，如 `[keyframe completion + reference generation]` |
| `retention_analysis` | 每个标签**怎么被保留**：`fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference`（音频用 `fully_copy` / `partially_copy` / `reference` / `weak_reference`）。**这一段里不许出现 `(Sx)`** |
| `detailed_description` | 主体。正文格式跟三段版一样，但把引用标签插进去；**风格句写在 `[Shot 1]` 之前**。生成类任务官方建议 **350–500 英文词** |
| `overall_soundscape` | 全片环境音/动作音/非语言人声，1–4 句 |
| `non_diegetic_music` | 只有观众听得到的配乐；没有写 `N/A` |

标签用法要点：

- `<Subject N>` = **可复用的可见内容**（人、场景、服装、道具、风格、动作）。
  一个 subject 可以来自多个素材；一个素材可以提供多个 subject。
- `<Picture N>` = 图**本身**充当某镜的首帧/关键帧/尾帧/构图锚点时才单独立项。
  只是用来定义人物长相/场景/风格的图，**不单独立项**，写进对应 `<Subject N>`
  的定义里。
- 人物说话时写成 `<Subject 2> (S1)`：前者标身份，后者标发声源。

### 几条容易写错的硬规则

- **运镜必须用官方受控词表**：`Push In / Pull Out / Zoom In / Zoom Out /
  Pan / Truck / Tilt / Pedestal / Arc Shot / Tracking Shot / Static Shot /
  Shake / POV / Roll` + 可选的 `with small|large amplitude` +
  `at slow|fast speed`。写成镜头内的自然英文动作，**不是末尾贴标签**。
  镜头不动就写 `holds a static shot`，别留空。
- **台词**：`<d>` 里**只**放语言标签和原文，逐字保留、不翻译不改写；
  说话人身份、动作、语气全写在 `<d>` **外面**。
- **旁白**：必须用固定短语 `says in an off-screen voiceover`，而且紧跟一句
  "画面里那个人的嘴是闭着的"。
- **说话人 ID**：按实际发声顺序给 `(S1)`/`(S2)`，同一个人跨镜保持同一个 ID，
  不发声的人不给 ID。
- **画面内的文字**（招牌、字幕）用英文双引号包住，原文照抄不翻译。
- **`overall_soundscape`** 只写环境音/动作音/非语言人声；
  台词和画内音乐已经在正文里了，**不要重复**。
- **`non_diegetic_music`** 只写乐器/速度/节奏/强弱变化，**不要写抽象情绪词**，
  也不要解释配乐的情绪功能。
- **否定句**：H3 是 guidance 蒸馏、没有负面通道，"不要 X"只会把 X 注入编码器。

## 6. 还没验证的（下次跑的时候顺手做掉）

**本仓库一次都没有真的跑过 H3**，下面全是文档推导，第一次实跑要逐条确认：

- 24–32GB 量化档**到底慢多少**——这决定"便宜卡"这条路划不划算
- diffusers 那条路的远端推理脚本还没写（见 4B）
- `h3_submit.py` 里的状态字符串（`completed`/`succeeded`/`failed`…）是照通用
  约定写的兜底集合，**没对着真实服务确认过**。第一次跑先 `--dry-run`，
  再单条真跑，把服务端实际返回的 status 补进 `DONE_STATES`/`FAIL_STATES`
- H3 会不会有 LTX 那两个毛病：A8「推拉运镜冲过头」、A9「人物自己转向镜头」。
  H3 的运镜是受控词表 + 幅度/速度，**理论上比 LTX 的散文运镜更可控**；
  而且 ref2va 的图是"参考"不是"焊死的首帧"，机制不同。
  **A9 是 LTX 上改提示词拦不住的硬故障，H3 能不能绕开它是换模型最大的潜在收益**
- 中文台词的口型准不准、音色跨镜稳不稳（LTX 那边是 A5「跨镜音色不保证一致」）
- `ref2va` 拿角色三视图当参考，能不能比首帧焊死更好地保人物一致性
