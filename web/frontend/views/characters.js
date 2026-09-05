window.Views = window.Views || {};

Views.characters = async function characters(app, project) {
  const data = await API.characters(project);
  app.innerHTML = `
    <h1>${UI.esc(project)} · 人物设计</h1>
    <div class="manage-content"></div>
    <div class="card">${data.intro_html || '还没有人物，点击“新增角色”开始。'}</div>
    <div id="charList"></div>
  `;
  const listEl = document.getElementById('charList');
  ContentEditor.toolbar(app.querySelector('.manage-content'), project, 'character');
  (data.characters || []).forEach((sec) => {
    const block = document.createElement('div');
    block.className = 'figure-block';
    block.innerHTML = `<h2>${UI.esc(sec.title)}</h2><div class="sec-mount"></div><div class="jobs-mount"></div>`;
    listEl.appendChild(block);
    ContentEditor.deleteButton(block.querySelector('h2'), project, {kind:'character',title:sec.title});
    UI.mountEditableSection(block.querySelector('.sec-mount'), {
      text: sec.body,
      html: sec.html,
      onSave: (newText) => API.patchCharacter(project, sec.title, newText),
      project,
      opts: { kind: 'asset', baseDirHint: 'assets' },
      jobs: sec.variants,
    });
    const jobsMount = block.querySelector('.jobs-mount');
    const jobIds = Object.keys(sec.variants);
    if (!jobIds.length) {
      jobsMount.innerHTML = '<div class="muted">还没有生成对应的立绘图片。</div>';
      return;
    }
    jobIds.forEach((jobId) => {
      UI.mountAssetJob(jobsMount, project, jobId, sec.variants[jobId], { kind: 'asset', baseDirHint: 'assets' });
    });
  });
};
