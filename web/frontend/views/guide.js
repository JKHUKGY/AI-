window.Views = window.Views || {};

Views.guide = async function guide(app) {
  const { html } = await API.guide();
  app.innerHTML = `<div class="card">${html}</div>`;
};
