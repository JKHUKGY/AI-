window.Views = window.Views || {};

Views.scenes = async function scenes(app, project) {
  const data = await API.scenes(project);
  if (!data.exists) {
    app.innerHTML = '<div class="empty-hint">这个项目还没有场景设计文档（scenes.md）。</div>';
    return;
  }
  app.innerHTML = `
    <h1>${UI.esc(project)} · 场景设计</h1>
    <div class="card">${data.intro_html}</div>
    <div id="sceneList"></div>
  `;
  const listEl = document.getElementById('sceneList');
  data.scenes.forEach((sec) => {
    const block = document.createElement('div');
    block.className = 'figure-block';
    block.innerHTML = `<h2>${UI.esc(sec.title)}</h2><div class="sec-mount"></div><div class="jobs-mount"></div>`;
    listEl.appendChild(block);
    UI.mountEditableSection(block.querySelector('.sec-mount'), {
      text: sec.body,
      html: sec.html,
      onSave: (newText) => API.patchScene(project, sec.title, newText),
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
