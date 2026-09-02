# 部署到云服务器（公网上线）

给"几人到十几人的熟人剧本家团队"用的最小可行部署方案。跟 `README.md` 里
"本地/局域网跑"的默认路径不同，这份文档是把同一套代码搬到一台公网云主机
上长期跑，并且保留"一键重新生成图片"（服务器上也要装并登录 Codex CLI）。

## 0. Azure for Students 专属说明

Azure for Students 的全球版账号本身就没有大陆区域可选（大陆是世纪互联
运营的独立版本，学生免费额度用不了），所以"地区要避开防火墙内"这条对
你天然满足，随便选一个离用户近的全球区域就行（比如东南亚/日本东部/
韩国中部，剧本家在国内访问延迟会小一些）。

另外 Azure 给每个公网 IP 免费送一个 `<你起的名字>.<区域>.cloudapp.azure.com`
子域名（"DNS 名称标签"），不用自己花钱买域名就能在第 6 步跑 certbot 申请
真的 HTTPS 证书——建议直接用这个，跳过买域名这一步。

## 1. 创建虚拟机（Azure 门户）

登录 https://portal.azure.com → 搜索"虚拟机" → 创建：

- **订阅**：选你的 Azure for Students 订阅。
- **资源组**：新建一个，比如 `scriptwriter-rg`。
- **区域**：East Asia / Southeast Asia / Japan East 任选一个（延迟低的）。
- **映像**：Ubuntu Server 22.04 LTS。
- **大小**：先选 `Standard_B1s`（1 vCPU/1GB，学生额度里通常最省钱，甚至
  可能落在 12 个月免费额度范围内）。如果后面装 npm/codex 时明显卡（内存
  不够被 OOM kill），再升到 `Standard_B2s`（2 vCPU/4GB）——升级只需要在
  门户里把虚拟机"停止(解除分配)"后改大小，不用重建。
- **身份验证**：选 SSH 公钥，用你本机已有的公钥，或者让门户帮你生成一对
  新的（生成后**立刻下载 .pem 私钥**，只会给你下载这一次）。
- **入站端口规则**：勾选 SSH(22)、HTTP(80)、HTTPS(443)。SSH 建议后面在
  "网络安全组"里把来源限制成你自己的公网 IP，减少被扫描爆破的机会。
- **磁盘**：默认的 30GB 系统盘够用——`git clone` 整个仓库（含历史里的
  视频文件）目前 `.git` 接近 1GB，加上 `output/` 下的视频，够留余量。

创建完成后，进这台虚拟机的资源页 → 左侧"配置"（属于它的"公共 IP 地址"
资源）→ **DNS 名称标签**，填一个全局唯一的名字（比如
`scriptwriter-jia`），保存后你就有了
`scriptwriter-jia.eastasia.cloudapp.azure.com` 这样一个免费域名，第 6 步
直接用它。

> 想用命令行也可以，等价的 `az` 命令：
> ```bash
> az login
> az group create --name scriptwriter-rg --location southeastasia
> az vm create --resource-group scriptwriter-rg --name scriptwriter-vm \
>   --image Ubuntu2204 --size Standard_B1s --admin-username deploy \
>   --generate-ssh-keys --public-ip-sku Standard
> az vm open-port --resource-group scriptwriter-rg --name scriptwriter-vm --port 80 --priority 1010
> az vm open-port --resource-group scriptwriter-rg --name scriptwriter-vm --port 443 --priority 1011
> az network public-ip list --resource-group scriptwriter-rg -o table   # 找到公共 IP 资源名
> az network public-ip update --resource-group scriptwriter-rg \
>   --name <上一步查到的名字> --dns-name scriptwriter-jia
> ```

## 2. 服务器初始化

