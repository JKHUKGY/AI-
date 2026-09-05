# 断点与结果记录

记录放在测试输出目录下的 `_test/`，不往全局配置或工作区外写入。恢复先读记录，再核验实际文件和用户消息。

## 文件

| 文件 | 用途 |
|---|---|
| `run.json` | 当前阶段、测试范围、产物路径、待确认 gate、批准来源、重试与费用累计 |
| `approvals/<gate_id>.md` | 用户看得到的具体批次方案、版本和变更记录；不是授权来源 |
| `report.md` | 阶段结果、失败原因、真实生成/复用情况、资源收尾证据与最终结论 |

以下为新测试的初始化示例，运行时填实际值；不能把示例状态当已执行证据：

```json
{
  "schema_version": 1,
  "run_id": "replace-with-actual-run-id",
  "project_dir": "replace-with-actual-project-relative-path",
  "source_refs": [],
  "scope": {"episode": "ep01", "shot_ids": [], "video_backend": "ltx"},
  "stage": "prepare",
  "status": "preparing",
  "artifacts": {},
  "pending_gate_id": null,
  "gates": [],
  "units": [],
  "agents": [],
  "resources": [],
  "final_result": null
}
```

`status`：`preparing`、`waiting_user`、`running`、`blocked`、`cleanup_pending`、`finished`。
`final_result`：未结束为 null；结束时为 `passed`、`partial`、`blocked`、`failed`。阶段已复用单独记 `reused`。

## 批次与证据

每个 `gates[]` 项至少记录：`gate_id`、`kind`（G1/G2）、`revision`、`packet_path`、`unit_ids`、`limits`、`status`、`request_message_ref`、`approval_message_ref`、`approval_quote`、`approved_at`。
确认前，`approval_message_ref`、`approval_quote`、`approved_at` 均为 null；**只有真实用户明确批准后才填写**。有消息 ID 用消息 ID，没有则记录会话/时间/原文定位信息，不能编造 ID。无法核验就保留待确认。

`limits` 保存实际批准的张数、轮次或 GPU 小时单价/最长租时/总费用上限，以及允许的重试变更。对已展示的 jobs、卡、提示词审阅表保存相对路径和 SHA-256，恢复时检查是否变化；这是变更检测，不是密码学授权。
允许范围内的重试记录新旧卡/参数及扣减用量；实质变更更新方案版本，并重新取得对应关口确认。

每个 `units[]` 项记录：ID、阶段、依赖、首次及后续真实生成轮次、候选路径、最终选片、Reviewer 结论与证据、失败原因。未通过的 `selected_file` 留空。
每个 `agents[]` 项记录真实宿主 ID、分工、负责的 unit、交付物；四个代理不等于四次工具调用。
每个 `resources[]` 项记录：提供商、本批拥有的实例/卷 ID、价格与费用上限、开始/截止时间、远端写入目录、生成状态、释放命令结果、只读回查时间和状态、残留存储及收费情况。
密钥、令牌和密码只记读取位置，不写明文。

文件有路径不代表检查通过。每阶段在报告中记录实际执行的命令/工具、退出结果及输出文件；未执行标 `not_run`，缺环境标 `blocked`，远端地址未就绪标 `remote_dry_run_pending`。

## 最终报告

1. 本次覆盖的故事、集数、镜号、模型；哪些阶段新执行、复用或未执行。
2. 分镜/卡/装配/生成/独立审查/预览各阶段结果与证据链接。
3. G1/G2 批次及实际用户确认来源；生成张数/次数、到限和依赖阻塞项。
4. 图片真实 subagent 参与数与分工；视频 Reviewer 的原剧本核对、画面与音频审查结果。
5. 视频数量、成本估算/实际可查成本、GPU 停止计费证据、残留存储费用。无法验证的成本或收尾必须明确写未知。
6. 最终结论与下一步。部分失败/未生成/未收尾不得写全流程实测通过；拼接缺镜预览也要明确标为部分预览。
