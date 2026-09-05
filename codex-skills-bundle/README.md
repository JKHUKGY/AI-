# Codex skills 转换包

包含全部 23 个 skill（17 个插件 skill 和 6 个维护 skill）。

每个目录的 SKILL.md 是新增 Codex 入口；SOURCE-SKILL.md 是逐字节保留的原始入口，所有附件也完整保留。入口单独说明工具、参数、插件变量和跨 skill 调用的适配关系。原始 description 仅在入口中将尖括号替换为圆括号以通过格式校验；原文仍完整保留。7 个原本禁止自动调用的 skill 保留该策略。

使用：将 skills 下的全部目录复制到目标项目的 .agents/skills/，或个人 ~/.codex/skills/；重新打开 Codex 会话后，通过 $skill-name 调用，例如 $codex-docs。为保证跨 skill 引用完整，请整组复制。此包尚未安装到个人全局目录。

conversion-manifest.json 记录源提交、全部原始文件的 SHA-256 和对应输出路径。全部入口通过 skill-creator 的 quick_validate.py，全部原始文件已进行字节一致性校验。未执行这些 skill 的实际业务流程；联网文档查询仍依赖网络，维护类 skill 仍需原始仓库和相应工具。Claude allowed-tools 无法作为 Codex 原生工具白名单强制执行。

本次为本地确定性转换，未调用模型 API，也未使用或保存 API key。

格式参考：https://developers.openai.com/codex/skills/
