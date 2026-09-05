window.Views = window.Views || {};

Views.scenes = async function scenes(app, project) {
  const data = await API.scenes(project);
  app.innerHTML = `
    <h1>${UI.esc(project)} · 场景设计</h1>
    <div class="manage-content"></div>
    <div class="card">${data.intro_html || '还没有场景，点击“新增场景”开始。'}</div>
    <div id="sceneList"></div>
  `;
  const listEl = document.getElementById('sceneList');
  ContentEditor.toolbar(app.querySelector('.manage-content'), project, 'scene');
  (data.scenes || []).forEach((sec) => {
    const block = document.createElement('div');
    block.className = 'figure-block';
    block.innerHTML = `<h2>${UI.esc(sec.title)}</h2><div class="sec-mount"></div><div class="jobs-mount"></div>`;
    listEl.appendChild(block);
    ContentEditor.deleteButton(block.querySelector('h2'), project, {kind:'scene',title:sec.title});
    UI.mountEditableSection(block.querySelector('.sec-mount'), {
      text: sec.body,
      html: sec.html,
      onSave: (newText) => API.patchScene(project, sec.title, newText),
      project,
      opts: { kind: 'asset', baseDirHint: 'assets' },
      jobs: sec.variants,
    });
    const jobsMount = block.querySelector('.jobs-mount');
    const jobIds = Object.keys(sec.variants);
    if (!jobIds.length) {
      jobsMount.innerHTML = '<div class="muted">还没有生成对应的场景图。</div>';
      return;
    }
    jobIds.forEach((jobId) => {
      UI.mountAssetJob(jobsMount, project, jobId, sec.variants[jobId], { kind: 'asset', baseDirHint: 'assets' });
    });
  });
};
