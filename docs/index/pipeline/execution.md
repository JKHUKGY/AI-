# LTX / H3 校验与执行

仅定位文件；实际操作读取对应 skill。路径相对当前宿主的 skills 根目录。
表中关键文件的省略前缀沿用最近的 `scripts/` 或 `references/`。

| 顺序 | Skill 目录 | 输入 → 输出 | 关键文件 |
|---|---|---|---|
| 6 | `short-drama-ltx-export/` | **LTX-2.5 通道**的提交前关卡：校验 `video_jobs.json`（路径/64整除/8k+1/台词语言声明/seed/token 预算/否定句/first_frame_strength/**是否还和镜头卡一致**）+ `ltx_remote_config.json` + `--dry-run` | `scripts/validate_video_jobs.py`, `references/resolution_presets.md` |
| 7 | `short-drama-ltx-generate/` | **LTX-2.5 通道**的执行：真实租显卡（只剩 RunPod，`rent_cheapest` 够用就行最便宜优先）→ `ltx_ssh_submit.py` 每镜跑一次 CLI（实测要 80GB，每镜重装 67GB 权重）→ 下载、验收、**用完关机**。⚠️ **本目录下的 GPU 运维资产是两条视频通道共用的** | `scripts/ltx_ssh_submit.py`, `ltx_batch.py`, **`runpod_ops.py` / `gpu_teardown.py` / `idle_shutdown_watchdog.py`（共用）**, `references/runpod_gpu_ops.md`（共用）, `ltx_pipeline_gotchas.md` |
| 6′ | `minimax-h3-export/` | **MiniMax-H3 通道**的提交前关卡：驱动 `build_h3_prompt.py` 把同一份镜头卡装配成 **ref2va 六段结构化提示词** + `h3_jobs.json`（**装配即校验**）+ `h3_remote_config.json` + `--dry-run` 看真实 HTTP 请求体 | 无自有脚本（装配器在 `short-drama-video-gen/scripts/`） |
| 7′ | `minimax-h3-generate/` | **MiniMax-H3 通道**的执行：租显卡（**门槛低得多，1×RTX 4090 24GB 就够，$0.34/hr**）→ 部署 SGLang Diffusion → 下 Ref2VA 权重 → 起**常驻服务**（权重只装一次）→ SSH 隧道 + `h3_submit.py` 走 HTTP 提交 → 抽帧**+听审**验收（原生立体声）→ 关机 | `scripts/h3_submit.py`（自建 SGLang）, **`h3_cloud_submit.py`（官方云 API，不租卡、能出 2K、没有 seed）**, `references/minimax_h3_ops.md`, **`minimax_cloud_api.md`（官方云 API 规格 + 跟自建那份 jobs 的四处落差）** |
