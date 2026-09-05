# Reviewer 子代理任务模板

每位审查者必须是与 Generator 不同的真实代理。R1负责逐张核对原文和已批准卡片，
R2负责基准身份／道具／空间／光线及场次连续性，单 unit 模式的R3再独立复核拟选图。
每位都实际打开图片；不能把另一代理的描述当成看图。先独立记录观察再对照其他结论。

依据按 unit 类型提供：角色档案、场景说明、关键帧的剧本原文 `script_ref_zh`、
已批准卡片，以及对应角色／机位／场次主帧参考。`scene_master` 按场次节拍、
在场名单、状态和原文核对，再检查它能否给后续镜头提供一致状态基准。

- 角色／场景检查清单：`../../short-drama-image-gen/references/review_checklist.md`。
- 主帧／关键帧清单：`../../short-drama-keyframe-gen/references/keyframe_review_checklist.md`。

```text
你是独立 Reviewer <R1/R2/R3>，本次职责：<单图/连续性/最终复核>。
unit/round：<ID及实际轮次>。
原文：<逐字摘录>。已批准设计：<源卡及版本>。
待审图片、人物参考、机位底板、主帧和相关前后镜头：<真实绝对路径>。
逐张打开待审图及相关参考，给出有画面证据的观察；不调用图像生成，不改源卡。
只写 <独立审查报告路径>，返回：
agent_id、unit_id、round、review_scope、inspected_files；
每张图的 verdict: pass/fail、reason、可执行 fix_instruction；
有卡片时指出 card_field 和建议修改值，不直接改派生 prompt；
proposed_file：该审查者认为可用的图，未通过留空。
三轮到限时另给 best_candidate 及尚存差异，它不等于通过或最终选图。
```

景别、朝向和走位按已确认卡片；剧情按原文，不能把生成 prompt 当唯一判据。
禁止为候选重新解释或降低标准，也不能添加原文和已确认设计没有要求的新细节。
看不清某项时写明“不足以确认”及具体区域，不能凭想象断言其正确或错误。
Reviewers 有分歧时记录证据并交主代理整理，不能由生成者裁定自己通过。
同一张拟选图必须取得所有已分配审查者的 pass，才能进入最终登记。
