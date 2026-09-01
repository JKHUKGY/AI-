const UI = (() => {
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function toast(msg, kind = 'info') {
    const bar = document.createElement('div');
    bar.className = `notice ${kind}`;
    bar.textContent = msg;
    Object.assign(bar.style, {
      position: 'fixed', top: '64px', right: '20px', zIndex: 999,
      maxWidth: '360px', boxShadow: '0 4px 16px rgba(0,0,0,.15)',
    });
    document.body.appendChild(bar);
    setTimeout(() => bar.remove(), 3800);
  }

  async function guarded(fn) {
    try {
      return await fn();
    } catch (e) {
      toast(e.message || String(e), 'error');
      throw e;
    }
  }

  function targetKey(t) {
    return JSON.stringify(t, Object.keys(t).sort());
  }

  function mountComments(container, project, target, allComments) {
    const key = targetKey(target);
    const related = allComments.filter((c) => targetKey(c.target) === key);
    const wrap = document.createElement('div');
    wrap.innerHTML = `
      <div class="comment-list"></div>
      <div class="comment-form">
        <input type="text" placeholder="留一条意见…">
        <button class="small send-btn">发送</button>
      </div>
    `;
    const list = wrap.querySelector('.comment-list');

    function renderList() {
      list.innerHTML = related.map((c) => `
        <div class="comment ${c.resolved ? 'resolved' : ''}" data-id="${esc(c.id)}">
          <div class="meta">${esc(c.author || '剧本家')} · ${esc(c.created_at || '')}${c.resolved ? ' · 已处理' : ''}</div>
          <div class="text">${esc(c.text)}</div>
          ${!c.resolved ? '<button class="small resolve-btn">标记已处理</button>' : ''}
        </div>
      `).join('') || '<div class="muted">暂无留言</div>';
      list.querySelectorAll('.resolve-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = btn.closest('.comment').dataset.id;
          await guarded(() => API.resolveComment(project, id));
          const c = related.find((x) => x.id === id);
          if (c) c.resolved = true;
          renderList();
        });
      });
    }
    renderList();

    const input = wrap.querySelector('input');
    const sendBtn = wrap.querySelector('.send-btn');
    async function send() {
      const text = input.value.trim();
      if (!text) return;
      const { comment } = await guarded(() => API.addComment(project, target, text));
      related.push(comment);
      input.value = '';
      renderList();
    }
    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });

    container.appendChild(wrap);
  }

  function openLightbox(project, jobId, relPath, fname, isSelected) {
    const overlay = document.createElement('div');
    overlay.className = 'lightbox';
    overlay.innerHTML = `
      <div class="lightbox-panel">
        <img src="${API.mediaUrl(relPath)}" alt="${esc(fname)}">
        <div class="muted">${esc(fname)}</div>
        <div class="lightbox-actions">
          <button class="select-btn primary small">${isSelected ? '已入选 ✓' : '标记为入选'}</button>
          <button class="close-btn small">关闭</button>
        </div>
        <div class="comments-mount"></div>
      </div>
    `;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector('.close-btn').addEventListener('click', () => overlay.remove());
    overlay.querySelector('.select-btn').addEventListener('click', async (e) => {
      await guarded(() => API.select(project, jobId, fname));
      e.currentTarget.textContent = '已入选 ✓';
      toast('已标记入选，供 Claude 下次核对时参考');
    });
    API.comments(project).then(({ comments }) => {
      mountComments(overlay.querySelector('.comments-mount'), project, { type: 'image', job_id: jobId, file: fname }, comments);
    }).catch(() => {});
    document.body.appendChild(overlay);
  }

  async function pollRegenerate(project, token, statusBox, grid, jobId, refPathForNaming) {
    for (let i = 0; i < 90; i += 1) {
      await new Promise((r) => setTimeout(r, 4000));
      let st;
      try {
        st = await API.regenerateStatus(project, token);
      } catch (e) {
        statusBox.textContent = '查询失败: ' + e.message;
        return;
      }
      statusBox.textContent = `状态: ${st.status}\n` + (st.log_tail || '').slice(-800);
      if (st.status !== 'running') {
        if (st.status === 'done' && st.new_files && st.new_files.length) {
          st.new_files.forEach((fname) => {
            const relPath = refPathForNaming.replace(/[^/]+$/, fname);
            const card = document.createElement('div');
            card.className = 'img-card';
            card.innerHTML = `<img loading="lazy" src="${API.mediaUrl(relPath)}">`;
            card.addEventListener('click', () => openLightbox(project, jobId, relPath, fname, false));
            grid.appendChild(card);
          });
          statusBox.textContent += `\n\n已生成 ${st.new_files.length} 张新图，已加入下方图库，点开可以标记入选或留言。`;
        } else if (st.status === 'failed') {
          statusBox.textContent += '\n\n生成失败，可以看看上面的日志或换个提示词再试。';
        }
        return;
      }
    }
    statusBox.textContent += '\n\n(轮询超时，任务可能仍在后台继续跑，稍后刷新页面查看新图)';
  }

  function mountAssetJob(container, project, jobId, jobData, opts) {
    const block = document.createElement('div');
    block.className = 'job-block';
    block.innerHTML = `
      <div class="job-title">
        <span>${esc(jobId)}</span>
        <button class="small regen-toggle">重新生成…</button>
      </div>
      <div class="img-grid"></div>
      <div class="regen-panel" hidden></div>
    `;
    const grid = block.querySelector('.img-grid');
    (jobData.files || []).forEach((relPath) => {
      const fname = relPath.split('/').pop();
      const isSelected = jobData.selected === fname;
      const card = document.createElement('div');
      card.className = 'img-card' + (isSelected ? ' selected' : '');
      card.innerHTML = `<img loading="lazy" src="${API.mediaUrl(relPath)}">` + (isSelected ? '<span class="mark">入选</span>' : '');
      card.addEventListener('click', () => openLightbox(project, jobId, relPath, fname, isSelected));
      grid.appendChild(card);
    });

    const regenPanel = block.querySelector('.regen-panel');
    block.querySelector('.regen-toggle').addEventListener('click', () => {
      regenPanel.hidden = !regenPanel.hidden;
      if (!regenPanel.hidden && !regenPanel.dataset.built) {
        regenPanel.dataset.built = '1';
        regenPanel.innerHTML = `
          <div class="regen-form">
            <div class="muted">留空提示词会自动复用这个角色/场景上一次生成时用的提示词，只改张数也可以。默认还会自动复用上一次生成这个 job 时用过的参考图（保证同一张脸/同一个场景），取消下面的勾选可以改成纯文字生成。</div>
            <textarea placeholder="要改提示词就在这里写完整版本…"></textarea>
            <label class="regen-refs-toggle"><input type="checkbox" checked> 复用上一次的参考图（保持人物/场景一致性）</label>
            <div class="toolbar">
              <label>生成张数 <input type="number" min="1" max="6" value="2" style="width:52px"></label>
              <button class="primary small go-regen">开始生成</button>
            </div>
            <div class="regen-used-refs" hidden></div>
            <div class="regen-status" hidden></div>
          </div>
        `;
        regenPanel.querySelector('.go-regen').addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          btn.disabled = true;
          const refsBox = regenPanel.querySelector('.regen-used-refs');
          const statusBox = regenPanel.querySelector('.regen-status');
          refsBox.hidden = true;
          refsBox.innerHTML = '';
          statusBox.hidden = false;
          statusBox.textContent = '已提交，正在生成…（免费本机生成，通常 1-3 分钟一张，请不要关闭页面）';
          try {
            const prompt = regenPanel.querySelector('textarea').value.trim();
            const count = Number(regenPanel.querySelector('input[type=number]').value) || 2;
            const reuseRefs = regenPanel.querySelector('.regen-refs-toggle input').checked;
            const body = { job_id: jobId, kind: opts.kind, count };
            if (prompt) body.prompt = prompt;
            if (opts.episode) body.episode = opts.episode;
            if (!reuseRefs) body.ref_images = [];
            const { token, used_ref_images } = await guarded(() => API.regenerate(project, body));
            if (used_ref_images && used_ref_images.length) {
              refsBox.hidden = false;
              refsBox.innerHTML = '<div class="muted">本次使用的参考图（保证一致性）：</div><div class="regen-ref-thumbs"></div>';
              const thumbs = refsBox.querySelector('.regen-ref-thumbs');
              used_ref_images.forEach((relPath) => {
                const img = document.createElement('img');
                img.src = API.mediaUrl(relPath);
                thumbs.appendChild(img);
              });
            }
            const refPath = (jobData.files && jobData.files[0]) || `${project}/${opts.baseDirHint}/${jobId}/${jobId}_00.png`;
            await pollRegenerate(project, token, statusBox, grid, jobId, refPath);
          } catch (err) {
            statusBox.textContent = '失败: ' + err.message;
          } finally {
            btn.disabled = false;
          }
        });
      }
    });

    container.appendChild(block);
  }

  function openCommentPanel(project, target, title) {
    const overlay = document.createElement('div');
    overlay.className = 'lightbox';
    overlay.innerHTML = `
      <div class="lightbox-panel">
        <h3 style="margin-top:0">${esc(title)}</h3>
        <div class="comments-mount"></div>
        <div class="lightbox-actions"><button class="close-btn small">关闭</button></div>
      </div>
    `;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    overlay.querySelector('.close-btn').addEventListener('click', () => overlay.remove());
    API.comments(project).then(({ comments }) => {
      mountComments(overlay.querySelector('.comments-mount'), project, target, comments);
    }).catch(() => {});
    document.body.appendChild(overlay);
  }

  function gradeClass(grade) {
    const g = (grade || '').trim().toUpperCase();
    return ['S', 'A', 'B', 'C'].includes(g) ? `grade-${g}` : '';
  }

  return { esc, toast, guarded, mountComments, mountAssetJob, openLightbox, openCommentPanel, gradeClass, targetKey };
})();
