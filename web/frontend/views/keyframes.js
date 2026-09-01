window.Views = window.Views || {};

function padNum(n, width) {
  return String(n).trim().padStart(width, '0');
}

Views.keyframes = async function keyframes(app, project, ep) {
  const epList = await API.episodeList(project);
  const episodes = epList.episodes;
  if (!episodes.length) {
    app.innerHTML = '<div class="empty-hint">这个项目还没有分镜表，也就没有关键帧。</div>';
    return;
  }
  const currentEp = episodes.includes(ep) ? ep : episodes[0];

  app.innerHTML = `
    <h1>${UI.esc(project)} · 关键帧</h1>
    <div class="pill-tabs">${episodes.map((n) => `<a href="#/p/${encodeURIComponent(project)}/keyframes/${n}" class="${n === currentEp ? 'active' : ''}">第${n}集</a>`).join('')}</div>
    <div id="kfBody"></div>
  `;
  const body = document.getElementById('kfBody');
  const data = await API.keyframes(project, currentEp);

  if (!data.exists) {
    body.innerHTML = '<div class="empty-hint">这一集还没有生成关键帧。</div>';
    return;
  }
  if (!data.rows.length) {
    body.innerHTML = '<div class="empty-hint">这一集的关键帧清单是空的。</div>';
    return;
  }

  const matchedJobIds = new Set();
  data.rows.forEach((row) => {
    const shotNo = row['镜号'];
    const jobId = `ep${padNum(currentEp, 2)}_镜${padNum(shotNo, 2)}`;
    const block = document.createElement('div');
    block.className = 'figure-block';
    block.innerHTML = `
      <h2>镜 ${UI.esc(shotNo)} · ${UI.esc(row['场景'] || '')}</h2>
      <p>${UI.esc(row['对应画面描述'] || '')}</p>
      <p class="muted">出场人物：${UI.esc(row['出场人物'] || '')} · 分级：${UI.esc(row['分级'] || '')}</p>
      <div class="jobs-mount"></div>
    `;
    body.appendChild(block);
    const mount = block.querySelector('.jobs-mount');
    if (data.variants[jobId]) {
      matchedJobIds.add(jobId);
      UI.mountAssetJob(mount, project, jobId, data.variants[jobId], { kind: 'keyframe', episode: currentEp, baseDirHint: `keyframes/ep${padNum(currentEp, 2)}` });
    } else {
      mount.innerHTML = `<div class="muted">还没有生成这一镜的关键帧图。清单里登记的路径：${UI.esc(row['选中文件路径'] || '（无）')}</div>`;
    }
  });

  const leftover = Object.keys(data.variants).filter((jid) => !matchedJobIds.has(jid));
  if (leftover.length) {
    const block = document.createElement('div');
    block.className = 'figure-block';
    block.innerHTML = '<h2>其他关键帧（未在清单表里对上镜号）</h2><div class="jobs-mount"></div>';
    body.appendChild(block);
    const mount = block.querySelector('.jobs-mount');
    leftover.forEach((jobId) => {
      UI.mountAssetJob(mount, project, jobId, data.variants[jobId], { kind: 'keyframe', episode: currentEp, baseDirHint: `keyframes/ep${padNum(currentEp, 2)}` });
    });
  }
};
