window.Views = window.Views || {};
Views.gpuCatalog = async function(app, data, form) {
  const box=app.querySelector('.gpu-catalog'), {esc}=ControlUI;
  if(!data.allowed){box.innerHTML='<p>管理员授予租卡权限后可查询实时机型。</p>';return;}
  box.innerHTML=`<h2>实时可用显卡与测试状态</h2>${data.h3_paused?'<p class="notice">视频生成通道已暂停，冷启动与各时长的详细耗时待测试。</p>':''}<p>RunPod Secure Cloud · 单卡 · 50 GB 容器盘要求。库存随时变化，查询有货不代表已预留；预览租卡时会再次查询。</p>
    <div class="notice a100-recommendation"><strong>推荐使用 A100，测试用例也以 A100 为基准。</strong><p>按项目方提供的参考速度：排除冷启动时间后，生成累计约 1 分钟视频，大约需要 10–20 分钟。这里指多个镜头的累计视频时长，实际耗时以任务为准。</p><p>考虑到冷启动需要额外等待，建议先积攒一批待生成的视频任务，再集中开启显卡批量制作，减少重复启动的等待与成本。批量生成前请准备好参考素材、确认任务，并预留足够的租期与预算。</p></div>
    <div class="toolbar"><button class="refresh-catalog" type="button">刷新实时库存</button><label><input type="checkbox" class="available-only" checked>只看当前有单卡库存</label></div>
    <p class="catalog-time" role="status">正在查询 RunPod…</p>
    <div class="catalog-table"></div><div class="catalog-estimate" role="status"></div>
    <details class="estimate-details"><summary>冷启动与生成测试说明</summary><div class="estimate-method"></div></details>`;
  const reload=box.querySelector('.refresh-catalog'), status=box.querySelector('.catalog-time');
  let snapshot=null, busy=false;
  const stockLabels={high:'充足',medium:'中等',low:'紧张',none:'暂无',unknown:'未知'};
  const range=()=> '待测试';
  const isA100=g=>/\bA100\b/i.test(g.name);
  function selectedEstimate(){
    if(!snapshot)return;
    const selected=snapshot.gpus.find(g=>g.id===form?.elements.gpu_id.value);
    box.querySelector('.catalog-estimate').innerHTML=`<p><strong>冷启动：</strong>已有权重：待测试；首次下载：待测试。</p>
      ${selected?`<p>已选 ${esc(selected.name)}：5 秒视频：待测试；10 秒视频：待测试；15 秒视频：待测试。</p>`:''}
      <p>冷启动及各时长的详细数据待测试；A100 的累计生成速度参考见上方推荐说明。</p>`;
  }
  function draw(){
    if(!snapshot)return;
    const rows=snapshot.gpus.filter(g=>!box.querySelector('.available-only').checked||g.available);
    box.querySelector('.catalog-table').innerHTML=ControlUI.table(['机型 / 显存','单卡库存','GPU 起价 / 小时','5 秒视频','10 秒视频','15 秒视频','选择'],rows.map(g=>{
      return `<tr><td>${esc(g.name)}${isA100(g)?' <span class="badge on">推荐 · 测试机型</span>':''}<br>${g.memory_gb} GB</td><td>${esc(stockLabels[g.stock]||'未知')}${!g.available?' · 暂不可选':''}</td><td>${g.hourly_usd===null?'暂无报价':'$'+Number(g.hourly_usd).toFixed(3)}</td>${[0,1,2].map(i=>`<td>${range()}</td>`).join('')}<td><button type="button" class="select-gpu small" data-id="${esc(g.id)}" ${!g.available||!form?'disabled':''}>选择</button></td></tr>`;
    }));
    if(!rows.length)box.querySelector('.catalog-table').innerHTML='<p>当前筛选下没有可确认的单卡库存。可取消“只看当前有单卡库存”查看全部机型，或稍后刷新。</p>';
    box.querySelectorAll('.select-gpu').forEach(button=>button.onclick=()=>{
      form.elements.gpu_id.value=button.dataset.id;
      app.querySelector('.rental-preview').replaceChildren();
      selectedEstimate();form.scrollIntoView({behavior:'smooth',block:'center'});
    });
    selectedEstimate();
  }
  async function refresh(){
    if(busy||!box.isConnected)return;
    busy=true;reload.disabled=true;status.textContent='正在向 RunPod 查询最新库存与价格…';
    if(form)form.querySelector('button').disabled=true;
    app.querySelector('.rental-preview').replaceChildren();
    try{
      const result=await API.control('GET','/api/gpu/catalog');
      if(!box.isConnected)return;
      snapshot=result;
      status.textContent=`查询时间：${ControlUI.time(snapshot.queried_at)} · ${snapshot.gpus.filter(g=>g.available).length} 种有单卡库存 / ${snapshot.gpus.length} 种机型 · 页面可见时每 30 秒刷新`;
      if(form){
        const selected=form.elements.gpu_id.value;
        const available=snapshot.gpus.filter(g=>g.available);
        form.elements.gpu_id.innerHTML=available.map(g=>`<option value="${esc(g.id)}">${esc(g.name)} · ${g.memory_gb} GB · $${g.hourly_usd}/小时 · ${esc(stockLabels[g.stock])}</option>`).join('')||'<option value="">暂时没有可用的单卡机型</option>';
        if(available.some(g=>g.id===selected))form.elements.gpu_id.value=selected;
        form.querySelector('button').disabled=!available.length;
      }
      box.querySelector('.estimate-method').innerHTML='<p>微调的视频模型推荐使用 A100，测试用例以 A100 为基准。项目方提供的速度参考为：排除冷启动后，生成累计约 1 分钟视频需 10–20 分钟。冷启动以及 5、10、15 秒任务的详细耗时仍待测试，不按比例自动推算。</p><p>价格来自 RunPod API，表内为 GPU 起价，磁盘等费用另计，完整预算见租卡预览。库存未知、没有单卡或无有效报价的机型不能直接选择。</p>';
      draw();
    }catch(error){
      snapshot=null;status.textContent='实时查询失败：'+error.message+'。请重试；旧库存与报价已停止使用。';
      box.querySelector('.catalog-table').replaceChildren();box.querySelector('.catalog-estimate').replaceChildren();
      if(form)form.elements.gpu_id.innerHTML='<option value="">实时查询失败，请刷新</option>';
    }finally{busy=false;reload.disabled=false;}
  }
  reload.onclick=refresh;
  box.querySelector('.available-only').onchange=draw;
  if(form)form.elements.gpu_id.onchange=()=>{app.querySelector('.rental-preview').replaceChildren();selectedEstimate();};
  await refresh();
  const timer=setInterval(()=>{
    if(!box.isConnected){clearInterval(timer);return;}
    // Keep an explicit approval review stable while the user reads it.
    if(!document.hidden && !app.querySelector('.rental-preview').textContent.trim())refresh();
  },30000);
};
