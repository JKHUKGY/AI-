Views.skills = async function (app, project) {
  const [catalog, projects] = await Promise.all([API.control('GET', '/api/skills'), API.projects()]);
  const esc = UI.esc;
  app.innerHTML = `<h1>制作 Skills</h1><p>${catalog.can_execute ? '从故事、分镜到图片和视频，按项目调用制作技能。加载自检验证文档与模型调用；执行结果会说明实际完成了什么。' : '管理员已授权你查看技能文档及已授权项目的调用记录与产物。'}</p>
    <label>当前项目 <select id="skillProject"><option value="">请选择项目</option>${projects.projects.map(p => `<option value="${esc(p.name)}" ${p.name === project ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label>
    <div class="skill-layout" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:2rem"><section><h2>已安装 ${catalog.skills.length} 个 Skills</h2><div id="skillCatalog"></div></section>
    <section id="skillDetail"></section></div><section><h2>调用记录与产物</h2><div id="skillRuns">选择项目后查看</div></section>`;
  app.querySelector('#skillProject').onchange = e => { location.hash = e.target.value ? `#/p/${encodeURIComponent(e.target.value)}/skills` : '#/skills'; };
  const detail = app.querySelector('#skillDetail'), runs = app.querySelector('#skillRuns');
  let selected = catalog.skills[0];
  function select(skill) {
    selected = skill;
    detail.innerHTML = `<h2>${esc(skill.title)}</h2><p>${esc(skill.description)}</p><p class="muted">${esc(skill.id)} · 版本 ${skill.version.slice(0, 12)} · ${skill.files} 个文件</p>
      ${!skill.enabled ? '<p class="notice">H3 按当前项目决定停用，可以自检加载。</p>' : ''}
      ${catalog.can_execute ? `<label>工作方式 <select id="skillMode"><option value="user_choice">分批反馈，由我选择</option>${skill.modes.includes('managed') ? '<option value="managed">完全托管，严格筛选</option>' : ''}</select></label>
      <p><label style="display:block">任务说明<textarea id="skillRequest" rows="5" maxlength="8000" style="display:block;width:100%;box-sizing:border-box;margin-top:.5rem;padding:.75rem" placeholder="说明要处理的集数、镜头、素材和希望得到的结果"></textarea></label></p>
      <button id="skillProbe" ${!project ? 'disabled' : ''}>加载调用自检</button> <button id="skillPreview" ${!project || !skill.enabled ? 'disabled' : ''}>给出执行方案</button>` : '<p class="notice">当前为只读查看，规划和执行由管理员操作。</p>'}
      <details><summary>查看原始 Skill 文档</summary><pre id="skillSource" style="white-space:pre-wrap;max-height:30rem;overflow:auto">展开后加载</pre></details>
      <p class="muted">执行会创建项目工作副本，产物留在调用记录中。当前带工具的执行对管理员开放；租显卡通过网站已有入口完成。</p>`;
    detail.querySelector('details').addEventListener('toggle', async e => {
      if (!e.target.open) return;
      try { const data = await API.control('GET', `/api/skills/${skill.id}`); if (selected.id === skill.id) detail.querySelector('#skillSource').textContent = data.text; }
      catch (err) { UI.toast(err.message, 'error'); }
    });
    for (const [id, action] of [['skillProbe', 'probe'], ['skillPreview', 'preview']]) {
      if (!catalog.can_execute) continue;
      detail.querySelector('#' + id).onclick = async e => {
        const button = e.target; button.disabled = true;
        try {
          await API.control('POST', `/api/projects/${encodeURIComponent(project)}/skills/${skill.id}/${action}`, {request: detail.querySelector('#skillRequest').value, mode: detail.querySelector('#skillMode').value});
          UI.toast('任务已提交，切换页面后仍会继续'); await TaskUI.refresh();
        } catch (err) { UI.toast(err.message, 'error'); }
        finally { button.disabled = false; }
      };
    }
  }
  for (const skill of catalog.skills) {
    const button = document.createElement('button'); button.textContent = skill.title;
    button.style.cssText = 'display:block;margin:0 0 .5rem;width:100%;text-align:left';
    button.onclick = () => select(skill); app.querySelector('#skillCatalog').append(button);
  }
  select(selected);
  let signature = '';
  TaskUI.subscribe(app, items => {
    if (!project) return;
    const tasks = items.filter(t => t.project === project && t.target?.type === 'skill').reverse();
    const next = JSON.stringify(tasks); if (next === signature) return; signature = next;
    runs.replaceChildren();
    if (!tasks.length) { runs.textContent = '暂无调用记录'; return; }
    for (const task of tasks) {
      const row = document.createElement('article'); row.className = 'notice';
      const labels = {running:'进行中', done:'已完成', failed:'失败', interrupted:'已中断', cancelled:'已终止'};
      row.innerHTML = `<h3>${esc(task.target.job_id)} · ${esc({probe:'加载自检',preview:'执行方案',execute:'实际执行'}[task.target.operation])} · ${esc(labels[task.status] || task.status)}</h3>`;
      if (task.result?.prompt || task.error) {
        const pre = document.createElement('pre'); pre.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;max-height:32rem;overflow:auto';
        pre.textContent = task.result?.prompt || task.error; row.append(pre);
      }
      if (task.status === 'running' && catalog.can_execute) {
        const stop = document.createElement('button'); stop.textContent = '终止调用';
        stop.onclick = async () => { stop.disabled = true; try { await TaskUI.cancel(task); } catch (err) { UI.toast(err.message, 'error'); stop.disabled = false; } }; row.append(stop);
      }
      if (task.status === 'done' && task.result?.scope === 'preview' && catalog.can_execute) {
        const go = document.createElement('button'); go.textContent = '批准以上方案并执行';
        go.onclick = async () => {
          go.disabled = true;
          try { await API.control('POST', `/api/projects/${encodeURIComponent(project)}/skills/execute`, {proposal:task.result.proposal, approved:true}); await TaskUI.refresh(); }
          catch (err) { UI.toast(err.message, 'error'); }
          finally { go.disabled = false; }
        }; row.append(go);
      }
      for (const path of task.result?.artifacts || []) {
        const link = document.createElement('a'); link.href = API.mediaUrl(path); link.target = '_blank'; link.rel = 'noopener';
        link.textContent = path.split('/workspace/output/')[1] || path; link.style.display = 'block'; row.append(link);
      }
      runs.append(row);
    }
  });
};
