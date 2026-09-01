window.Views = window.Views || {};

Views.home = async function home(app) {
  const { projects } = await API.projects();
  app.innerHTML = `
    <h1>选择一个项目</h1>
    <p class="muted">第一次来先看看<a href="#/guide">使用指南</a>，了解每一步该看什么、该怎么留意见。</p>
    <div class="grid-cards">
      ${projects.map((p) => `
        <a class="project-card card" href="#/p/${encodeURIComponent(p.name)}/characters">
          <h3>${UI.esc(p.name)}</h3>
          <div class="muted">${p.episodes.length ? `共 ${p.episodes.length} 集分镜表` : '分镜表待补充'}</div>
          <div class="badge-row">
            <span class="badge ${p.has_storyboard ? 'on' : ''}">分镜表</span>
            <span class="badge ${p.has_assets ? 'on' : ''}">人物/场景图</span>
            <span class="badge ${p.has_keyframes ? 'on' : ''}">关键帧</span>
            <span class="badge ${p.has_videos ? 'on' : ''}">视频</span>
          </div>
        </a>
      `).join('') || '<div class="empty-hint">还没有项目。项目会出现在 output/ 目录下，让 Claude 先跑一遍分镜/出图流程。</div>'}
    </div>
  `;
};
