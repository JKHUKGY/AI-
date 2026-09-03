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

  // opts: { files: [媒体相对路径], index, selected: 文件名, caption, meta, onSelect(fname) }
  // 只传一张图时退化成旧行为；传多张时可以在同一镜的备选之间左右翻，不用
  // 关掉再点开下一张——审片时"这一镜的三张里挑一张"是最高频的动作。
  function openLightbox(project, jobId, opts) {
    const files = opts.files && opts.files.length ? opts.files : [];
    if (!files.length) return;
    let idx = Math.max(0, Math.min(opts.index || 0, files.length - 1));
    let selected = opts.selected || null;

    const overlay = document.createElement('div');
    overlay.className = 'lightbox';
    overlay.innerHTML = `
      <div class="lightbox-panel">
        <div class="lightbox-stage">
          <button class="nav-btn prev" title="上一张 (←)" ${files.length > 1 ? '' : 'hidden'}>‹</button>
          <img alt="">
          <button class="nav-btn next" title="下一张 (→)" ${files.length > 1 ? '' : 'hidden'}>›</button>
        </div>
        ${opts.caption ? `<p class="lightbox-caption">${esc(opts.caption)}</p>` : ''}
        ${opts.meta ? `<div class="muted">${esc(opts.meta)}</div>` : ''}
        <div class="muted lightbox-fname"></div>
        <div class="lightbox-actions">
          <button class="select-btn primary small"></button>
          <button class="close-btn small">关闭</button>
        </div>
        <div class="comments-mount"></div>
      </div>
    `;
    const img = overlay.querySelector('img');
    const fnameBox = overlay.querySelector('.lightbox-fname');
    const selectBtn = overlay.querySelector('.select-btn');
    const commentsMount = overlay.querySelector('.comments-mount');
    let allComments = null;

    function currentName() {
      return files[idx].split('/').pop();
    }

    function paint() {
      const fname = currentName();
      img.src = API.mediaUrl(files[idx]);
      img.alt = fname;
      fnameBox.textContent = files.length > 1
        ? `${fname}（第 ${idx + 1} / ${files.length} 张备选）`
        : fname;
      selectBtn.textContent = selected === fname ? '已入选 ✓' : '把这张定为入选';
      // 留言是挂在具体某一张图上的，翻页要跟着换
      commentsMount.innerHTML = '';
      if (allComments) {
        mountComments(commentsMount, project, { type: 'image', job_id: jobId, file: fname }, allComments);
      }
    }

    function go(step) {
      if (files.length < 2) return;
      idx = (idx + step + files.length) % files.length;
      paint();
    }

    function onKey(e) {
      if (e.key === 'Escape') close();
      else if (e.key === 'ArrowLeft') go(-1);
      else if (e.key === 'ArrowRight') go(1);
    }
    function close() {
      document.removeEventListener('keydown', onKey);
      overlay.remove();
    }

    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    overlay.querySelector('.close-btn').addEventListener('click', close);
    overlay.querySelector('.prev').addEventListener('click', () => go(-1));
    overlay.querySelector('.next').addEventListener('click', () => go(1));
    document.addEventListener('keydown', onKey);

    selectBtn.addEventListener('click', async () => {
      const fname = currentName();
      await guarded(() => API.select(project, jobId, fname));
      selected = fname;
      selectBtn.textContent = '已入选 ✓';
      toast('已标记入选，供 Claude 下次核对时参考');
      if (opts.onSelect) opts.onSelect(fname, files[idx]);
    });

    API.comments(project).then(({ comments }) => {
      allComments = comments;
      paint();
    }).catch(() => {});

    paint();
    document.body.appendChild(overlay);
  }

  async function pollRegenerate(project, token, statusBox, onNewFile, refPathForNaming) {
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
            onNewFile(refPathForNaming.replace(/[^/]+$/, fname), fname);
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

  // 把"重新生成"面板（提示词编辑 / AI 改写 / 参考图复用 / 提交+轮询）做成
  // 可复用的一块：立绘、场景图、关键帧卡片都挂同一份逻辑，只是新图落到哪里
  // 由调用方通过 onNewFile 决定。
  function attachRegenPanel(regenPanel, project, jobId, jobData, opts, onNewFile) {
      if (!regenPanel.dataset.built) {
        regenPanel.dataset.built = '1';
        regenPanel.innerHTML = `
          <div class="regen-form">
            <div class="muted">下面是这个角色/场景上一次生成时实际用的提示词，可以直接在里面改，改完点"开始生成"就会用你改过的版本重新生成，不改也可以直接生成。默认还会自动复用上一次生成这个 job 时用过的参考图（保证同一张脸/同一个场景），取消下面的勾选可以改成纯文字生成。</div>
            <div class="ai-rewrite-row">
              <input type="text" class="ai-instruction" placeholder="不想自己改提示词？口语化说说想怎么改（比如"头发剪短一点，表情更冷艳"），点右边按钮让 AI 帮你改写">
              <button class="small ai-rewrite-btn">AI 改写</button>
            </div>
            <textarea placeholder="加载上一次的提示词中…" disabled></textarea>
            <label class="regen-refs-toggle"><input type="checkbox" checked> 复用上一次的参考图（保持人物/场景一致性）</label>
            <div class="toolbar">
              <label>生成张数 <input type="number" min="1" max="6" value="2" style="width:52px"></label>
              <button class="primary small go-regen">开始生成</button>
            </div>
            <div class="regen-used-refs" hidden></div>
            <div class="regen-status" hidden></div>
          </div>
        `;
        const textarea = regenPanel.querySelector('textarea');
        API.lastPrompt(project, jobId, opts.kind, opts.episode).then(({ prompt }) => {
          textarea.value = prompt || '';
          textarea.placeholder = prompt ? '' : '没有找到上一次的提示词，手动写一个完整版本…';
        }).catch((e) => {
          textarea.placeholder = '加载上一次的提示词失败（' + e.message + '），可以手动写一个完整版本…';
        }).finally(() => {
          textarea.disabled = false;
        });

        regenPanel.querySelector('.ai-rewrite-btn').addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          const instrInput = regenPanel.querySelector('.ai-instruction');
          const instruction = instrInput.value.trim();
          if (!instruction) {
            toast('先写一句想怎么改，再点 AI 改写', 'error');
            return;
          }
          const before = textarea.value;
          btn.disabled = true;
          textarea.disabled = true;
          const savedPlaceholder = textarea.placeholder;
          textarea.placeholder = 'AI 改写中，通常 10-30 秒…';
          try {
            const { prompt } = await guarded(() => API.aiRewritePrompt(project, {
              job_id: jobId, kind: opts.kind, episode: opts.episode,
              instruction, current_prompt: before,
            }));
            textarea.value = prompt;
            instrInput.value = '';
            toast('AI 已改写，还可以在文本框里继续手动微调');
          } catch (err) {
            textarea.value = before;
          } finally {
            textarea.placeholder = savedPlaceholder;
            textarea.disabled = false;
            btn.disabled = false;
          }
        });

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
            await pollRegenerate(project, token, statusBox, onNewFile, refPath);
          } catch (err) {
            statusBox.textContent = '失败: ' + err.message;
          } finally {
            btn.disabled = false;
          }
        });
      }
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
    const files = (jobData.files || []).slice();

    function addCard(relPath, i) {
      const fname = relPath.split('/').pop();
      const isSelected = jobData.selected === fname;
      const card = document.createElement('div');
      card.className = 'img-card' + (isSelected ? ' selected' : '');
      card.innerHTML = `<img loading="lazy" src="${API.mediaUrl(relPath)}">` + (isSelected ? '<span class="mark">入选</span>' : '');
      card.addEventListener('click', () => openLightbox(project, jobId, {
        files, index: i, selected: jobData.selected,
      }));
      grid.appendChild(card);
    }
    files.forEach(addCard);

    const regenPanel = block.querySelector('.regen-panel');
    block.querySelector('.regen-toggle').addEventListener('click', () => {
      regenPanel.hidden = !regenPanel.hidden;
      if (!regenPanel.hidden) {
        attachRegenPanel(regenPanel, project, jobId, jobData, opts, (relPath) => {
          files.push(relPath);
          addCard(relPath, files.length - 1);
        });
      }
    });

    container.appendChild(block);
  }

  // "提示词正文"标题后面不一定紧跟代码块——有的项目会在标题里带括注
  // （比如"提示词正文（正面立绘，伪装期）"），所以标题和"```"之间不能只
  // 按空白字符匹配，要允许中间有任意文字，非贪婪找最近的一个代码块。
  const _PROMPT_BLOCK_RE = /提示词正文[\s\S]*?```\n?([\s\S]*?)```/;

  function extractPromptBlock(text) {
    const m = _PROMPT_BLOCK_RE.exec(text || '');
    return m ? m[1].trim() : null;
  }

  function mountRegenShortcut(container, project, jobs, opts, prompt) {
    container.innerHTML = '';
    const jobIds = Object.keys(jobs || {});
    if (!jobIds.length) return;
    const wrap = document.createElement('div');
    wrap.className = 'post-save-regen';
    wrap.innerHTML = `
      <div class="muted">检测到"提示词正文"有更新，要不要用它重新生成对应的图？（免费本机生成，1-3 分钟一张）</div>
      <div class="post-save-jobs"></div>
    `;
    const jobsBox = wrap.querySelector('.post-save-jobs');
    jobIds.forEach((jobId) => {
      const row = document.createElement('div');
      row.className = 'post-save-job-row';
      row.innerHTML = `
        <span class="job-name">${esc(jobId)}</span>
        <label>张数 <input type="number" min="1" max="6" value="2" style="width:48px"></label>
        <button class="small go-regen">重新生成</button>
        <div class="regen-status" hidden></div>
        <div class="img-grid"></div>
      `;
      jobsBox.appendChild(row);
      row.querySelector('.go-regen').addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        const statusBox = row.querySelector('.regen-status');
        const grid = row.querySelector('.img-grid');
        statusBox.hidden = false;
        try {
          const count = Number(row.querySelector('input[type=number]').value) || 2;
          const body = { job_id: jobId, kind: opts.kind, count, prompt };
          if (opts.episode) body.episode = opts.episode;
          const { token } = await guarded(() => API.regenerate(project, body));
          const refPath = (jobs[jobId].files && jobs[jobId].files[0])
            || `${project}/${opts.baseDirHint}/${jobId}/${jobId}_00.png`;
          const shown = [];
          await pollRegenerate(project, token, statusBox, (relPath) => {
            shown.push(relPath);
            const card = document.createElement('div');
            card.className = 'img-card';
            card.innerHTML = `<img loading="lazy" src="${API.mediaUrl(relPath)}">`;
            card.addEventListener('click', () => openLightbox(project, jobId, {
              files: shown, index: shown.indexOf(relPath),
            }));
            grid.appendChild(card);
          }, refPath);
        } catch (err) {
          statusBox.hidden = false;
          statusBox.textContent = '失败: ' + err.message;
        } finally {
          btn.disabled = false;
        }
      });
    });
    container.appendChild(wrap);
  }

  function mountEditableSection(container, { text, html, onSave, project, opts, jobs }) {
    const wrap = document.createElement('div');
    wrap.className = 'editable-section';
    wrap.innerHTML = `
      <div class="view-mode">
        <div class="content-html"></div>
        <button class="small edit-toggle">编辑…</button>
      </div>
      <div class="edit-mode" hidden>
        <textarea class="edit-textarea"></textarea>
        <div class="toolbar">
          <button class="primary small save-btn">保存</button>
          <button class="small cancel-btn">取消</button>
        </div>
        <div class="edit-status" hidden></div>
      </div>
      <div class="regen-shortcut-mount"></div>
    `;
    const viewMode = wrap.querySelector('.view-mode');
    const editMode = wrap.querySelector('.edit-mode');
    const contentHtml = wrap.querySelector('.content-html');
    const textarea = wrap.querySelector('.edit-textarea');
    const statusBox = wrap.querySelector('.edit-status');
    const regenMount = wrap.querySelector('.regen-shortcut-mount');
    contentHtml.innerHTML = html;

    wrap.querySelector('.edit-toggle').addEventListener('click', () => {
      textarea.value = text;
      statusBox.hidden = true;
      viewMode.hidden = true;
      editMode.hidden = false;
    });
    wrap.querySelector('.cancel-btn').addEventListener('click', () => {
      editMode.hidden = true;
      viewMode.hidden = false;
    });
    wrap.querySelector('.save-btn').addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      const newText = textarea.value;
      btn.disabled = true;
      statusBox.hidden = true;
      try {
        const result = await onSave(newText);
        text = newText;
        contentHtml.innerHTML = result.html;
        editMode.hidden = true;
        viewMode.hidden = false;
        toast('已保存');
        if (jobs && Object.keys(jobs).length) {
          const prompt = extractPromptBlock(newText);
          if (prompt) {
            mountRegenShortcut(regenMount, project, jobs, opts, prompt);
          }
        }
      } catch (err) {
        statusBox.hidden = false;
        statusBox.textContent = '保存失败：' + err.message;
      } finally {
        btn.disabled = false;
      }
    });

    container.appendChild(wrap);
    return wrap;
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

  return {
    esc, toast, guarded, mountComments, mountAssetJob, attachRegenPanel,
    mountEditableSection, openLightbox, openCommentPanel, gradeClass, targetKey,
  };
})();
