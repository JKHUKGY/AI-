window.Views = window.Views || {};

function padNum(n, width) {
  return String(n).trim().padStart(width, '0');
}

Views.keyframes = async function keyframes(app, project, ep) {
  const epList = await API.episodeList(project);
  // 有些项目关键帧已经出了、分镜表却不在 storyboard/ 下（早期样例），
  // 所以集数要取"分镜表 ∪ 关键帧目录"，否则已有的图会被整集藏起来。
  const episodes = Array.from(new Set([
    ...(epList.episodes || []), ...(epList.keyframe_episodes || []),
  ])).sort((a, b) => a - b);
  if (!episodes.length) {
    app.innerHTML = '<div class="empty-hint">这个项目还没有分镜表，也还没有生成任何关键帧。</div>';
    return;
  }
  const currentEp = episodes.includes(ep) ? ep : episodes[0];

  app.innerHTML = `
    <h1>${UI.esc(project)} · 关键帧</h1>
    <div class="pill-tabs">${episodes.map((n) => `<a href="#/p/${encodeURIComponent(project)}/keyframes/${n}" class="${n === currentEp ? 'active' : ''}">第${n}集</a>`).join('')}</div>
    <div id="kfBody"></div>
  `;
  const body = document.getElementById('kfBody');
  const [data, commentData] = await Promise.all([
    API.keyframes(project, currentEp),
    API.comments(project).catch(() => ({ comments: [] })),
  ]);

  const baseDirHint = `keyframes/ep${padNum(currentEp, 2)}`;
  const opts = { kind: 'keyframe', episode: currentEp, baseDirHint };

  // 每张图上的留言数：审片时最想先看"哪几镜已经被人提过意见"，所以要在
  // 卡片上直接标出来，而不是逐张点开才知道。
  const commentCount = {};
  (commentData.comments || []).forEach((c) => {
    const t = c.target || {};
    if (t.type === 'image' && t.job_id) {
      commentCount[t.job_id] = (commentCount[t.job_id] || 0) + (c.resolved ? 0 : 1);
    }
  });

  // 没有 keyframes.md 时，用磁盘上的图目录本身当"镜"，至少让图能被看到。
  let shots = data.shots || [];
  if (!shots.length) {
    shots = Object.keys(data.orphan_jobs || data.variants || {}).sort().map((jobId) => {
      const job = (data.orphan_jobs || data.variants)[jobId];
      const m = /镜(\d+)/.exec(jobId);
      return {
        shot_no: m ? m[1] : jobId, shot_num: m ? Number(m[1]) : 0, job_id: jobId,
        scene: '', camera: '', characters: '', description: '', grade: '',
        notes: [], files: job.files || [], selected: job.selected, listed_file: '',
      };
    });
  }

  if (!shots.length) {
    body.innerHTML = '<div class="empty-hint">这一集还没有关键帧：既没有 keyframes.md 清单，也没有生成出来的图。</div>';
    return;
  }

  const withImg = shots.filter((s) => s.files.length).length;
  const commented = shots.filter((s) => commentCount[s.job_id]).length;

  body.innerHTML = `
    ${data.exists ? '' : '<div class="notice warn">这一集还没有 keyframes.md 清单，下面是直接按图片目录列出来的，所以没有镜头描述。</div>'}
    <div class="kf-toolbar">
      <div class="kf-stats">
        共 <b>${shots.length}</b> 镜 · 已出图 <b>${withImg}</b> · 待出图 <b>${shots.length - withImg}</b>${commented ? ` · 有未处理留言 <b>${commented}</b>` : ''}
      </div>
      <div class="kf-filters">
        <button class="chip active" data-filter="all">全部</button>
        <button class="chip" data-filter="todo">待出图</button>
        <button class="chip" data-filter="multi">有多张备选</button>
        <button class="chip" data-filter="commented">有留言</button>
        <span class="chip-sep"></span>
        ${['S', 'A', 'B', 'C'].map((g) => `<button class="chip chip-grade grade-${g}" data-filter="grade:${g}">${g}</button>`).join('')}
      </div>
    </div>
    <div class="kf-grid" id="kfGrid"></div>
  `;

  const grid = document.getElementById('kfGrid');

  shots.forEach((shot) => {
    const files = shot.files.slice();
    // 展示哪一张：优先剧本家标记的入选图，其次清单里登记的那张，最后第一张。
    let shownIdx = Math.max(0, files.findIndex((f) => f.split('/').pop() === (shot.selected || shot.listed_file)));

    const card = document.createElement('article');
    card.className = 'kf-card';
    card.dataset.grade = (shot.grade || '').trim().toUpperCase();
    card.dataset.hasImg = files.length ? '1' : '0';
    card.dataset.variants = String(files.length);
    card.dataset.comments = String(commentCount[shot.job_id] || 0);

    const gradeCls = UI.gradeClass(shot.grade);
    const metaBits = [shot.scene, shot.camera, shot.characters].filter(Boolean);

    card.innerHTML = `
      <div class="kf-thumb ${files.length ? '' : 'empty'}">
        ${files.length
          ? '<img loading="lazy" alt="">'
          : '<div class="kf-empty-mark">还没出图<br><span class="muted">点下面「重新生成」可以现在生成</span></div>'}
        <span class="kf-no ${gradeCls}">镜${UI.esc(String(shot.shot_num || shot.shot_no))}${shot.grade ? ` · ${UI.esc(shot.grade)}` : ''}</span>
        ${files.length > 1 ? `<span class="kf-count">${files.length} 张备选</span>` : ''}
        ${commentCount[shot.job_id] ? `<span class="kf-comment-flag">${commentCount[shot.job_id]} 条留言</span>` : ''}
      </div>
      <div class="kf-body">
        <p class="kf-desc">${UI.esc(shot.description || '（清单里没写这一镜的画面描述）')}</p>
        ${metaBits.length ? `<div class="kf-meta">${metaBits.map((b) => UI.esc(b)).join(' · ')}</div>` : ''}
        ${shot.notes.length ? `<div class="kf-notes">${shot.notes.map((n) => `<div class="kf-note" title="${UI.esc(n.label)}：${UI.esc(n.value)}"><span>${UI.esc(n.label)}</span>${UI.esc(n.value)}</div>`).join('')}</div>` : ''}
        <div class="kf-variants"></div>
        <div class="kf-actions">
          <button class="small kf-open" ${files.length ? '' : 'disabled'}>看大图 / 挑图</button>
          <button class="small kf-comment">留言</button>
          <button class="small kf-regen">重新生成…</button>
        </div>
        <div class="regen-panel" hidden></div>
      </div>
    `;
    grid.appendChild(card);

    const varBox = card.querySelector('.kf-variants');
    const thumbBox = card.querySelector('.kf-thumb');

    function paint() {
      // 待出图的卡片一开始没有 <img>，是"重新生成"出图后才补上的，
      // 所以每次都重新取一次，不能在构建时抓一次就一直用。
      const imgEl = card.querySelector('.kf-thumb img');
      if (!files.length || !imgEl) return;
      imgEl.src = API.mediaUrl(files[shownIdx]);
      imgEl.alt = files[shownIdx].split('/').pop();
      thumbBox.classList.toggle('is-selected', files[shownIdx].split('/').pop() === shot.selected);
      // 多张备选时，缩略图条直接在卡片上切换，不必点开大图
      varBox.innerHTML = files.length > 1 ? files.map((f, i) => {
        const fname = f.split('/').pop();
        return `<button class="kf-var ${i === shownIdx ? 'on' : ''} ${fname === shot.selected ? 'picked' : ''}" data-i="${i}" title="${UI.esc(fname)}"><img loading="lazy" src="${API.mediaUrl(f)}"></button>`;
      }).join('') : '';
      varBox.querySelectorAll('.kf-var').forEach((b) => {
        b.addEventListener('click', () => { shownIdx = Number(b.dataset.i); paint(); });
      });
      const mark = card.querySelector('.kf-selected-mark');
      if (mark) mark.remove();
      if (shot.selected) {
        const s = document.createElement('span');
        s.className = 'kf-selected-mark';
        s.textContent = files[shownIdx].split('/').pop() === shot.selected ? '这张已入选' : '已入选别的备选';
        thumbBox.appendChild(s);
      }
    }
    paint();

    function open() {
      if (!files.length) return;
      UI.openLightbox(project, shot.job_id, {
        files,
        index: shownIdx,
        selected: shot.selected,
        caption: shot.description,
        meta: metaBits.join(' · '),
        onSelect: (fname) => { shot.selected = fname; paint(); },
      });
    }
    if (files.length) thumbBox.addEventListener('click', open);
    card.querySelector('.kf-open').addEventListener('click', open);

    card.querySelector('.kf-comment').addEventListener('click', () => {
      const fname = files.length ? files[shownIdx].split('/').pop() : '';
      UI.openCommentPanel(
        project,
        { type: 'image', job_id: shot.job_id, file: fname },
        `镜${shot.shot_num || shot.shot_no}${fname ? ` · ${fname}` : ''}`,
      );
    });

    const regenPanel = card.querySelector('.regen-panel');
    card.querySelector('.kf-regen').addEventListener('click', () => {
      regenPanel.hidden = !regenPanel.hidden;
      if (!regenPanel.hidden) {
        UI.attachRegenPanel(regenPanel, project, shot.job_id, { files }, opts, (relPath) => {
          files.push(relPath);
          shownIdx = files.length - 1;
          card.dataset.hasImg = '1';
          card.dataset.variants = String(files.length);
          const emptyMark = card.querySelector('.kf-empty-mark');
          if (emptyMark) {
            emptyMark.remove();
            thumbBox.classList.remove('empty');
            const img = document.createElement('img');
            img.loading = 'lazy';
            thumbBox.prepend(img);
            thumbBox.addEventListener('click', open);
            card.querySelector('.kf-open').disabled = false;
          }
          paint();
        });
      }
    });
  });

  // 过滤只切每张卡片的 hidden，不重建 DOM——重建会把已经展开的"重新生成"
  // 面板和正在跑的轮询一起丢掉。
  const chips = body.querySelectorAll('.kf-filters .chip');
  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chips.forEach((c) => c.classList.toggle('active', c === chip));
      const f = chip.dataset.filter;
      grid.querySelectorAll('.kf-card').forEach((c) => {
        let show = true;
        if (f === 'todo') show = c.dataset.hasImg === '0';
        else if (f === 'multi') show = Number(c.dataset.variants) > 1;
        else if (f === 'commented') show = Number(c.dataset.comments) > 0;
        else if (f.startsWith('grade:')) show = c.dataset.grade === f.slice(6);
        c.hidden = !show;
      });
    });
  });
};
