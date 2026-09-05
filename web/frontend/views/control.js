window.Views = window.Views || {};
const ControlUI = (() => {
  const esc = UI.esc;
  const labels = {image:'图片',video:'视频',gpu:'租卡',prompt:'提示词',setup:'项目筹备',help:'帮助问答',login:'登录',mail_test:'测试邮件',
    reserved:'积分已冻结',running:'运行中',done:'已完成',failed:'失败',cancelled:'已终止',interrupted:'已中断',
    preview:'待确认',creating:'创建中',unknown:'待核实',stopping:'正在释放',terminated:'已释放'};
  const time = value => value ? new Date(value*1000).toLocaleString() : '暂无';
  const table = (headers,rows) => `<div class="control-table"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.join(''):`<tr><td colspan="${headers.length}">暂无记录</td></tr>`}</tbody></table></div>`;
  function usage(rows) {
    return table(['时间','账号 / 项目','操作','数量','状态','已扣积分'],rows.map(r=>`<tr><td>${esc(time(r.created_at))}</td><td>${esc(r.username)}<br>${esc(r.project||'—')}</td><td>${esc(labels[r.kind]||r.kind)}</td><td>${r.quantity}</td><td>${esc(labels[r.status]||r.status)}</td><td>${r.charged}</td></tr>`));
  }
  function rentals(rows) {
    return table(['账号 / 项目','机型','状态','时长 / 到期','价格 / 估算费用','GPU / 显存','操作'],rows.filter(r=>r.status!=='preview').map(r=>{
      const gpu=r.runtime?.gpus?.[0];
      return `<tr><td>${esc(r.username)}<br>${esc(r.project)}</td><td>${esc(r.gpu?.name||'—')}</td><td>${esc(labels[r.status]||r.status)}${r.error?`<p class="notice error">${esc(r.error)}</p>`:''}</td><td>${Math.floor((r.elapsed_seconds||0)/60)} 分钟<br>${esc(time(r.expires_at))}</td><td>$${Number(r.hourly_usd||0).toFixed(4)}/小时<br>约 $${Number(r.cost_estimate_usd||0).toFixed(4)}</td><td>${gpu?`${gpu.gpuUtilPercent}% / ${gpu.memoryUtilPercent}%`:'暂无实时数据'}</td><td>${['creating','unknown','running','stopping'].includes(r.status)?`<button class="stop-rental small" data-id="${esc(r.id)}">释放显卡</button>`:'—'}</td></tr>`;
    }));
  }
  function bindStops(app,refresh) {
    app.querySelectorAll('.stop-rental').forEach(button=>button.onclick=async()=>{
      if (!confirm('确认释放这台显卡？正在运行的视频会停止，容器盘内的临时文件会清除。已下载到网站的文件保留。')) return;
      button.disabled=true;
      try {await API.control('POST',`/api/gpu/${button.dataset.id}/stop`,{confirmed:true}); await refresh();}
      catch(e){UI.toast(e.message,'error');}
      finally{button.disabled=false;}
    });
  }
  return {esc,labels,time,table,usage,rentals,bindStops};
})();

