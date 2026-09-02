# AutoDL CPU（无卡模式）接入记录

用途：跑短剧生成流程里不需要 GPU 的部分（Codex CLI 调用外部 API、ffmpeg 处理、git 操作等），
跟 `gpu_rental_ops.md` 里 vast.ai 租 GPU 跑 LTX-2.5 是两条独立的算力通道，不要混用。

## 关键结论（踩坑记录）

1. **AutoDL 没有独立的纯 CPU 实例产品**。所谓"CPU"是已创建实例的「无卡模式」开机方式
   （0.5核/2GB内存/不挂GPU，统一 ¥0.1/小时），必须先按 GPU 规格创建一个实例，才能切换到无卡模式开机。
2. **无卡模式开机只能在网页控制台手动点，开放平台 API 不支持。**
   `power_on` 接口的 `payload` 参数官方文档原话："gpu：有卡开机, 暂不支持API以无卡模式开机"。
   实测给 `payload` 传各种猜测值（cpu/no_gpu/无卡/economy…）全部返回 `不支持的启动模式`，
   只有 `"gpu"` 是合法值。**所以自动化流程里，只有创建/查状态/查连接信息/关机能走 API，
   开机（无卡模式）必须人工去 https://www.autodl.com 控制台点。**
3. 创建实例部分规格要求实名认证（`4090D`、`v-32g-p` 等提示 `TORealName`），
   部分规格常年无库存（`v-48g-350w`、`v-48g` 试的时候都是 `暂无库存`）。
   实测在北京区（`beijingDC2`）能创建成功的规格：`4090D`。
4. API Token 获取：登录 autodl.com → 控制台 → 账号 → 设置 → 开发者Token，
   放 `Authorization` header 里，不带 `Bearer` 前缀。
5. 镜像选的是 `base-image-qkkhitpik5`（cuda10.2-cudnn7-ubuntu18.04-py38），
   自带 miniconda（`/root/miniconda3/bin/python3`），**没有 ffmpeg，需要自己
   `apt-get update && apt-get install -y ffmpeg`**（首次装约几分钟）。
6. 连接信息在 `snapshot` 接口里：`proxy_host`/`ssh_port`/`root_password`，
   用户名固定 `root`。无卡模式下 SSH 信息是否变化未验证过，如果连不上先重新查一次 snapshot。

## 本地文件

- `autodl_config.json`（同目录，已加入 `.gitignore`，不会被提交）：存 `api_token`、
  `instance_uuid`、`ssh_host`、`ssh_port`、`root_password`。
- `scripts/autodl_ops.py`：`status` / `snapshot` / `power_off` 三个子命令，封装了上面这些 API 调用。

## 标准使用流程

1. 需要跑任务前，人工去控制台把实例切到「无卡模式」开机（实例已经建好，不用重新建）。
2. `python3 scripts/autodl_ops.py snapshot` 拿到最新 SSH 信息（host/port/密码可能变，别用旧的）。
3. `sshpass -p <password> ssh -p <port> root@<host>` 连上去跑任务。
4. 跑完 `python3 scripts/autodl_ops.py power_off` 关机停止计费（无卡模式关机同样调这个接口）。
5. 忘记关机会一直按 ¥0.1/小时（无卡）或对应 GPU 单价（有卡）计费，跟 vast.ai 那边一样建议养成
   跑完立刻关机的习惯；这里数据集/环境在关机期间不受影响，下次开机（无论有卡无卡）都还在。