```bash
ssh -i 你下载的.pem文件 deploy@scriptwriter-jia.eastasia.cloudapp.azure.com

sudo apt update && sudo apt install -y python3 git nginx certbot python3-certbot-nginx ufw

sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

**注意**：Azure 的网络安全组（NSG）和虚拟机里的 `ufw` 是两层独立的防火
墙，创建虚拟机时勾选的入站规则只解决 NSG 这一层，`ufw` 这一层仍然要在
机器里自己开（上面命令已经包含），两层都放行端口才真的能访问。


## 3. 部署代码

```bash
cd ~
git clone <你的仓库地址> AI-
cd AI-/web
```

首次启动前建账号（每个剧本家一个，密码交互输入不回显）：

```bash
python3 server/manage_users.py add <用户名>
```

先手动跑一次确认没问题：

```bash
python3 server/app.py --port 8000 --secure-cookies
# 另开一个终端 curl 一下确认能通，再 Ctrl+C 停掉，转成 systemd 常驻
```

## 4. 装 Codex CLI 并登录（保留"重新生成图片"功能必须做这步）

```bash
sudo apt install -y npm   # 没有 npm 的话
sudo npm install -g @openai/codex
codex login --device-auth
```

会打印一个链接+一次性代码，**在你自己电脑的浏览器里打开**，用有 Plus/
Pro/Team 订阅的 ChatGPT 账号登录授权，跟本机是否有浏览器无关。登录凭证
存在 `~/.codex/`，跟着这个 `deploy` 用户的 home 目录，长期有效不用每次
重新登录（除非官方要求重新认证）。

## 5. 用 systemd 常驻

把 `web/deploy/scriptwriter-web.service` 里的 `User` 和
`WorkingDirectory` 换成你实际的用户名和仓库路径，然后：

```bash
sudo cp web/deploy/scriptwriter-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now scriptwriter-web
sudo systemctl status scriptwriter-web   # 确认是 active (running)
```

之后更新代码：`git pull` 之后 `sudo systemctl restart scriptwriter-web`。

## 6. nginx 反代 + HTTPS

用第 1 步在 Azure 里免费拿到的 `xxx.区域.cloudapp.azure.com` 域名，不用
另外买域名、不用配 DNS（Azure 已经帮你解析好了）：

```bash
sudo cp web/deploy/nginx.conf.example /etc/nginx/sites-available/scriptwriter-web
sudo sed -i 's/your.domain.com/scriptwriter-jia.eastasia.cloudapp.azure.com/' /etc/nginx/sites-available/scriptwriter-web
sudo ln -s /etc/nginx/sites-available/scriptwriter-web /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d scriptwriter-jia.eastasia.cloudapp.azure.com   # 自动申请证书并改写成 https，会问邮箱和是否强制跳转 https，选强制跳转
```

如果暂时不想配这一步，也可以先跳过，把 systemd 里的 `--secure-cookies`
去掉，直接用 `http://scriptwriter-jia.eastasia.cloudapp.azure.com:8000`
访问验证（没有 HTTPS 时 `--secure-cookies` 会导致 cookie 存不进浏览器，
登录不了），但公网裸 HTTP 传密码不安全，正式给剧本家用之前建议还是走完
这一步。

## 7. 验收清单

- [ ] `https://你的域名` 能打开登录页，账号密码能登录
- [ ] 找一张已有图片点"重新生成"，确认服务器上真的在跑 `codex exec`
      （`journalctl -u scriptwriter-web -f` 能看到相关输出），几分钟后
      图片更新
- [ ] 把账号分发给各个剧本家，每人自己的用户名密码（不要共用一个账号，
      改密码撤权限时才不会互相影响）
- [ ] 确认 `output/<项目>/_web_state/review.json` 会随着评论/修改正常
      更新，且这个文件在 git 里（不是被 `.gitignore` 掉的临时文件）

## 已知边界（部署后仍然成立，见 `README.md`）

- 没有"服务端强制踢人下线"，撤销权限只能改密码。
- 登录限流按用户名、5 分钟 8 次，够小团队用，不是防大规模攻击的方案。
- 视频没有一键重新生成，只登记待办。

## 学生额度别花超了

Azure for Students 是一次性 $100 额度，`B1s` 24 小时跑一个月大概几美元、
`B2s` 大概一二十美元，正常不会很快用完，但建议在门户里"成本管理 + 计费"
下面设一个预算提醒（比如花到 $50、$80 各提醒一次邮件），免得额度用尽后
服务被自动停掉都不知道。
