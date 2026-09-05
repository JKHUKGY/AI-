# 当前执行断点（2026-09-05）

原任务继续：第1集6主帧、38关键帧，至少4个真实subagent/已批准批次，最多3子代理同时运行。用户取消项目外工具临时目录限制，自动执行；平台approval_policy=never，无sandbox_permissions。当前AGENTS已反映授权。

## 已有产物

- 主帧28候选、3已选（机场a1/a2、客房r2），监狱p2/p3追加各1次局部修正仍失败、别墅第三轮3张仍失败；均到限。依赖17镜未生成。
- 21个独立关键帧均已生成首轮，累计38张候选（17/18/20共三轮、19到第二轮）；仅19_02通过两份审查已选。17/18/20已到限，不自动第四轮。
- 01/02/03/09、21–25、35–38首轮未通过；14/15/16/34首轮审查已齐，均总体fail（16单图pass但连戏fail）。
- 一次会话恢复丢失原子代理，38的旧调用无产物；resume_generate_38已补齐首轮1张，并由新两名独立reviewer补齐35–38审查，全部fail。技术中断不清零轮次。

## 装配与登记

- 当前主源卡：keyframes/ep01/keyframe_cards.json。
- 正常装配用机器文件/build_keyframe_jobs.py；它导入原skill，未改原skill文件。显式支持reference_strategy=plate_plus_master、framing.subject_measurement=full_body（头到鞋底）或cropped（primary_subject及headroom_frac）。原数值“头顶到画底68%”与头顶留白5%矛盾，已用源字段澄清，未到限近景95%保留区间WARN说明。
- `tmp/merge_v3_keyframe_reviews.py`读取所有独立review_keyframes_*.json及_shots侧录，至少两名且全部通过才selected；候选数未达到该轮规定数量不能提前capped。保留全部历史agent与轮次。
- 每次合并后运行机器文件/刷新阅读入口.py，将选图/失败/待审分开，并重建给人看/阅读首页.html、关键帧登记。
- 当前机器队列：机器文件/多代理续做/keyframe_units_queue.json及keyframe_batch_schedule.json。部分状态需随派发实时更新。

## 下一步已准备

独立子代理plan_same_unit_crops实际查看09/21/23/36/37/38，认为主体身份场景正确，纯裁切不能同时保留小过肩，给出同候选local_reframe计划及准确归一化方框，文件same_unit_crop_plans.json。所有编辑必须由imagegen工具执行，不能Python裁切图片。

机器文件/build_same_unit_edit_jobs.py只校验并写JSON，不编辑图片；从源卡+结构化修改计划机械装配，目标必须是同一镜自己的候选，避免跨镜链式播种。

第二轮正在执行，每镜2张（候选01/02）：
- edits_round2_a.json：21、23，给Generator A。
- edits_round2_b.json：36、37，给Generator B。
- edits_round2_c.json：38、09，稍后与其他两项组合或分批。

每组最多4活跃unit；默认两名Generator、两名不同Reviewer。第一组a+b可在batch05复核结束后执行；生成者不审自己的图，root只改卡/装配/登记。

其余未到限失败项仍按1→2→3推进。已准备9个源卡第二轮修正，常规jobs_pending_round2.json中21/23/36/37/38已改走上述local_reframe；22/25/35追加已选机场主帧作为同一箱包的视觉参考、手臂一高一低区分左右持物。24需修回B反打，不能单纯裁A背景。01/02/03和batch05若失败尚待修改其具体字段。

新图工具结果原始路径在/home/codespace/.codex/generated_images/；每张立即用tmp/save_v3_generation.py shot ID ROUND INDEX SOURCE归档，先检查目的文件不存在。原始PNG不删，已有候选不覆盖。

## 最新续做09:30

21/23/36/37局部编辑第二轮已由两名生成者执行，正在独立双审；详见roster_edits_round2.json。14同镜局部取景计划已由Reviewer实际看图后生成并并入same_unit_crop_plans；edits_round2_14.json已装配。

剩余首轮失败项全部已按审查修正并装配备用：standard_round2_d(1/2)、e(3/15)、f(16/34)、g(22/24)、h(25/35)，以及edits_round2_c(38/09)、edits_round2_14(14)。只有从队列选出且不超过4活跃unit后才可派发。01/02/03/15修门外位置/手序/裁切；16同步p5旧blocking到批准首帧动作；34修右手箱、包尺寸、原通道；24加强B车道背景。

## 最新09:40之后

21/23/36/37第二轮8张已完成全部双审，全fail。roster_edits_round2.json确认四真实代理。第三轮源计划same_unit_crop_plans_round3.json（来自单图审查实际量图，target21_02/23_02/36_02/37_01），已装配edits_round3_a(21/23)、b(36/37)各6张但尚未生成。采用tight_reframe简短明确主脸/顶空/窄边指令。

当前第二轮1/9/14/38共8张全部生成，等待review_keyframes_round2_next_single.json和review_keyframes_edits_round2_09_14_38_continuity.json齐备。Generator IDs /root/generate_keyframes_batch04_b、/root/generate_edits_09_14。R1 /root/review_round2_next_single；R2 /root/review_edits_round2_continuity。R2已审9/14/38失败，但09_02与14_01主体已基本合规，最小修改仅左下陈野过肩缩到15%，其报告附minimal_edit_appendix。build_same_unit_edit_jobs.py已支持source prompt_variant=edge_only，等R1意见齐备再装配，不重复放大已经合格主体。

下一组标准第二轮已装配standard_round2_prison_a(2/3)、prison_b(15/16)，再后standard_round2_g(22/24)、h(25/35)；34还有2轮待执行。遵守最多4活跃unit。tmp/merge_v3_keyframe_reviews.py已增加真实generator_report与agent_id回填，审查排除生成者本人。


## 本会话续做（2026-09-05 10时）

- 真实子代理恢复为 Generator A/B、Reviewer 单图/连戏四名，峰值3名子代理；人员见roster_resume_20260905.json。
- 03第二轮缺图02已补齐；01/02/03/09/14第三轮候选03–05全部完成生成。独立审查进行中，以新的review_keyframes_resume_20260905_*.json为准。
- 已恢复永久登记脚本机器文件/merge_keyframe_reviews.py，替代丢失的tmp脚本；按真实图片/独立审查/生成者记录合并，JSON原子写入。禁止重复产出已有候选。
- 继承自v2的7张紧底板丢失，已从2026-09-04原始出图会话精确定位并全部无损恢复到v3内；来源及SHA256见reference_recovery_20260905.json。当前67项注册素材路径全部存在。
- 磁盘曾满，已暂停生成并保全原始返回路径；外部空间变化后恢复约645MB，候选归档已补齐。两份新审查报告已由原独立Reviewer重建；继续监控空间、报告先临时文件再替换。
- 下一组15/16第三轮计划已机械装配resume_prison_round3_15_16.json；21/23、36/37第三轮和22/24、25/35第二轮已有任务可执行。34第二轮单独提取resume_standard_round2_34.json；38第三轮提取resume_edits_round3_38.json。最多4个活跃镜头，等当前审查结束再推进。
