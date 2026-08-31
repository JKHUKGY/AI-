# 出图环境准备（Codex CLI / ChatGPT 登录）

## 1. 登录（不需要 API key，不需要开通计费）

- 确认是否已安装：`codex --version`；没装就 `npm install -g @openai/codex`。
- 登录状态：`codex login status`。
- 没登录就跑设备码登录（不需要本地浏览器回调，适合远程/容器环境）：

  ```bash
  codex login --device-auth
  ```

  会打印一个链接和一次性代码（15 分钟内有效），用户在自己的浏览器里打开链接、
  输入代码、用 ChatGPT 账号登录（需要 Plus/Pro/Team 等已订阅账号，具体额度以
  账号方案为准）。这一步必须由用户在真实浏览器里完成，Claude 没法代劳，只能
  提示用户去做。
- 登录凭证缓存在 `~/.codex/`，跟这个环境共享同一个用户目录的会话都能直接用，
  不需要每次重新登录。

**为什么不用 Gemini API / OpenAI 开发者 API**：实测过 Gemini CLI 用 Google
账号 OAuth 登录后，图片生成模型的免费额度是 0（`limit: 0`），必须走 Google
Cloud 计费账号的 API key 才能出图；OpenAI 的开发者 API 同理，跟 ChatGPT 网页
会员是两套独立计费体系。而 Codex CLI 的 `image_gen` 内置工具，用 ChatGPT 登录
就能直接生成图片，不需要额外开通任何计费——这是当前唯一验证成功的免费出图路
径，实测跑通过（生成并保存了一张真实 PNG 图片）。

## 2. 出图脚本怎么工作

`scripts/generate_images.py` 对每个 job 调用一次：

```bash
codex exec --skip-git-repo-check --sandbox workspace-write -C <job目录> \
  "<prompt>\n\n请生成这张图片，并把最终图片文件保存到这个精确的绝对路径：<目标路径>"
```

- `--sandbox workspace-write` 允许 codex 在指定目录里写文件（生成图片本身走
  的是内置工具，落地到 codex 自己的缓存目录后再由它自己执行 `cp` 到目标路径，
  所以必须给它写权限，否则复制这一步会失败，图片虽然生成了但保存不到我们要
  的位置）。
- `ref_images`（jobs.json 里的参考图路径）通过 `codex exec -i <file>` 传入，
  作为"图生图"的参考输入，用来提升同一角色/场景跨镜头的一致性——原理和之前
  Gemini 方案里传参考图是一个目的，只是接口形式换成了 codex 的 `-i` 附件参数。
- 脚本会话不复用：每张图是独立的一次 `codex exec` 调用（无记忆），所以每次都
  把完整提示词（画风锚点+角色描述等）传全，不要依赖"上一张记得的设定"。

## 3. 额度与稳定性提醒

- ChatGPT 账号的使用额度目前没有对外公开的精确图片生成配额文档，出图速度和
  是否触发限流以实际运行情况为准。脚本如果连续多个 job 都失败（`codex exec`
  非零退出或目标文件迟迟不出现），先看 `codex` 的报错原文（脚本已经会打印到
  stderr），大概率是限流或者账号未登录，不要无脑加大重试次数硬跑，跟用户确认
  情况。
- 模型名称/工具行为由 OpenAI 一侧决定，如果生成效果或速度有明显变化，先联网
  查一下 `codex` 当前版本的发行说明，不要凭旧记忆假设行为不变。
- 每次成功生成一张图都算一次调用，同样要延续"S/A/B/C 优先级"的成本意识——
  优先保证人物/场景资产清单里的图先出全、出好。
