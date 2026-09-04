# 素材冷归档 (scripts/archive.py)

把暂时用不上的短剧素材（png/mp4）打包传到 Google Drive，本地只留清单，
需要时原样取回。剧本、镜头表、jobs.json 这些文本**永远留在仓库里**，不参与归档。

## 一次性设置：授权 Google Drive

> ⚠️ **别用 rclone 内置的共享 client_id。** rclone 自己会警告：
> "rclone's shared Google Drive client_id is being retired and will stop
> working during 2026." 现在已经是 2026 年，随时可能失效。
> 自己建一个 client_id 只要十分钟，一次做完长期有效。

### 第一步：建自己的 Google OAuth client_id

1. 开 https://console.cloud.google.com/ → 新建一个项目（名字随便，比如 `rclone-archive`）
2. 左侧 **APIs & Services → Library** → 搜 `Google Drive API` → **Enable**
3. **APIs & Services → OAuth consent screen**
   - User Type 选 **External** → 填个 App name、选自己的邮箱 → 保存
   - **Audience** 页把自己的 Google 账号加进 **Test users**
     （不加的话授权会被拒；测试模式下 token 有效期较短，
     想长期免打扰就把应用状态发布成 Production）
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type 选 **Desktop app** → Create
   - 记下 **Client ID** 和 **Client Secret**

### 第二步：在本机（有浏览器的那台）拿 token

本机装一个同版本 rclone（https://rclone.org/downloads/），然后：

```bash
rclone authorize "drive" \
  --drive-client-id "你的CLIENT_ID" \
  --drive-client-secret "你的SECRET" \
  --drive-scope drive.file
```

`--drive-scope drive.file` 是关键 —— 详见下面「授权范围」一节。

浏览器会弹出授权页，同意后终端会打印一段
`{"access_token":...,"refresh_token":...}`，**整段**复制下来。

### 第三步：在 Codespace 里写进配置

直接写配置文件最稳 —— 不联网、不弹问题、结果确定
（`rclone config create` 走到 team drive 探测那步会卡住）：

```bash
mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf <<'EOF'
[gdrive]
type = drive
client_id = 你的CLIENT_ID
client_secret = 你的SECRET
scope = drive.file
team_drive =
token = 第二步复制的整段JSON
EOF
```

注意 `token =` 后面要放**完整的一行 JSON**（`{"access_token":...}`，不要换行）。

验证：

```bash
rclone listremotes          # 应该看到 gdrive:
rclone about gdrive:        # 看到 Drive 容量就通了
```

### 备选：在 Codespace 里直接走浏览器流程

Codespace 能把端口转发到你本机（转发域 `app.github.dev`），所以
`rclone config` 的浏览器流程也可能直接可用 —— 交互式跑一遍，
在 "Use web browser to automatically authenticate?" 时答 **Y**，
VS Code 会提示转发 `53682` 端口，点开就能授权。
注意 scope 那一问要选 **`drive.file`**（不是 `drive`）。不通就退回上面三步。

凭证存在 `~/.config/rclone/rclone.conf`，**不在仓库里**（不要提交），
换机器或重建 Codespace 都要重做一次。

## 授权范围：给 drive.file，不要给 drive

脚本对 Drive 只做三种操作（`grep rclone_bin scripts/archive.py` 可自查）：

| 操作 | 用途 |
|---|---|
| `rclone copyto` | 上传归档包 / 下载归档包 |
| `rclone lsjson` | 读自己那个包的大小，用来校验上传完整 |
| `rclone listremotes` | 纯本地，检查有没有配 remote |

**它从不删除 Drive 上任何东西**，也从不遍历你的其他文件。所以
`scope = drive.file`（只能访问 rclone 自己创建的文件）就完全够用，
而 `scope = drive` 会把整个 Drive 的读写删权交出去 —— 没必要。

为什么值得较真：token 明文存在 `~/.config/rclone/rclone.conf`。
万一 Codespace 被人摸到、或者你不小心把配置提交进 git，
`drive.file` 的泄露后果只是这些归档包，`drive` 则是你的整个云盘。

### drive.file 的一个代价

Google 的说法是 "File authorization is revoked when the user deauthorizes
the app"。也就是说如果你去 Google 账号设置里撤销了这个应用的授权，
之后重新授权，**rclone 会看不见之前上传的那些包**。

