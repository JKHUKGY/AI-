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

Codespace 停掉这个地址就失效，**不要拿它当给剧本家的长期地址**，长期地址见 [正式站](website.md) 的 Azure 站。
