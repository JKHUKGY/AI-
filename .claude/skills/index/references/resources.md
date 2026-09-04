# 资源清单：网址、账号、机器、外部资料

`INDEX.md` 管"仓库里的文件在哪"，这份文档管"仓库外面的东西在哪"——线上网站、
云主机、要登录的账号、租显卡的平台、不在 git 里的原始素材。找不到某个"网址/
key/机器"时读这份，别去仓库里 grep（这些东西按设计就不在 git 里）。

> 凡是密码、API key、私钥，本文档只写**在哪里拿**，不写值。

## 1. 剧本家协作网站（正式站，公网）

| 项 | 值 |
|---|---|
| 网址 | **https://scriptwriter-jia.northcentralus.cloudapp.azure.com** |
| 托管 | Azure VM `scriptwriter-vm`，资源组 `SCRIPTWRITER-RG`，区域 North Central US |
| 公网 IP | 20.88.34.230（域名是 Azure 免费送的 DNS 名称标签，不用自己买域名） |
| 订阅 | Azure for Students（`az account show` 可确认；一次性额度，VM 一直开机会持续扣） |
| 规格 | Standard_B2als_v2，Ubuntu Server |
| SSH | `ssh deploy@scriptwriter-jia.northcentralus.cloudapp.azure.com`（私钥在本机 `~/.ssh/`） |
| 进程 | systemd 服务 `scriptwriter-web`（`sudo systemctl status/restart scriptwriter-web`，日志 `journalctl -u scriptwriter-web -f`） |
| 前置 | nginx 反代 + certbot 证书，HTTP 自动跳 HTTPS |
| 登录账号 | `junzhenj`（密码只有哈希，存在**服务器上**的 `web/server/data/users.json`，这个目录已 gitignore，不在仓库里） |
| 改密/加人 | 在服务器上 `python3 web/server/manage_users.py passwd <用户名>` / `add <用户名>` |
| 更新代码 | 服务器上 `git pull` 后 `sudo systemctl restart scriptwriter-web` |

常用运维命令（本机装了 `az`，已登录）：

```bash
az vm list -d -o table                                   # 看 VM 开没开、IP 多少
az vm start|deallocate -g SCRIPTWRITER-RG -n scriptwriter-vm   # 开机 / 停机省额度
```

**注意**：`deallocate` 停机会让网站不可访问，但保留磁盘和域名，重新 `start`
即可恢复；不用的时候停掉能省学生额度。部署步骤的完整版见 `web/DEPLOY.md`。

## 2. 协作网站（本地/Codespace 副本）

同一套代码在开发机上跑起来的临时副本，跟正式站**数据不互通**（各自读各自机器上的
`output/`），只用来自测：

```bash
python3 web/server/app.py --port 8000      # 本机 http://localhost:8000
```

在 GitHub Codespace 里跑时，公网访问要靠端口转发（域名形如
`https://<codespace 名>-8000.app.github.dev`）：

```bash
gh codespace ports -c "$CODESPACE_NAME"                        # 看当前转发和可见性
gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" # 设为公开（用完记得改回 private）
```

Codespace 停掉这个地址就失效，**不要拿它当给剧本家的长期地址**，长期地址用第 1 节的 Azure 站。

## 3. 出图 / 出视频要用的外部账号

| 用途 | 怎么接入 | 在哪配 |
|---|---|---|
| 人物图/场景图/关键帧图 | Codex CLI（ChatGPT 账号登录，无需 API key、不额外计费） | 本机 `codex login --device-auth`，登录态在本机 `~/.codex/`；服务器上要单独登录一次，否则网站的"重新生成"按钮不可用 |
| 图生视频（LTX-2.5 / MiniMax-H3） | 租显卡自建，**渠道只剩 RunPod**（AutoDL 和 vast.ai 2026-09-04 已删除：销毁实例会连权重一起删）。用哪个模型看 config 里的 `model` 字段 | 各剧的 `output/<剧名>/videos/ep0X/ltx_remote_config.json`（连接信息 + `model` + `platform`/`instance_id`/`network_volume_id`）；平台 key 在 `.claude/skills/short-drama-ltx-generate/runpod_config.json`（**已 gitignore，仓库里没有**） |
| 早期 Gemini 出图（已废弃） | 曾用 `GEMINI_API_KEY`，现在整条出图链走 Codex CLI | 历史遗留，`.env.example` 已删 |

显卡**用完必须关**：`.claude/skills/short-drama-ltx-generate/scripts/gpu_teardown.py`
一条命令关实例并轮询确认停止计费；批量任务用 `ltx_ssh_submit.py --auto-stop`。

## 4. 不在 git 里 / 非产出物的原始素材

| 路径 | 是什么 |
|---|---|
| `《出狱后我成为了非洲矿王》一卡.docx` | 该剧原始剧本一卡（覆盖到第 10 集"明牌决裂"），分镜的唯一事实来源 |
| `列车重逢/` | 另一部外来剧本（正式剧本 + 分镜版 docx + 两张参考图），尚未进流水线 |
| `短剧流水线.pdf` | 外部参考资料 |
| `研究.md` | 方法论长文：剧本→分镜→关键帧→图生视频，提示词到底怎么写（skill 里的规则大多出自这里，改规则前先读它） |
| `需求.md` | 原始需求 + 按日期追加的"AI 已做"工作日志（找历史决策/上次做到哪，看这份） |

## 5. 这份文档过期了怎么办

值会变（IP、区域、账号、平台），所以**先验证再引用**：

- 网站活没活：`curl -sS -o /dev/null -w '%{http_code}\n' -L <网址>/login.html`
- VM 真实状态：`az vm list -d -o table`
- 仓库产出进度：`python3 .claude/skills/index/scripts/snapshot.py`（磁盘现状，不会过期）

发现和实际不符，**当场改这份文档**，别只在回答里口头更正。
