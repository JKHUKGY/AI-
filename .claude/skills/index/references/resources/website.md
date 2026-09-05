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
