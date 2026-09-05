window.Views=window.Views||{};
Views['help-history']=async function(app){
  if(!currentUser?.is_admin){app.innerHTML='<p>仅管理员可查看助手对话记录。</p>';return;}
  const {esc}=ControlUI;
  app.innerHTML=`<h1>助手对话记录</h1><p>保存内置解释助手的提问和实际回答；按最新提问排序。此页面仅管理员可访问。</p><p><a href="#/admin">返回管理员管理</a></p>
    <form class="history-filter control-form"><label>账号（留空查看全部）<input name="username" maxlength="100"></label><label>对话编号（可选）<input name="conversation_id" maxlength="100"></label><button>查询 / 刷新</button></form>
    <p class="history-status" role="status"></p><div class="history-records"></div><div class="toolbar"><button class="history-newest">返回最新</button><button class="history-older" disabled>查看更早记录</button></div>`;
  let next=null,busy=false;
  const form=app.querySelector('form'),records=app.querySelector('.history-records'),status=app.querySelector('.history-status');
  const labels={done:'已回答',failed:'未完成回答',pending:'处理中或曾中断'};
  async function load(before){
    if(busy)return;busy=true;
    app.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='正在读取服务器记录…';
    try{
      const query=new URLSearchParams(new FormData(form));if(before)query.set('before',before);
      const data=await API.control('GET','/api/admin/help-conversations?'+query);
      if(!records.isConnected)return;
      next=data.next_before;
      records.innerHTML=data.records.map(r=>`<article class="card"><h3>${esc(r.username)} · ${esc(ControlUI.time(r.created_at))}</h3><p>${esc(r.project||'无项目')} · ${esc(r.page)} · ${esc(labels[r.status]||r.status)}</p>
        <p>对话编号：<button class="history-conversation small" data-id="${esc(r.conversation_id)}">${esc(r.conversation_id)}</button></p>
        <strong>用户提问</strong><pre class="prompt-text">${esc(r.question)}</pre><strong>助手回答</strong><pre class="prompt-text">${esc(r.answer??'暂无回答')}</pre>
        <p class="muted">记录 #${r.id} · 回答时间 ${esc(ControlUI.time(r.finished_at))}</p></article>`).join('')||'<p>暂无符合条件的记录。启用保存后，新问答会显示在这里。</p>';
      status.textContent=`本页 ${data.records.length} 条；每页最多 50 条。`;
      records.querySelectorAll('.history-conversation').forEach(b=>b.onclick=()=>{form.elements.conversation_id.value=b.dataset.id;load();});
    }catch(error){next=null;status.textContent='读取失败：'+error.message;records.replaceChildren();}
    finally{busy=false;if(records.isConnected){app.querySelectorAll('button').forEach(b=>b.disabled=false);app.querySelector('.history-older').disabled=!next;}}
  }
  form.onsubmit=e=>{e.preventDefault();load();};
  app.querySelector('.history-newest').onclick=()=>load();
  app.querySelector('.history-older').onclick=()=>load(next);
  await load();
};
