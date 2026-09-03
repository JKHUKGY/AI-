window.Views = window.Views || {};

Views.videos = async function videos(app, project, ep) {
  const epList = await API.episodeList(project);
  // 跟关键帧页同理：有视频产出但没有 storyboard/ep0X.md 的项目，集数要
  // 取"分镜表 ∪ 视频目录"，否则已经跑出来的片子会被整集藏起来。
  const episodes = Array.from(new Set([
    ...(epList.episodes || []), ...(epList.video_episodes || []),
  ])).sort((a, b) => a - b);
  if (!episodes.length) {
    app.innerHTML = '<div class="empty-hint">这个项目还没有分镜表，也还没有任何视频产出。</div>';
    return;
  }
  const currentEp = episodes.includes(ep) ? ep : episodes[0];

  app.innerHTML = `
    <h1>${UI.esc(project)} · 视频</h1>
    <div class="notice warn">
      视频生成大多要在可灵/即梦等平台网页手动提交，或者需要真的租显卡跑，
      这个页面的"请求重新生成"不会自动帮你跑视频，只会把你的意见记下来，
      由后续处理这一步的人决定要不要真的重新提交。
    </div>
    <div class="pill-tabs">${episodes.map((n) => `<a href="#/p/${encodeURIComponent(project)}/videos/${n}" class="${n === currentEp ? 'active' : ''}">第${n}集</a>`).join('')}</div>
    <div id="videoFiles"></div>
    <div id="videoTableWrap"></div>
  `;

  const data = await API.videos(project, currentEp);

  const filesWrap = document.getElementById('videoFiles');
  const fileKeys = Object.keys(data.video_files || {});
  if (fileKeys.length) {
    filesWrap.innerHTML = `<div class="card"><h3>已生成的视频文件</h3><div class="img-grid">${fileKeys.map((k) => `
      <div><video class="preview" controls preload="metadata" src="${API.mediaUrl(data.video_files[k])}"></video><div class="muted">${UI.esc(k)}</div></div>
    `).join('')}</div></div>`;
  }

  const tableWrap = document.getElementById('videoTableWrap');
  if (!data.exists) {
    tableWrap.innerHTML = '<div class="empty-hint">这一集还没有生成视频提交清单（video_jobs.md）。</div>';
    return;
  }
  if (!data.rows.length) {
    tableWrap.innerHTML = '<div class="empty-hint">这一集的视频清单是空的。</div>';
    return;
  }

  const header = data.header;
  const promptCol = header.find((h) => h.includes('正向提示词')) || '正向提示词';
  const statusCol = header.find((h) => h.includes('状态')) || '状态';

  tableWrap.innerHTML = `
    <div class="table-scroll"><table class="shot-table">
      <thead><tr>${header.map((h) => `<th>${UI.esc(h)}</th>`).join('')}<th>操作</th></tr></thead>
      <tbody id="videoBody"></tbody>
    </table></div>
  `;
  const tbody = document.getElementById('videoBody');

  data.rows.forEach((row) => {
    const tr = document.createElement('tr');
    header.forEach((col) => {
      const td = document.createElement('td');
      td.textContent = row[col];
      if (col !== '镜号') {
        td.classList.add('editable');
        td.contentEditable = 'false';
        td.addEventListener('click', () => {
          if (td.contentEditable === 'true') return;
          td.contentEditable = 'true';
          td.focus();
          document.execCommand('selectAll', false, null);
        });
        td.addEventListener('blur', async () => {
          td.contentEditable = 'false';
          const newVal = td.textContent.trim();
          if (newVal === row[col]) return;
          try {
            await API.patchVideoShot(project, currentEp, row['镜号'], { [col]: newVal });
            row[col] = newVal;
            UI.toast(`镜${row['镜号']}「${col}」已保存`);
          } catch (e) {
            td.textContent = row[col];
            UI.toast('保存失败: ' + e.message, 'error');
          }
        });
        td.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); td.blur(); }
          if (e.key === 'Escape') { td.textContent = row[col]; td.blur(); }
        });
      }
      tr.appendChild(td);
    });

    const opTd = document.createElement('td');
    opTd.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:4px">
        <button class="small copy-btn">复制提示词</button>
        <button class="small comment-btn">留言</button>
        <button class="small regen-btn">请求重新生成</button>
      </div>
    `;
    opTd.querySelector('.copy-btn').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(row[promptCol] || '');
        UI.toast('已复制正向提示词');
      } catch (e) {
        UI.toast('复制失败，请手动选中文字复制', 'error');
      }
    });
    opTd.querySelector('.comment-btn').addEventListener('click', () => {
      UI.openCommentPanel(project, { type: 'video', episode: currentEp, shot_no: row['镜号'] }, `第${currentEp}集 · 镜${row['镜号']} 视频`);
    });
    opTd.querySelector('.regen-btn').addEventListener('click', async () => {
      const note = prompt('说说这一镜想怎么改（会记录为待办，不会自动生成）：', '');
      if (note === null) return;
      try {
        await UI.guarded(() => API.requestVideoRegen(project, currentEp, row['镜号'], note));
        UI.toast('已记录，等待处理');
      } catch (e) { /* toast already shown */ }
    });
    tr.appendChild(opTd);
    tbody.appendChild(tr);
  });
};
