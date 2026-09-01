window.Views = window.Views || {};

Views.characters = async function characters(app, project) {
  const data = await API.characters(project);
  if (!data.exists) {
    app.innerHTML = '<div class="empty-hint">这个项目还没有人物设计文档（characters.md）。</div>';
    return;
  }
  app.innerHTML = `
    <h1>${UI.esc(project)} · 人物设计</h1>
    <div class="card">${data.intro_html}</div>
    <div id="charList"></div>
  `;
  const listEl = document.getElementById('charList');
  data.characters.forEach((sec) => {
    const block = document.createElement('div');
    block.className = 'figure-block';
    block.innerHTML = `<h2>${UI.esc(sec.title)}</h2>${sec.html}<div class="jobs-mount"></div>`;
    listEl.appendChild(block);
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
