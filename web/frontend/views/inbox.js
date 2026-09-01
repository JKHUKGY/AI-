window.Views = window.Views || {};

Views.inbox = async function inbox(app) {
  const { projects } = await API.inbox();
  if (!projects.length) {
    app.innerHTML = '<h1>反馈汇总</h1><div class="empty-hint">目前没有待处理的留言或重新生成请求。</div>';
    return;
  }
  app.innerHTML = `<h1>反馈汇总</h1><p class="muted">跨项目列出所有还没处理的留言、和剧本家发起的重新生成请求。</p>` + projects.map((p) => `
    <div class="card">
      <h3><a href="#/p/${encodeURIComponent(p.project)}/characters">${UI.esc(p.project)}</a></h3>
      ${p.comments.map((c) => `
        <div class="inbox-item">
          <div class="muted">${UI.esc(describeTarget(c.target))} · ${UI.esc(c.author || '剧本家')} · ${UI.esc(c.created_at || '')}</div>
          <div>${UI.esc(c.text)}</div>
        </div>
      `).join('')}
      ${p.regen_jobs.map((j) => `
        <div class="inbox-item">
          <div class="muted">重新生成请求 · 状态: ${UI.esc(j.status)} · ${UI.esc(j.requested_at || '')}</div>
          <div>${UI.esc(describeTarget(j.target))}${j.note ? ' — ' + UI.esc(j.note) : ''}</div>
        </div>
      `).join('')}
      ${(!p.comments.length && !p.regen_jobs.length) ? '<div class="muted">无</div>' : ''}
    </div>
  `).join('');
};

function describeTarget(t) {
  if (!t) return '';
  if (t.type === 'shot') return `第${t.episode}集 · 镜${t.shot_no}`;
  if (t.type === 'image') return `图片 ${t.job_id} / ${t.file}`;
  if (t.type === 'asset' || t.type === 'character' || t.type === 'scene') return `资产 ${t.job_id}`;
  if (t.type === 'keyframe') return `关键帧 ${t.job_id}（第${t.episode}集）`;
  if (t.type === 'video') return `第${t.episode}集 · 镜${t.shot_no} 视频`;
  return JSON.stringify(t);
}
