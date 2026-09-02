# 租显卡跑 LTX-2.5：AutoDL 渠道（2026-09 实测）

这是 vast.ai 之外的第二条 GPU 租赁渠道。两条渠道**互相独立，不要混用同一份
`ltx_remote_config.json`**——`ltx_ssh_submit.py` 本身平台无关（只认 SSH 连接
信息），差异全部在"怎么把显卡租起来/关掉"这一层，也就是本文档 vs
`gpu_rental_ops.md` 的区别。

## 什么时候选 AutoDL，什么时候选 vast.ai

**每次新租卡前，两边都查一次实际价格再决定，不要凭印象选**（AutoDL 无官方
listing API，只能创建后从 `snapshot` 里读到真实 `payg_price`；vast.ai 用
`vastai search offers` 能先看价格再决定，两边流程不对称，AutoDL 这边只能
"先创建再看价"，如果价格不理想要接受释放掉重建的成本）。已知参考点：

- AutoDL `4090D`（24GB，本仓库 CPU 用途实测过）：约 ¥1.88/小时。
- AutoDL 大显存卡（`h800` 80GB / `pro6000-p` 96GB）：官方文档没有公开价目表
  API，实测前先用 `autodl_ops.py create` 建一个再 `snapshot` 查真实价格，
  不满意可以 `power_off` + `release` 重来（记得先确认没有产生不可控费用）。
- vast.ai 的 96GB 卡实测价格见 `gpu_rental_ops.md`（该文档没写死具体数字，
  用 `vastai search offers` 现查）。

选卡优先级：先满足 0 条的显存门槛，再比价，其余因素（地域延迟、下载模型的
带宽）分量较小。

## 0. 选卡之前先确认显存够不够（跟 vast.ai 渠道要求一致）

LTX-2.5 权重合计约 66GiB：

- **显存 ≥ 80GB**：AutoDL 目前找到的选项是 `h800`（H800-80G）和
  `pro6000-p`（PRO6000-96G），可以完整精度跑。
- **显存 32-48GB**（`v-48g` 4090-48G / `v-48g-350w` 3090-48G /
  `v-32g-p` 4080(S)-32G）：需要 `--quantization fp8-cast --offload
  cpu/disk`，不保证能塞下，跟 vast.ai 那边一样不要轻信"应该够"，创建后
  务必用 `snapshot` 确认真实显存型号。
- **不要用 `4090D`（24GB）跑生成**——这是本仓库目前唯一实测过的 AutoDL
  规格，但只够跑 CPU 编排/ffmpeg 这类不需要 GPU 的任务，装不下 LTX-2.5。
- 磁盘：创建时 `expand_system_disk_by_gb` 至少给够 150GB 量级空间（模型
  权重 66GB + 系统/依赖），实测创建时系统盘默认 30GB 左右，肯定不够，
  必须显式传扩容参数。

## 1. 账号前置条件

- **部分 GPU 规格需要实名认证**才能创建，遇到 `TORealName` 错误提示用户去
  控制台做实名认证，做完立刻能用，不是账号问题、不用等审核。
- **同一账号短时间内不一定所有规格都有库存**，遇到
  `当前算力规格暂无库存` 是正常现象，换个规格或稍后重试，不代表账号或
  API key 有问题。
- API Token：控制台 → 账号 → 设置 → 开发者Token，放 `autodl_config.json`
  的 `api_token` 字段（该文件已在 `.gitignore`，不会被提交）。

## 2. 创建 + 开机（GPU/有卡模式）

跟 vast.ai 不同，AutoDL **创建实例默认不会自动开始按 GPU 价格计费到"运行"
状态**——`create` 成功后实例会经历 `creating` → `starting` → `running`
（首次创建，镜像下载会占用这段时间，之后可能会保持 running）。之后如果被
`power_off` 过，下次要用必须显式 `power_on`（`payload:"gpu"`，无卡模式开机
API 不支持，见下面第 4 条）。

```bash
# 创建
python3 .claude/skills/short-drama-ltx-generate/scripts/autodl_ops.py create \
  --gpu-spec pro6000-p --image base-image-mbr2n4urrc \
  --cuda-v-from 113 --region beijingDC2 --name ltx-gpu --disk-gb 150

# 轮询状态直到 running（后台轮询，别前台傻等，跟 vast.ai 渠道要求一致）
python3 .claude/skills/short-drama-ltx-generate/scripts/autodl_ops.py status --instance-uuid <uuid>

# 拿 SSH 信息 + 实际价格
python3 .claude/skills/short-drama-ltx-generate/scripts/autodl_ops.py snapshot --instance-uuid <uuid>
```

- 镜像 UUID 从 AutoDL API 文档附录的"公共基础镜像"表里选（本仓库暂时只
  验证过几个 Miniconda/CUDA devel 镜像，见下面第 3 条），没有专门给
  LTX-2.5 预装好的镜像，跟 vast.ai 渠道一样要走一遍环境搭建（clone
  LTX-2 仓库、装 uv、下模型权重），步骤跟 `SKILL.md` 第 2 步一致，跟平台
  无关。
- `cuda_v_from` 要和选的镜像匹配（例如镜像是 cuda11.3 就填 113），不确定
  就选一个不低于 LTX-2 依赖要求的镜像+对应版本号，第一次用先跑
  `python -m ltx_pipelines.distilled --help` 按 `SKILL.md` 第 3 步核实。

## 3. 已验证可用的字段值（截至 2026-09）

