window.Views = window.Views || {};

Views.guide = async function guide(app) {
  const { html } = await API.guide();
  app.innerHTML = `<section class="card production-entry"><h2>置顶 · 内置 ChatGPT 解释助手</h2><p>不清楚页面怎么用？点击下方按钮或右下角“使用帮助”，直接在网站内提问。</p><button class="open-help primary">打开内置解释助手</button></section><div class="card">${html}</div>`;
  app.querySelector('.open-help').onclick=()=>HelpUI.open();
};
