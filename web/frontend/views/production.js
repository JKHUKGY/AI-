window.Views = window.Views || {};

Views.production = async function(app, selectedProject) {
  const [gpu, result] = await Promise.all([API.control('GET','/api/gpu'), API.projects()]);
  const projects = result.projects;
  const canConfigure = currentUser?.is_admin;
  const videoAllowed = gpu.video_allowed !== false;
  app.innerHTML = `<h1>租显卡 / 生成视频</h1>
    <p>先查看视频任务和服务状态，再租用显卡并确认生成。开卡会花费真实费用。</p>
    <div class="production-status">
      <section class="card"><h2>1. 视频任务</h2><p>选择项目，进入分集页面查看待生成镜头。</p></section>
      <section class="card"><h2>2. 生成服务</h2><p>${gpu.h3_paused?'视频生成通道已暂时停用。':gpu.video_ready?'视频生成服务已启用。':'视频生成服务尚未配置，暂时无法生成视频。'}</p>
        ${!videoAllowed?'<p>当前账号尚未获准生成视频，请联系管理员。</p>':''}
        ${!gpu.video_ready&&canConfigure?'<a href="#/admin">配置视频生成服务</a>':''}</section>
      <section class="card"><h2>3. 租用显卡</h2><p>${!gpu.enabled?'网站租卡尚未启用。':!gpu.allowed?'当前账号尚未获准租卡，请联系管理员。':!gpu.mail_configured?'通知邮箱尚未配置，暂不能开卡。':'租卡入口已开放；先预览费用，再确认启动。'}</p>
        <a class="action-link" href="#/gpu">租用 / 关闭显卡</a></section>
    </div>
    <section class="card"><h2>选择项目继续</h2>
      ${projects.length?`<div class="control-form"><label>项目<select class="production-project">${projects.map(p=>`<option value="${UI.esc(p.name)}">${UI.esc(p.name)}</option>`).join('')}</select></label></div><div class="production-project-detail" role="status"></div>`:'<p>当前没有可访问的项目。请先创建项目或联系管理员分配项目权限。</p><a href="#/">返回项目首页</a>'}
    </section>
    <p class="muted">成功生成图片每张 10 点、视频每条 300 点，失败退还未完成部分。显卡费用另计；连续空闲 10 分钟自动关闭，也可随时手动关闭。</p>`;
  const select = app.querySelector('.production-project');
  if (!select) return;
  if (projects.some(p=>p.name===selectedProject)) select.value=selectedProject;
  let sequence=0;
  async function showProject() {
    const request = ++sequence;
    const name=select.value, p=encodeURIComponent(name);
    const detail=app.querySelector('.production-project-detail');
    detail.innerHTML='<p>正在读取分集…</p>';
    try {
      const list=await API.episodeList(name);
      if(request!==sequence || !detail.isConnected)return;
      const episodes=[...new Set([...(list.episodes||[]),...(list.video_episodes||[])])].sort((a,b)=>a-b);
      detail.innerHTML=`<p>${episodes.length?'选择一集查看可生成任务和已有视频。':'这个项目还没有分集，请先准备分镜和关键帧。'}</p>
        <div class="toolbar">${episodes.map(ep=>`<a class="action-link" href="#/p/${p}/videos/${ep}">第 ${ep} 集 · 视频任务</a>`).join('')||`<a class="action-link" href="#/p/${p}/episodes/1">准备分镜</a><a class="action-link" href="#/p/${p}/videos/1">查看视频准备情况</a>`}</div>
        <div class="toolbar"><a class="action-link" href="#/gpu?project=${p}">为此项目租卡 / 查看显卡</a><a href="#/p/${p}/keyframes/${episodes[0]||1}">查看关键帧</a></div>`;
    } catch (error) {
      if(request===sequence&&detail.isConnected)detail.textContent='读取分集失败：'+error.message;
    }
  }
  select.onchange=showProject;
  await showProject();
};