- GPU 规格：`4090D`（已验证能创建，24GB，不够跑生成，仅供 CPU 编排用）。
  **`pro6000-p`（RTX PRO 6000 96GB）已于 2026-09 实测创建成功**，`snapshot`
  查到真实价格 `payg_price` 约 ¥5.98/小时（折扣价，`origin_price_yuan_per_
  hour` 约¥7.97/小时），北京B区（`beijingDC2`/`bj-B1`），比同显存量级的
  vast.ai（约$1.4167/hr）便宜不少。`h800`/`v-48g`/`v-48g-350w`/`v-32g-p`/
  `5090-p` 这几个规格ID存在于 API 文档附录但本仓库还没实际创建过，第一次
  用之前按第 2 条跑一遍 `create`，创建失败（库存/实名认证）就换下一个，
  不要假设某个特定规格一定有货。
- 镜像：`base-image-qkkhitpik5`（cuda10.2-cudnn7-ubuntu18.04-py38，装了
  miniconda，没有 ffmpeg，需要自己 `apt-get install ffmpeg`）已验证可用于
  纯 CPU 编排场景；跑 LTX-2.5 生成建议换一个 CUDA 版本更新的镜像（比如
  `base-image-mbr2n4urrc`，cuda11.6），具体以 LTX-2 仓库 README 的 CUDA
  版本要求为准，第一次用先核实。
- 地域：`beijingDC2`（北京区）已验证可创建成功。

## 4. 无卡模式（省钱模式）的 API 限制——不要在生成阶段依赖它

AutoDL 官方文档明确写了：`power_on` 的 `payload` 参数只支持
`"gpu"`，**"暂不支持API以无卡模式开机"**。这意味着：

- 生成任务本身必须用有卡（GPU）模式，这条没有绕过的办法，符合预期
  （反正生成也需要真 GPU 算力）。
- 如果这台 AutoDL 实例平时还兼职跑 CPU 编排任务（省钱模式 ¥0.1/小时），
  切换到无卡模式**必须用户去网页控制台手动点**，Claude 没法自动化这一步，
  见 `autodl_cpu_ops.md`。
- 因此**关机（`power_off`）和开机（`power_on`，GPU）都能全自动化**，
  真正卡自动化的只有"切到无卡模式"这一个动作，不影响生成任务本身的自动化
  程度。

## 5. 成本管理

跟 `gpu_rental_ops.md` 第 4 条要求一致：

- 实例一确认 `running` 就要启动 `idle_shutdown_watchdog.py`
  （传 `--platform autodl --autodl-config <路径>`，见脚本内 `--help`），
  不是可选步骤。
- **`--ssh-host` 必须带 `root@` 前缀**（2026-09 实测踩坑，代价是两次误关
  正在下载/正常运行的实例）：脚本内部直接把 `--ssh-host` 的值拼进
  `ssh ... <ssh_host> <remote_cmd>` 命令，如果漏填 `root@`（比如只传
  `connect.bjb1.seetacloud.com`），SSH 会用本地当前用户名去连，认证必定
  失败，`check_activity()` 把"连不上"当成"无活动"处理——**结果是看门狗会
  在闲置阈值到了之后，不管远程实际是不是正在跑 `hf download`/`uv sync`/
  生成任务，一律判定为空闲并关机**，且这个 bug 不会报错、看门狗日志只会
  持续打印"无活动"，很容易被误以为是"远程真的没在干活"。**每次启动看门狗
  后，先等一个 `--check-interval` 周期，检查日志有没有出现"检测到活动，
  重置计时"这行（而不是清一色的"无活动"），确认 SSH 参数没写错再放心
  让它在后台跑**，不要假设参数传对了。
- **国内数据中心（比如 AutoDL 北京区）访问 `huggingface.co` 本身会网络
  不通**（`ConnectError: Network is unreachable`/超时），下载 LTX-2.5
  权重前必须设置 `export HF_ENDPOINT=https://hf-mirror.com`（`hf auth
  login`、`hf download` 都要带这个环境变量），用这个镜像站可以正常登录
  和下载 gated repo（token 权限校验能通过）。这条只在国内机房渠道
  （AutoDL）遇到过，vast.ai（海外机房）不需要。
- **`hf download` 支持断点续传**：如果下载中途因为看门狗误关机、网络
  波动等原因中断，直接用同一条 `hf download` 命令重新跑一次就行，已经
  下载完的文件会跳过，没下完的文件会从 `.cache/huggingface/download/`
  下的 `.incomplete` 缓存续传，不需要删掉重下。
- **实例的关机(`power_off`)和释放(`release`)是两回事，复用实例能省掉
  重复下载 66GB 模型的时间**：`power_off` 只停止计费，硬盘数据（已装好的
  环境、已下载的模型权重）完整保留；只有 `release` 才会删除数据、不可逆。
  跑完一批生成任务后，只要接下来还会用到 LTX-2.5（比如下一集），就应该
  只调用 `power_off`，把这台实例的 `uuid`/`ltx_remote_config.json` 记下来
  留着复用，下次直接 `power_on` 就能用，不用重新走一遍环境搭建+66GB下载；
  只有确认整个项目都不会再用 LTX-2.5 了才考虑 `release`。
- 批量提交任务前粗略心算一下预计时长和费用，`snapshot` 里能拿到真实
  `payg_price`（单位是"厘"，除以1000才是元/小时），报给用户看的时候换算
  成元。
- 跑完主动确认是否要 `power_off`，不要假设看门狗一定会按预期触发。
- `release`（释放）是不可逆操作，会连数据一起删掉，只有用户明确说"不再
  需要这台实例了"才调用，跑完一批任务只需要 `power_off`，不要顺手
  `release`。
