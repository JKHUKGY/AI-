window.Views = window.Views || {};
Views.gpuMonitor = async function(box) {
  const {esc}=ControlUI;let busy=false;
  const percent=value=>typeof value==='number'&&Number.isFinite(value)?`${value.toFixed(1)}%`:'暂无数据';
  const duration=value=>typeof value==='number'&&Number.isFinite(value)?`${Math.floor(value/3600)} 小时 ${Math.floor(value%3600/60)} 分 ${Math.floor(value%60)} 秒`:'暂无数据';
  const metric=(label,value)=>`<div class="gpu-metric"><span>${esc(label)}</span><strong>${percent(value)}</strong>${typeof value==='number'&&Number.isFinite(value)?`<meter min="0" max="100" value="${Math.max(0,Math.min(100,value))}" aria-label="${esc(label)}"></meter>`:''}</div>`;
  box.innerHTML=`<div class="toolbar"><h2>显卡实时监控</h2><button type="button" class="refresh-monitor">刷新监控</button></div><p class="monitor-status" role="status">正在读取…</p><p class="muted">页面可见时每 15 秒向 RunPod 查询。指标可能存在平台采样延迟；刷新不会延长空闲关卡时间。</p><div class="monitor-cards"></div>`;
  const button=box.querySelector('.refresh-monitor'),status=box.querySelector('.monitor-status'),cards=box.querySelector('.monitor-cards');
  async function refresh(){
    if(busy||!box.isConnected)return;
    busy=true;button.disabled=true;status.textContent='正在向 RunPod 查询显卡使用情况…';
    try{
      const result=await API.control('GET','/api/gpu/monitor');
      if(!box.isConnected)return;
      status.textContent=`最近查询：${ControlUI.time(result.refreshed_at)} · ${result.rentals.length} 台在管理中 · ${result.is_admin?'管理员查看全部账号':'仅显示本人租用的显卡'}`;
      cards.innerHTML=result.rentals.map(r=>{
        const runtime=r.runtime, state={live:'已取得实时数据',pending:'等待实例启动或平台上报',error:'实时查询失败',missing:'实例待核实'}[r.monitor_state]||'暂无数据';
        const idle=r.active_tasks?'有视频任务，空闲关卡计时暂停':`空闲自动关闭倒计时：${duration(Math.max(0,r.idle_deadline-result.refreshed_at))}`;
        return `<article class="gpu-monitor-card"><h3>${esc(r.gpu?.name||'显卡创建中')} · ${esc(r.project)}</h3><p>${esc(r.username)} · 网站状态：${esc(ControlUI.labels[r.status]||r.status)}${r.provider_status?' · RunPod 目标状态：'+esc(r.provider_status):''}</p>
          <p class="${r.monitor_state==='error'?'notice error':'muted'}">${esc(state)}${r.queried_at?' · 查询于 '+esc(ControlUI.time(r.queried_at)):''}${r.monitor_error?' · '+esc(r.monitor_error):''}</p>
          ${(runtime?.gpus||[]).map((g,i)=>`<h4>GPU ${i+1}</h4><div class="gpu-metrics">${metric('GPU 利用率',g.gpuUtilPercent)}${metric('显存占用',g.memoryUtilPercent)}</div>`).join('')||'<p>GPU 与显存指标暂无数据。</p>'}
          <div class="gpu-metrics">${metric('CPU 利用率',runtime?.container?.cpuPercent)}${metric('主机内存占用',runtime?.container?.memoryPercent)}</div>
          <p>实例已运行：${duration(runtime?.uptimeInSeconds)} · 未完成视频任务：${r.active_tasks}</p><p>${esc(idle)} · 租期截止：${esc(ControlUI.time(r.expires_at))}</p>
          <p>最近费用记录：约 $${Number(r.cost_estimate_usd||0).toFixed(4)} · $${Number(r.hourly_usd||0).toFixed(4)}/小时 · 更新于 ${esc(ControlUI.time(r.last_checked))}，以 RunPod 账单为准。</p>
          <button class="stop-rental" data-id="${esc(r.id)}">手动关闭显卡</button></article>`;
      }).join('')||'<p class="empty-hint">当前没有正在管理的显卡。租卡启动后，这里会显示实时使用情况。</p>';
      ControlUI.bindStops(box,refresh);
    }catch(error){
      if(box.isConnected){status.textContent='刷新失败：'+error.message+'。请点击“刷新监控”重试。';cards.innerHTML='<p>当前监控数据不可用，旧指标已清除。</p>';}
    }finally{busy=false;button.disabled=false;}
  }
  button.onclick=refresh;
  await refresh();
  const timer=setInterval(()=>{if(!box.isConnected){clearInterval(timer);return;}if(!document.hidden)refresh();},15000);
  return refresh;
};