数据不会丢 —— 这些包在 Drive 网页里照常可见（`drive.appfolder` 就不行，
所以别用那个），你可以手动下载，或者重新走一遍 stash。
但 `archive.py restore` 会失效，得手动 `rclone copy` 救回来。

所以：**别去撤销这个 app 的授权**。真撤了，去 Drive 网页里找
`AI-短剧归档/` 文件夹手动下载 `.tar.zst`，然后按 `.archived.json` 里的
清单自己解包校验。

> ✅ `drive.file` 已在真实 Drive 上端到端实测通过（2026-09-03）：
> stash 上传 → verify → restore 下载 → 逐字节 sha256 比对一致。
> 最小权限完全够用，不需要 `drive`。
> （若哪天真要换 scope，必须重新拿一次 token —— 光改配置文件那一行没用，
> scope 是烧在 token 里的。）

## 日常用法

```bash
# 看谁占地方、哪些已经归档
scripts/archive.py status

# 归档除 v2 以外的全部项目（先 dry-run 看看它要干什么）
scripts/archive.py stash --all-except 出狱后我成为了非洲矿王_v2 --dry-run
scripts/archive.py stash --all-except 出狱后我成为了非洲矿王_v2

# 也可以点名归档
scripts/archive.py stash 千金归位 暗局

# 要用了，取回来
scripts/archive.py restore 千金归位

# 只取回关键帧，不下那 50M 视频
scripts/archive.py restore 千金归位 -v keyframes

# 列出云端有什么 / 确认云端文件还健康
scripts/archive.py list
scripts/archive.py verify 千金归位

# 不走云端，导出 tar.zst 到移动硬盘
scripts/archive.py export 千金归位 -o /mnt/外置盘
```

## 机制

- **分卷**：按项目下的顶层子目录切包（`assets` / `keyframes` / `videos` 各一个
  `tar.zst`），所以能只取回需要的那部分。
- **清单**：`output/<项目>/.archived.json` 记录每个文件的路径、大小、sha256，
  以及压缩包本身的 sha256。**这个文件必须提交进 git** —— 取回完全靠它。
- **安全顺序**：打包 → 上传 → 回读远端确认大小一致 → 才写清单 → 才删本地。
  中间任何一步失败或被 Ctrl-C，本地素材都还在原处。
- **取回校验**：先验压缩包 sha256，解包后再逐个文件验 sha256。
  对不上就报错退出，不会给你半个损坏的项目。
- **压缩率**：png/mp4 本身已是压缩格式，zstd 再压收益为零（实测 100%），
  所以压缩级别设成 1 —— 打 tar 只是为了把上百个文件合成一个上传对象。

## 注意

**归档不会缩小 `.git`。** `.git/objects` 约 1.6G，来自*历史提交*里的旧素材
（比如 `videos/ep01/ep01_full_cut.mp4` 79MB、`ep01_full_cut_v1.mp4` 76MB），
删工作区文件对它没有任何影响。要回收那 1.6G 得用 `git filter-repo` 重写历史
并强推 origin，是另一件事、另一种风险，目前没做。

**stash 之后 `git status` 会出现大量 deleted。** `output/` 下的素材是
git 已跟踪文件（318 个全部已跟踪、且已推到 origin），所以归档删掉本地副本后
git 会把它们报成删除。两个选择：

- **提交这些删除**：`git status` 干净，素材以 Drive 为准。推荐，
  但同时要加 `.gitignore` 规则，否则下次生成的素材又会被提交进历史、
  让 `.git` 继续涨。
- **不提交**：`git status` 一直是 318 条 deleted 的噪音。

⚠️ **别在 `output/` 下跑 `git checkout -- .` 或 `git restore`** ——
那会把 861M 素材从 git 历史里恢复出来，空间白省。
要取回素材请用 `archive.py restore`。

好消息是：这些文件在 git 历史里、且已推到 origin 的 `try1`/`try2`/`try3`/`try4`
分支（`main` 上没有），所以你实际上有**两份**备份：Drive + GitHub 分支历史。
真要救，`git cat-file -e origin/try3:<路径>` 能确认某个文件在哪个分支上。
坏消息是这也意味着 `.git` 那 1.6G 一分都没省下来。

**唯一不能丢的东西是 `.archived.json`。** 清单没了就只剩一堆 Drive 上的
`项目__分卷.tar.zst`，虽然还能手动 `rclone copy` 下来解包，但校验信息就没了。
记得提交进 git。
