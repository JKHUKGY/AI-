window.Views = window.Views || {};

Views.styleBible = async function styleBible(app, project) {
  const data = await API.styleBible(project);
  if (!data.exists) {
    app.innerHTML = '<div class="empty-hint">这个项目还没有风格简报（style_bible.md）。</div>';
    return;
  }
  app.innerHTML = `
    <h1>${UI.esc(project)} · 风格与叙事基调简报</h1>
    <div class="card">${data.html}</div>
  `;
};
