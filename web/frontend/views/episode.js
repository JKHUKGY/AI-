window.Views = window.Views || {};

Views.episode = async function episode(app, project, ep) {
  const epList = await API.episodeList(project);
  const episodes = epList.episodes;
  if (!episodes.length) {
    app.innerHTML = '<h1>分镜表</h1><div class="manage-episodes"></div><div class="empty-hint">还没有分镜表，新增分集后可以添加镜头。</div>';
    ContentEditor.toolbar(app.querySelector('.manage-episodes'),project,'episode');
    return;
  }
  const currentEp = episodes.includes(ep) ? ep : episodes[0];

  app.innerHTML = `
    <h1>${UI.esc(project)} · 分镜表</h1>
    <div class="manage-episodes"></div>
    <div class="pill-tabs" id="epTabs">
      ${episodes.map((n) => `<a href="#/p/${encodeURIComponent(project)}/episodes/${n}" class="${n === currentEp ? 'active' : ''}">第${n}集</a>`).join('')}
    </div>
    <div id="epMeta"></div>
    <div class="toolbar">
      <label><input type="checkbox" id="onlySA"> 只看 S/A 级关键镜头</label>
      <span class="muted">单元格点一下即可直接改文字，改完点别处自动保存；每一行右侧可以留言。</span>
    </div>
    <div class="table-scroll"><table class="shot-table"><thead></thead><tbody id="shotBody"></tbody></table></div>
    <div id="epTail"></div>
  `;

  const data = await API.episode(project, currentEp);
  ContentEditor.toolbar(app.querySelector('.manage-episodes'),project,'episode');
  ContentEditor.toolbar(app.querySelector('.manage-episodes'),project,'shot',{episode:currentEp,header:data.header});
  const deleteEpisode = document.createElement('button'); deleteEpisode.className = 'small delete-episode'; deleteEpisode.textContent = `删除第 ${currentEp} 集`;
  deleteEpisode.addEventListener('click',() => ContentEditor.remove(project,{kind:'episode',episode:currentEp}));
  app.querySelector('.manage-episodes').appendChild(deleteEpisode);
  document.getElementById('epMeta').innerHTML = `<div class="card">${data.meta_html}</div>`;
  document.getElementById('epTail').innerHTML = `<div class="card">${data.tail_html}</div>`;

  const header = data.header;
  const gradeIdx = header.indexOf('分级');
  document.querySelector('.shot-table thead').innerHTML = `<tr>${header.map((h) => `<th>${UI.esc(h)}</th>`).join('')}<th>操作</th></tr>`;

  const tbody = document.getElementById('shotBody');
  function renderRows(rows) {
    tbody.innerHTML = '';
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      const grade = gradeIdx >= 0 ? row['分级'] : '';
      tr.className = UI.gradeClass(grade);
      header.forEach((col) => {
        const td = document.createElement('td');
        td.textContent = row[col];
        td.dataset.field = col;
        if (col === '分级') td.className = 'grade-cell';
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
              await API.patchShot(project, currentEp, row['镜号'], { [col]: newVal });
              row[col] = newVal;
              UI.toast(`第${row['镜号']}镜「${col}」已保存`);
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
      const commentTd = document.createElement('td');
      commentTd.innerHTML = '<button class="small">留言</button>';
      commentTd.querySelector('button').addEventListener('click', () => {
        UI.openCommentPanel(project, { type: 'shot', episode: currentEp, shot_no: row['镜号'] }, `第${currentEp}集 · 镜${row['镜号']}`);
      });
      const insert = document.createElement('button'); insert.className = 'small insert-shot'; insert.textContent = '在后面插入';
      insert.addEventListener('click',() => ContentEditor.add(project,'shot',currentEp,header,row['镜号'])); commentTd.appendChild(insert);
      ContentEditor.deleteButton(commentTd,project,{kind:'shot',episode:currentEp,shot:row['镜号']});
      tr.appendChild(commentTd);
      tbody.appendChild(tr);
    });
  }

  renderRows(data.rows);
  document.getElementById('onlySA').addEventListener('change', (e) => {
    const rows = e.target.checked
      ? data.rows.filter((r) => ['S', 'A'].includes((r['分级'] || '').trim().toUpperCase()))
      : data.rows;
    renderRows(rows);
  });
};
