# 外部资源入口

只读命中的一页；密码、API key、私钥只记录获取位置，不写值。

| 要找什么 | 读取 |
|---|---|
| 正式站网址、登录账号、Azure VM、SSH、部署/开关机 | [正式站](resources/website.md) |
| 本地网站、Codespace 临时网址、端口转发 | [本地副本](resources/local.md) |
| 出图账号、视频 API、RunPod 配置、GPU 关机脚本 | [生成服务账号](resources/accounts.md) |
| 原始剧本 docx、外部 PDF、参考素材 | [原始素材](resources/sources.md) |

## 5. 这份文档过期了怎么办

值会变（IP、区域、账号、平台），所以**先验证再引用**：

- 网站活没活：`curl -sS -o /dev/null -w '%{http_code}\n' -L <网址>/login.html`
- VM 真实状态：`az vm list -d -o table`
- 仓库产出进度：`python3 .claude/skills/index/scripts/snapshot.py`（磁盘现状，不会过期）

发现和实际不符，**当场改这份文档**，别只在回答里口头更正。
