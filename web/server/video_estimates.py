"""Video timing data remains unset until measurements are available."""


def generation(gpu_name, steps=50):
    if steps not in (20, 50):
        raise ValueError('Unsupported estimate profile')
    return [{'video_seconds':seconds,'status':'pending','min_minutes':None,'max_minutes':None}
            for seconds in (5,10,15)]


def methodology():
    return {
        'status':'pending', 'model':'微调的视频模型',
        'basis':'冷启动和视频生成耗时均待测试，完成实际测试后再更新。',
        'cold_start':{'status':'pending','cached_minutes':None,'first_download_minutes':None},
        'scope':'分段耗时与冷启动待测试。显卡库存与价格由 RunPod API 实时查询。',
        'recommendation':{'gpu':'A100','test_gpu':'A100','basis':'项目方提供的参考速度，具体以实际任务为准',
                          'generated_video_seconds':60,'generation_minutes':[30,30],
                          'excludes_cold_start':True,'duration_scope':'多个镜头累计视频时长',
                          'batch_advice':'先积攒待生成任务，再集中开卡批量制作，减少重复冷启动。'},
    }