Views.admin = async function(app) {
  if(!currentUser?.is_admin) {app.innerHTML='<div class="notice error">仅管理员可访问。</div>'; return;}
  const data=await API.control('GET','/api/admin/overview'); const {esc}=ControlUI;
  app.innerHTML=`<h1>管理员管理</h1><p>分配项目、停用账号、管理积分及查看使用记录。</p>
    <div class="toolbar"><button class="admin-refresh">刷新使用情况</button><a href="#/gpu">租卡管理</a><a href="#/usage">我的积分</a></div>
    <div class="card"><h2>账号与项目权限</h2><p>新账号可用积分为 0。图片每张 10 积分，视频每条 300 积分；提交先冻结，成功后结算，未完成部分退还。</p>
    <form class="create-user control-form"><label>新账号<input name="username" required maxlength="40"></label><label>初始密码<input name="password" type="password" required minlength="12" autocomplete="new-password"></label><button class="primary">创建账号</button></form><div class="admin-users"></div></div>
    <div class="card"><h2>服务配置</h2><p class="mail-state"></p><form class="admin-settings control-form"></form></div>
    <div class="card"><h2>租卡运行情况</h2><p>费用为按运行时间计算的估算，最终金额以 RunPod 账单为准；释放中的实例尚未确认停止计费。</p><div class="admin-rentals"></div></div>
    <div class="card"><h2>每人使用汇总</h2><div class="admin-totals"></div></div>
    <div class="card"><h2>最近使用记录</h2><div class="admin-usage"></div></div>
    <div class="card"><h2>积分流水</h2><div class="admin-ledger"></div></div>`;
  const users=app.querySelector('.admin-users');
  for(const user of data.users) {
    const item=document.createElement('div'); item.className='control-user';
    item.innerHTML=`<h3>${esc(user.display_name)} <span class="muted">${esc(user.username)} · ${user.admin?'管理员':'普通账号'} · ${user.enabled?'启用':'已停用'}</span></h3>
      <p class="account-balance">可用 ${user.balance} 积分 · 冻结 ${user.held} 积分 · 最近访问 ${esc(ControlUI.time(user.last_seen))}</p>
      <div class="control-projects">${data.projects.map(p=>`<label><input type="checkbox" value="${esc(p)}" ${user.projects.includes(p)?'checked':''} ${user.admin?'disabled':''}>${esc(p)}</label>`).join('')}</div>
      <div class="toolbar"><label><input class="gpu-permission" type="checkbox" ${user.gpu_allowed?'checked':''} ${user.admin?'disabled':''}>允许租显卡</label><button class="save-access" ${user.admin?'disabled':''}>保存权限</button>
      <button class="toggle-user" ${user.username===currentUser.username?'disabled':''}>${user.enabled?'立即停用并停止任务':'重新启用'}</button></div>
      <form class="grant-credits toolbar"><label>增加 / 减少积分<input name="delta" type="number" step="1" min="-10000000" max="10000000" placeholder="例如 1000 或 -100" required></label><button>确认调整积分</button></form>
      <details><summary>重置密码</summary><form class="reset-password toolbar"><input name="password" type="password" minlength="12" required autocomplete="new-password" placeholder="至少 12 位新密码"><button>重置并撤销旧登录</button></form></details>`;
    users.appendChild(item);
    const action=async(type,body)=>API.control('POST',`/api/admin/users/${encodeURIComponent(user.username)}/${type}`,body);
    item.querySelector('.save-access').onclick=async e=>{
      e.target.disabled=true;
      try {await action('access',{projects:[...item.querySelectorAll('.control-projects input:checked')].map(i=>i.value),gpu_allowed:item.querySelector('.gpu-permission').checked});UI.toast('权限已保存');}
      catch(err){UI.toast(err.message,'error');}finally{e.target.disabled=false;}
    };
    item.querySelector('.toggle-user').onclick=async e=>{
      e.target.disabled=true;
      try{await action('enabled',{enabled:!user.enabled}); await Views.admin(app);}catch(err){UI.toast(err.message,'error');e.target.disabled=false;}
    };
    item.querySelector('.grant-credits').onsubmit=async e=>{
      e.preventDefault(); const button=e.target.querySelector('button');button.disabled=true;
      const requestId=e.target.dataset.requestId||crypto.randomUUID();e.target.dataset.requestId=requestId;
      try{await action('credits',{delta:Number(new FormData(e.target).get('delta')),request_id:requestId});delete e.target.dataset.requestId;await Views.admin(app);}
      catch(err){UI.toast(err.message,'error');}finally{button.disabled=false;}
    };
    item.querySelector('.reset-password').onsubmit=async e=>{
      e.preventDefault(); const button=e.target.querySelector('button');button.disabled=true;
      try{await action('password',{password:new FormData(e.target).get('password')});e.target.reset();UI.toast('密码已重置，旧登录已撤销');}catch(err){UI.toast(err.message,'error');}finally{button.disabled=false;}
    };
  }
  app.querySelector('.create-user').onsubmit=async e=>{
    e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;
    try{await API.control('POST','/api/admin/users',Object.fromEntries(new FormData(e.target)));await Views.admin(app);}catch(err){UI.toast(err.message,'error');}finally{button.disabled=false;}
  };
  const fields=[['mail_to','通知收件邮箱','email'],['mail_from','发信邮箱','email'],['smtp_host','SMTP 服务器','text'],['smtp_port','SMTP 端口','number'],['smtp_user','SMTP 登录账号','text'],['smtp_password','SMTP 授权码 / 密码','password'],['runpod_api_key','RunPod API Key','password'],['gpu_image','RunPod 运行镜像','text'],['gpu_public_key','SSH 公钥（非私钥）','text'],['gpu_max_minutes','每次最长租用分钟数（最多 240）','number'],['gpu_max_usd','每次美元预算上限（最多 100）','number']];
  const settings=app.querySelector('.admin-settings'), config=data.settings;
  settings.innerHTML=fields.map(([key,label,type])=>`<label>${esc(label)}<input name="${key}" type="${type}" step="${key==='gpu_max_usd'?'0.01':'1'}" value="${type==='password'?'':esc(String(config[key]??({smtp_port:465,gpu_max_minutes:60,gpu_max_usd:10}[key]??'')))}" placeholder="${type==='password'&&config[key+'_configured']?'已设置；留空保留原值':''}" autocomplete="off"></label>`).join('')+
    `<label>SMTP 加密<select name="smtp_security"><option value="ssl">SSL</option><option value="starttls">STARTTLS</option></select></label>
    <label><input name="gpu_enabled" type="checkbox" ${config.gpu_enabled?'checked':''}>启用网站租卡</label>
    <label><input name="video_ready" type="checkbox" ${config.video_ready?'checked':''}>运行镜像已提供 H3 / SGLang 视频服务（端口 30011）</label>
    <p class="muted">API Key 和邮件授权码只保存于服务器，页面不会回显。运行镜像由管理员配置；请先验证模型服务，再开放视频生成。</p>
    <div class="toolbar"><button class="primary">保存服务配置</button><button type="button" class="test-mail">发送测试邮件</button></div>`;
  settings.elements.smtp_security.value=config.smtp_security||'ssl';
  settings.onsubmit=async e=>{
    e.preventDefault(); const button=settings.querySelector('button');button.disabled=true;
    const body=Object.fromEntries(new FormData(settings));
    for(const key of ['smtp_port','gpu_max_minutes','gpu_max_usd']) body[key]=Number(body[key]);
    for(const key of ['gpu_enabled','video_ready']) body[key]=settings.elements[key].checked;
    try{await API.control('POST','/api/admin/settings',body);settings.elements.smtp_password.value='';settings.elements.runpod_api_key.value='';UI.toast('配置已保存');await refresh();}catch(err){UI.toast(err.message,'error');}finally{button.disabled=false;}
  };
  settings.querySelector('.test-mail').onclick=async()=>{try{await API.control('POST','/api/admin/mail/test',{});UI.toast('测试邮件已排队，请稍后刷新发送状态');}catch(err){UI.toast(err.message,'error');}};
  async function refresh(snapshot) {
    const value=snapshot||await API.control('GET','/api/admin/overview');
    if(!app.querySelector('.admin-usage'))return;
    app.querySelector('.admin-usage').innerHTML=ControlUI.usage(value.usage);
    app.querySelector('.admin-rentals').innerHTML=ControlUI.rentals(value.rentals);
    app.querySelector('.admin-totals').innerHTML=ControlUI.table(['账号','操作','次数','进行中','已扣积分'],value.totals.map(r=>`<tr><td>${esc(r.username)}</td><td>${esc(ControlUI.labels[r.kind]||r.kind)}</td><td>${r.tasks}</td><td>${r.running}</td><td>${r.charged}</td></tr>`));
    app.querySelector('.admin-ledger').innerHTML=ControlUI.table(['时间','账号','变动','原因','操作人'],value.ledger.map(r=>`<tr><td>${esc(ControlUI.time(r.created_at))}</td><td>${esc(r.username)}</td><td>${r.delta>0?'+':''}${r.delta}</td><td>${esc(r.reason)}</td><td>${esc(r.actor)}</td></tr>`));
    app.querySelector('.mail-state').textContent=`邮件：${value.mail.configured?'已配置':'尚未配置完整，通知会保留在队列中'} · 已发送 ${value.mail.counts.sent||0} · 待发 ${value.mail.counts.pending||0} · 失败重试 ${value.mail.counts.failed||0}`;
    ControlUI.bindStops(app,refresh);
  }
  app.querySelector('.admin-refresh').onclick=()=>refresh().catch(e=>UI.toast(e.message,'error'));
  await refresh(data);
};

