const HelpUI = (() => {
  let mounted = false;
  function init(username) {
    if (mounted) return;
    mounted = true;
    const key = 'system-help:' + username;
    let messages = [], busy = false;
    try { messages = JSON.parse(sessionStorage.getItem(key) || '[]').filter(m => ['user','assistant'].includes(m.role) && typeof m.content === 'string').slice(-12); } catch {}
    const button = document.createElement('button');
    button.className = 'help-launch primary'; button.textContent = '？ 使用帮助';
    button.setAttribute('aria-expanded', 'false'); button.setAttribute('aria-controls', 'help-panel');
    const panel = document.createElement('aside'); panel.id = 'help-panel'; panel.className = 'help-panel'; panel.hidden = true;
    panel.setAttribute('aria-label', '系统使用帮助');
    panel.innerHTML = `<div class="help-header"><div><strong>系统使用帮助</strong><div class="muted">GPT-5.6 Luna</div></div><button class="help-close" aria-label="收起帮助">×</button></div>
      <p class="help-context muted"></p><p class="help-intro">不知道下一步怎么做？直接问我，我会按当前页面给你指引。</p>
      <div class="help-shortcuts"><button type="button">怎么创建新项目？</button><button type="button">生成中可以离开页面吗？</button><button type="button">怎么完全重新生成？</button><button type="button">图片如何审批？</button></div>
      <div class="help-messages" role="log" aria-live="polite" aria-label="帮助对话"></div>
      <div class="help-status muted" role="status"></div><div class="help-links"></div>
      <form class="help-form"><label for="help-input">你想了解什么？</label><textarea id="help-input" rows="2" maxlength="2000" placeholder="例如：我已经导入剧本，接下来点哪里？"></textarea><div class="help-actions"><button type="button" class="help-clear small">新开对话</button><button type="submit" class="primary help-send">发送</button></div></form>`;
    document.body.append(button, panel);
    const input = panel.querySelector('textarea'), status = panel.querySelector('.help-status'), log = panel.querySelector('.help-messages');
    function save() { try { sessionStorage.setItem(key, JSON.stringify(messages.slice(-12))); } catch {} }
    function draw() {
      log.replaceChildren();
      if (!messages.length) {
        const welcome = document.createElement('p'); welcome.className = 'help-welcome'; welcome.textContent = '可以问我新建项目、历史提示词、生成进度、选参考图，以及图片审批的操作方法。'; log.appendChild(welcome);
      }
      for (const message of messages) {
        const item = document.createElement('div'); item.className = 'help-message ' + message.role;
        const label = document.createElement('strong'); label.textContent = message.role === 'user' ? '你' : '使用助手';
        const text = document.createElement('div'); text.textContent = message.content; item.append(label,text); log.appendChild(item);
      }
      log.scrollTop = log.scrollHeight;
    }
    function context() {
      const route = parseHash();
      const titles = {home:'项目首页',setup:'项目筹备',characters:'人物',scenes:'场景',style:'风格简报',episode:'分镜表',keyframes:'关键帧',videos:'视频',guide:'指南',inbox:'反馈汇总'};
      panel.querySelector('.help-context').textContent = '当前：' + (route.project ? route.project + ' · ' : '') + (titles[route.name] || '项目首页');
      const links = panel.querySelector('.help-links'); links.replaceChildren();
      const targets = [['#/guide','查看操作指南'], ['#/','项目首页']];
      if (route.project) targets.push([`#/p/${encodeURIComponent(route.project)}/setup`,'查看项目筹备']);
      targets.forEach(([href,title]) => { const a = document.createElement('a'); a.href = href; a.textContent = title; links.appendChild(a); });
      return {page:route.name, project:route.project || null};
    }
    function setOpen(open) {
      panel.hidden = !open; button.setAttribute('aria-expanded', String(open));
      if (open) { context(); input.focus(); } else button.focus();
    }
    button.addEventListener('click', () => setOpen(panel.hidden));
    panel.querySelector('.help-close').addEventListener('click', () => setOpen(false));
    panel.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });
    window.addEventListener('hashchange', context);
    async function ask(question) {
      if (busy || !question.trim()) return;
      question = question.trim();
      const history = messages.slice(-10).map(m => ({role:m.role, content:m.content.slice(0,6000)}));
      const requestContext = context();
      busy = true; messages.push({role:'user',content:question}); save(); draw();
      input.value = ''; input.disabled = true;
      panel.querySelectorAll('button').forEach(b => { if (!b.classList.contains('help-close')) b.disabled = true; });
      status.textContent = '正在查阅操作指南并回答…可以收起窗口，回答会保留。';
      try {
        const result = await API.helpQuestion({question, history, ...requestContext});
        messages.push({role:'assistant',content:result.answer}); messages = messages.slice(-12); save(); draw();
        status.textContent = '回答基于操作指南和提问时的页面；不会替你执行或审批任务。';
      } catch (err) {
        status.textContent = '暂时无法回答：' + err.message + '。问题已放回输入框，可再次发送。';
        messages.pop(); save(); draw(); input.value = question;
      } finally {
        busy = false; input.disabled = false; panel.querySelectorAll('button').forEach(b => { b.disabled = false; });
      }
    }
    panel.querySelector('form').addEventListener('submit', e => { e.preventDefault(); ask(input.value); });
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(input.value); } });
    panel.querySelectorAll('.help-shortcuts button').forEach(b => b.addEventListener('click', () => ask(b.textContent)));
    panel.querySelector('.help-clear').addEventListener('click', () => { if (!busy) { messages = []; save(); draw(); status.textContent = ''; input.focus(); } });
    draw(); context();
  }
  return {init};
})();
