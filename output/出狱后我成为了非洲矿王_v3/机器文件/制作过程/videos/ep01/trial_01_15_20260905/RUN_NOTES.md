# 本批执行记录

- 用户授权范围：第1集镜01—15，RunPod + LTX-2.5，一轮测试档试片。对应20单元、5条尾帧依赖。
- 使用已有300GB卷 vr1dk0uvnx；新Pod i1mdtadbn5g0ux，实际A100 80GB PCIe，API实际创建价 $1.59/小时。最低价列表中的AMD MI300X不兼容本次CUDA环境，调用原rent_cheapest时只筛NVIDIA，未修改技能源码。
- 远端 `/workspace/LTX-2` 与5份LTX-2.5权重实际存在，checkpoint日志声明2.5.0。没有重下权重。
- distilled和DFR的远端 --help 均已实际执行；DFR必需detailing LoRA未在现有卷发现。本轮用distilled，镜14接受仅作能力观察的单轮试片，错误表情不判作通过。
- 使用技能ltx_batch.py同一套DistilledPipeline调用，制作本批请求队列适配器。模型进程仅初始化一次；每个请求的argv都由ltx_ssh_submit.build_remote_cmd装配，提示词来自镜头卡。首段调用前实际完成export校验和CLI dry-run，续段回填真实尾帧后再次校验。
- 初次解tar遇Network Volume不允许chown，用--no-same-owner重新提取成功。未修改卷权限。
- SSH/SCP使用本批bin包装器，在项目内保存known_hosts并加保活；未改全局SSH配置。
- 长进程使用工具运行会话持续持有。独立闲置看门狗及独立收工守卫均持有运行会话；控制器退出后守卫调用gpu_teardown --platform-config并核实关机。最初控制器已运行版本误用了--runpod-config，源文件已修正，独立守卫确保本轮也使用正确参数。最终状态以teardown_guard.log及RunPod只读复核为准。
- 本批不自动循环换seed重做。对照原剧情检查动作、表情、人物、道具和连戏；视频是否生成与质量是否通过分别记录。
- 音频：记录音轨和volumedetect，不能由响度推出台词正确；听审未完成时明确标记。