Views.usage = async function(app) {
  const data=await API.control('GET','/api/usage');
  app.innerHTML=`<h1>我的使用情况</h1><div class="card"><h2>可用 ${data.account.balance} 积分</h2><p>冻结中 ${data.account.held} 积分。图片每张 10 积分，视频每条 300 积分；未完成部分退还。</p><p>需要积分或项目权限时，请联系管理员。</p><button class="refresh-usage">刷新</button></div><div class="card">${ControlUI.usage(data.usage)}</div>`;
  app.querySelector('.refresh-usage').onclick=()=>Views.usage(app).catch(e=>UI.toast(e.message,'error'));
};

Views.gpu = async function(app) {
  const [data,projects]=await Promise.all([API.control('GET','/api/gpu'),API.projects()]); const {esc}=ControlUI;
  app.innerHTML=`<h1>RunPod 租显卡</h1><p>查看机型和预算后确认启动。到期自动释放，也可提前释放；费用由 RunPod 账号支付，图片与视频积分另行结算。</p>
    <div class="notice warn">释放显卡会清除容器盘中的临时文件。请将需要的结果下载到网站；释放状态须经 RunPod 确认。</div>
    <div class="card"><h2>新建租卡任务</h2>${!data.enabled?'<p>管理员尚未启用租卡，请联系管理员配置。</p>':!data.allowed?'<p>你的账号尚未获准租卡，请联系管理员。</p>':`
    <form class="rent-form control-form"><label>项目<select name="project" required>${projects.projects.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}</option>`).join('')}</select></label>
    <label>显卡<select name="gpu_id" required><option value="">加载实时报价…</option></select></label><label>租用分钟数<input name="minutes" type="number" min="5" max="${data.max_minutes}" value="${Math.min(30,data.max_minutes)}" required></label>
    <label>美元预算上限<input name="max_usd" type="number" min="0.01" step="0.01" max="${data.max_usd}" value="${data.max_usd}" required></label><button class="primary">预览租卡方案</button></form>`}<div class="rental-preview"></div></div>
    <div class="card"><h2>使用情况</h2><button class="refresh-rentals">刷新状态</button><div class="rental-list"></div></div>`;
  async function refresh(){const current=await API.control('GET','/api/gpu'); if(!app.querySelector('.rental-list'))return; app.querySelector('.rental-list').innerHTML=ControlUI.rentals(current.rentals);ControlUI.bindStops(app,refresh);}
  app.querySelector('.refresh-rentals').onclick=()=>refresh().catch(e=>UI.toast(e.message,'error'));
  await refresh();
  const form=app.querySelector('.rent-form'); if(!form)return;
  try {const catalog=await API.control('GET','/api/gpu/catalog');form.elements.gpu_id.innerHTML=catalog.gpus.map(g=>`<option value="${esc(g.id)}">${esc(g.name)} · ${g.memory_gb} GB · 起价 $${g.hourly_usd}/小时 · ${esc(g.stock||'库存待确认')}</option>`).join('');}
  catch(err){form.elements.gpu_id.innerHTML='<option value="">无法读取机型，请刷新重试</option>';UI.toast(err.message,'error');}
  form.onsubmit=async e=>{
    e.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{
      const body=Object.fromEntries(new FormData(form));body.minutes=Number(body.minutes);body.max_usd=Number(body.max_usd);
      const {rental}=await API.control('POST',`/api/projects/${encodeURIComponent(body.project)}/gpu/preview`,body);
      const box=app.querySelector('.rental-preview');
      box.innerHTML=`<h3>确认租卡方案</h3><p>${esc(rental.gpu.name)} · ${rental.minutes} 分钟 · 预计 $${rental.estimated_usd} · 预算上限 $${rental.max_usd}</p><p>到期自动释放；如实际价格超出本次预算，系统会请求释放。费用估算与最终账单可能有差异。</p><label><input class="approve-rental" type="checkbox">我已检查机型、时长、预算和释放方式，批准本次租卡</label><div class="toolbar"><button class="start-rental primary" disabled>批准并租用</button><button class="dismiss-rental">取消</button></div>`;
      box.querySelector('.approve-rental').onchange=e=>box.querySelector('.start-rental').disabled=!e.target.checked;
      box.querySelector('.dismiss-rental').onclick=()=>box.replaceChildren();
      box.querySelector('.start-rental').onclick=async e=>{
        e.target.disabled=true;
        try{await API.control('POST',`/api/gpu/${rental.id}/start`,{approved:true});box.innerHTML='<p>已提交租卡，正在创建实例。可刷新下方查看状态。</p>';await refresh();}
        catch(err){UI.toast(err.message,'error');e.target.disabled=false;}
      };
    }catch(err){UI.toast(err.message,'error');}finally{button.disabled=false;}
  };
};
