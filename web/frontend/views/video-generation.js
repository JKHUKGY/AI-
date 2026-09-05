Views.videoGeneration = async function(container,project,episode) {
  const base=`/api/projects/${encodeURIComponent(project)}/videos/${episode}/generation`;
  const [data,gpu]=await Promise.all([API.control('GET',base),API.control('GET','/api/gpu')]);
  const rentals=gpu.rentals.filter(r=>r.username===currentUser.username&&r.project===project&&r.status==='running'&&r.video_ready);
  container.innerHTML=`<div class="card"><h2>生成视频</h2><p>每条 ${data.credits} 点数；提交先冻结，成功下载后扣除，失败退还。</p>
    ${data.paused?'<p>视频生成通道已暂时停用，当前不能提交生成任务。</p>':!data.ready?'<p>管理员尚未启用视频运行环境。</p>':!data.jobs.length?'<p>这一集还没有准备好的视频生成任务，请先完成镜头卡与视频任务清单。</p>':!rentals.length?`<p>当前项目没有可用的视频显卡，请先<a href="#/gpu?project=${encodeURIComponent(project)}">租显卡</a>。</p>`:`
    <form class="video-form control-form"><label>视频任务<select name="job_id">${data.jobs.map(j=>`<option value="${UI.esc(j.id)}">${UI.esc(j.id)}</option>`).join('')}</select></label>
    <label>显卡<select name="rental_id">${rentals.map(r=>`<option value="${UI.esc(r.id)}">${UI.esc(r.gpu.name)}</option>`).join('')}</select></label><button>预览视频与点数</button></form>`}
    <div class="video-preview"></div><div class="toolbar"><button class="refresh-video">刷新任务</button><a href="#/gpu?project=${encodeURIComponent(project)}">查看 / 手动关闭显卡</a></div><div class="video-task-list"></div></div>`;
  function showTasks(tasks) {
    container.querySelector('.video-task-list').innerHTML=tasks.map(t=>`<div class="control-user"><strong>${UI.esc(t.detail.job_id)} · ${UI.esc(ControlUI.labels[t.status]||t.status)}</strong>
      <p>${t.charged} 点数已结算${t.detail.error?' · '+UI.esc(t.detail.error):''}</p>${t.detail.output?`<video class="preview" controls preload="metadata" src="${API.mediaUrl(t.detail.output)}"></video>`:''}</div>`).join('')||'<p class="muted">暂无视频生成任务。</p>';
  }
  showTasks(data.tasks);
  const refresh=async()=>{const value=await API.control('GET',base);if(container.isConnected)showTasks(value.tasks);};
  container.querySelector('.refresh-video').onclick=()=>refresh().catch(e=>UI.toast(e.message,'error'));
  const timer=setInterval(()=>{if(!container.isConnected){clearInterval(timer);return;}refresh().catch(()=>{});},10000);
  const form=container.querySelector('.video-form');if(!form)return;
  form.onsubmit=async e=>{
    e.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{
      const {task}=await API.control('POST',base+'/preview',Object.fromEntries(new FormData(form)));
      const box=container.querySelector('.video-preview');
      box.innerHTML=`<h3>确认生成 ${UI.esc(task.detail.job_id)}</h3><p>${task.target.duration_seconds} 秒 · ${task.target.short_edge} 像素短边 · 本次 ${task.credits} 点数</p><pre class="prompt-text"></pre><p>显卡继续按小时计费；本次点数不包含显卡费用。</p><label><input type="checkbox" class="approve-video">我确认上述提示词及费用</label><button class="start-video primary" disabled>确认并生成视频</button>`;
      box.querySelector('pre').textContent=task.detail.prompt;
      box.querySelector('.approve-video').onchange=e=>box.querySelector('.start-video').disabled=!e.target.checked;
      box.querySelector('.start-video').onclick=async e=>{
        e.target.disabled=true;
        try{await API.control('POST',`/api/video/${encodeURIComponent(task.id)}/start`,{approved:true});box.innerHTML='<p>已提交，点数已冻结，可在下方查看进度。</p>';await refresh();}
        catch(err){UI.toast(err.message,'error');e.target.disabled=false;}
      };
    }catch(err){UI.toast(err.message,'error');}finally{button.disabled=false;}
  };
};
