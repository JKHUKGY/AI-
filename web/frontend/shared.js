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

  async function approveImageGeneration(project, body) {
    const {approval} = await API.previewRegenerate(project, body);
    const payload = approval.payload;
    const accepted = await new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'lightbox approval-dialog';
      overlay.innerHTML = `<div class="lightbox-panel" role="dialog" aria-modal="true" aria-label="图片生成审批">
        <h2>审批本次图片生成</h2><p class="approval-summary"></p>
        <div class="regen-ref-thumbs"></div><h3>本次完整提示词</h3><pre class="approval-prompt"></pre>
        <label><input class="approval-check" type="checkbox"> 我已检查提示词、参考图和张数，批准本次图片生成</label>
        <p class="muted">本次将使用服务器的 Codex 图片额度。此审批不包含租显卡或视频生成。</p>
        <div class="toolbar"><button class="primary approve-image" disabled>批准并生成</button><button class="cancel-approval">取消</button></div>
      </div>`;
      overlay.querySelector('.approval-summary').textContent = `${payload.job_id} · ${payload.count} 张图片 · ${payload.ref_images.length} 张参考图 · 冻结 ${approval.credits ?? payload.count*10} 积分，成功每张扣 10，未完成部分退回`;
      overlay.querySelector('.approval-prompt').textContent = payload.prompt;
      payload.ref_images.forEach((path) => {
        const img = document.createElement('img');
        img.src = API.mediaUrl(path); img.alt = path.split('/').pop();
        overlay.querySelector('.regen-ref-thumbs').appendChild(img);
      });
      const done = (result) => { overlay.remove(); document.removeEventListener('keydown', onKey); resolve(result); };
      const onKey = (e) => { if (e.key === 'Escape') done(false); };
      const approve = overlay.querySelector('.approve-image');
      overlay.querySelector('.approval-check').addEventListener('change', (e) => { approve.disabled = !e.target.checked; });
      approve.addEventListener('click', () => done(true));
      overlay.querySelector('.cancel-approval').addEventListener('click', () => done(false));
      document.addEventListener('keydown', onKey);
      document.body.appendChild(overlay);
      overlay.querySelector('.cancel-approval').focus();
    });
    return accepted ? API.regenerate(project, {approval_id: approval.id, approved: true}) : null;
  }

  // 把"重新生成"面板（提示词编辑 / AI 改写 / 参考图复用 / 提交+轮询）做成
  // 可复用的一块：立绘、场景图、关键帧卡片都挂同一份逻辑，只是新图落到哪里
  // 由调用方通过 onNewFile 决定。
  function attachRegenPanel(regenPanel, project, jobId, jobData, opts, onNewFile) {
      if (!regenPanel.dataset.built) {
        regenPanel.dataset.built = '1';
        regenPanel.innerHTML = `
          <div class="regen-form">
            <strong>1. 选择参考图</strong>
            <div class="muted refs-group">正在加载同栏目图片…</div>
            <div class="reference-options"></div>
            <div class="toolbar"><span class="refs-summary muted"></span><button class="small clear-refs" disabled>取消全部参考</button></div>
            <strong>2. 选择提示词生成方式</strong>
            <label class="prompt-mode">生成方式 <select class="prompt-mode-select"><option value="fresh">完全重新生成（只根据本次描述）</option><option value="edit" selected>参考历史原文，按描述局部修改</option></select></label>
            <p class="mode-description muted"></p>
            <div class="prompt-source muted" role="status">正在查找历史提示词…</div>
            <div class="history-picker">
              <label>历史提示词 <select class="history-select"><option value="">选择历史版本…</option></select></label>
              <div class="toolbar"><button class="small use-history" disabled>载入这个版本</button><button class="small undo-history" hidden>撤销载入</button><button class="small save-version" disabled>保存当前为历史版本</button></div>
              <details class="history-preview" hidden><summary>预览所选历史版本</summary><pre></pre></details>
            </div>
            <button class="small retry-context" hidden>重新加载</button>
            <details class="original-prompt-details"><summary>查看历史原始提示词</summary><pre class="original-prompt"></pre></details>
            <div class="ai-rewrite-row">
              <input type="text" class="ai-instruction" maxlength="4000" placeholder="只写想改的部分，例如：头发剪短一点，其余保持原样">
              <button class="small ai-rewrite-btn" disabled>Codex 按原文改写</button>
            </div>
            <div class="muted">这里先生成文字提示词，图片仍需单独审批。参考图以本次勾选为准。</div>
            <div class="ai-write-status muted" role="status" aria-live="polite" hidden></div>
            <textarea maxlength="30000" placeholder="加载上一次的提示词中…" disabled></textarea>
            <strong>3. 检查提示词后生成</strong>
            <div class="toolbar">
              <label>生成张数 <input type="number" min="1" max="6" value="1" style="width:52px"></label>
              <button class="primary small go-regen" disabled>预览并审批图片生成</button>
              <button class="small stop-generation" hidden>终止生成</button>
            </div>
            <div class="regen-used-refs" hidden></div>
            <div class="regen-status" hidden></div>
          </div>
        `;
        const textarea = regenPanel.querySelector('textarea');
        const historySelect = regenPanel.querySelector('.history-select');
        const useHistory = regenPanel.querySelector('.use-history');
        const saveVersion = regenPanel.querySelector('.save-version');
        const undoHistory = regenPanel.querySelector('.undo-history');
        let history = [];
        let selectedVersion = null;
        let beforeHistory = null;
        const modeSelect = regenPanel.querySelector('.prompt-mode-select');
        const draftKey = 'regen-draft:' + JSON.stringify([currentUser?.username, project, opts.kind, opts.episode || null, jobId]);
        let draft = {};
        try { draft = JSON.parse(localStorage.getItem(draftKey) || '{}'); } catch {}
        let pendingSubmit = false;
        let taskBusy = false;
        let runningTasks = [];
        const stopGeneration = regenPanel.querySelector('.stop-generation');
        stopGeneration.addEventListener('click', async () => {
          stopGeneration.disabled = true; stopGeneration.textContent = '正在终止…';
          try { for (const task of runningTasks) await TaskUI.cancel(task); }
          catch (err) { UI.toast(err.message, 'error'); }
          finally { stopGeneration.disabled = false; stopGeneration.textContent = '终止生成'; }
        });
        const appliedImages = new Set(jobData.files || []);
        function saveDraft() {
          draft = {...draft, prompt: textarea.value, instruction: regenPanel.querySelector('.ai-instruction').value,
            mode: modeSelect.value, selectedVersion, refs: [...selectedRefs],
            original: regenPanel.querySelector('.original-prompt').textContent,
            source: regenPanel.querySelector('.prompt-source').textContent};
          try { localStorage.setItem(draftKey, JSON.stringify(draft)); } catch {}
        }
        function showMode() {
          const fresh = modeSelect.value === 'fresh';
          regenPanel.querySelector('.history-picker').hidden = fresh;
          regenPanel.querySelector('.original-prompt-details').hidden = fresh;
          regenPanel.querySelector('.prompt-source').hidden = fresh;
          regenPanel.querySelector('.mode-description').textContent = fresh
            ? '只根据这次描述从零写提示词，不传入历史原文或旧编辑内容。切换到此模式会清空旧参考图，可自行重新选择。'
            : '根据历史原文和当前提示词，自动定位描述涉及的部分，只修改这些内容，其余设定保留。';
          regenPanel.querySelector('.ai-instruction').placeholder = fresh ? '描述想要的完整画面，例如人物外貌、服装、构图和画风…' : '只写要改的部分，例如：把头发改短，其余保持原样';
          regenPanel.querySelector('.ai-rewrite-btn').textContent = fresh ? 'Codex 全新写提示词' : 'Codex 按原文改写';
        }
        function setBusy(busy) {
          taskBusy = busy;
          for (const selector of ['textarea', '.ai-instruction', '.ai-rewrite-btn', '.go-regen', '.prompt-mode-select', '.history-select', '.save-version', '.undo-history']) {
            regenPanel.querySelector(selector).disabled = busy || pendingSubmit;
          }
          useHistory.disabled = busy || pendingSubmit || !historySelect.value;
        }
        modeSelect.addEventListener('change', () => {
          const instruction = regenPanel.querySelector('.ai-instruction');
          if (modeSelect.value === 'fresh') {
            draft.editPrompt = textarea.value;
            draft.editInstruction = instruction.value;
            instruction.value = draft.freshInstruction || '';
            textarea.value = draft.freshPrompt || '';
            selectedRefs.clear();
            referenceOptions.querySelectorAll('input').forEach(input => { input.checked = false; });
            paintRefCount();
          } else {
            draft.freshPrompt = textarea.value;
            draft.freshInstruction = instruction.value;
            instruction.value = draft.editInstruction || '';
            textarea.value = draft.editPrompt ?? textarea.value;
          }
          showMode(); saveDraft();
        });
        function fillHistory(versions) {
          history = versions;
          historySelect.replaceChildren(new Option('选择历史版本…', ''));
          history.forEach((v) => historySelect.add(new Option(
            `${v.timestamp || '早期记录'} · ${v.source} · ${v.prompt.length} 字${v.image_count ? ` · 出过 ${v.image_count} 张图` : ''}`, v.id)));
          useHistory.disabled = true;
        }
        function addVersion(v) {
          if (v) fillHistory([v, ...history.filter((item) => item.id !== v.id)]);
        }
        historySelect.addEventListener('change', () => {
          const version = history.find((v) => v.id === historySelect.value);
          const preview = regenPanel.querySelector('.history-preview');
          preview.hidden = !version;
          preview.open = !!version;
          preview.querySelector('pre').textContent = version?.prompt || '';
          useHistory.disabled = !version;
        });
        useHistory.addEventListener('click', () => {
          const version = history.find((v) => v.id === historySelect.value);
          if (!version) return;
          beforeHistory = {prompt: textarea.value, version: selectedVersion,
            original: regenPanel.querySelector('.original-prompt').textContent,
            source: regenPanel.querySelector('.prompt-source').textContent};
          textarea.value = version.prompt;
          selectedVersion = version.id;
          regenPanel.querySelector('.original-prompt').textContent = version.prompt;
          regenPanel.querySelector('.prompt-source').textContent = `已载入历史版本：${version.source} · ${version.timestamp || '早期记录'}；Codex 将以此为原文。`;
          undoHistory.hidden = false;
        });
        undoHistory.addEventListener('click', () => {
          if (!beforeHistory) return;
          textarea.value = beforeHistory.prompt;
          selectedVersion = beforeHistory.version;
          regenPanel.querySelector('.original-prompt').textContent = beforeHistory.original;
          regenPanel.querySelector('.prompt-source').textContent = beforeHistory.source;
          undoHistory.hidden = true;
        });
        saveVersion.addEventListener('click', async () => {
          saveVersion.disabled = true;
          try {
            const {version} = await guarded(() => API.savePromptVersion(project, {
              job_id: jobId, kind: opts.kind, episode: opts.episode, prompt: textarea.value,
            }));
            addVersion(version);
            toast('当前提示词已保存到历史版本');
          } catch {} finally { saveVersion.disabled = false; }
        });
        const selectedRefs = new Set();
        const referenceOptions = regenPanel.querySelector('.reference-options');
        const clearRefs = regenPanel.querySelector('.clear-refs');
        function paintRefCount() {
          regenPanel.querySelector('.refs-summary').textContent = selectedRefs.size
            ? `已选 ${selectedRefs.size} 张参考图（最多 6 张）`
            : '未选参考图：本次将使用纯文字生成';
        }
        function addReferenceOption(option) {
          if (Array.from(referenceOptions.querySelectorAll('input')).some((input) => input.value === option.path)) return;
          const card = document.createElement('div');
          card.className = 'reference-choice';
          const label = document.createElement('label');
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.value = option.path;
          checkbox.checked = selectedRefs.has(option.path);
          const img = document.createElement('img');
          img.src = API.mediaUrl(option.path);
          img.alt = option.job_id;
          img.loading = 'lazy';
          const caption = document.createElement('span');
          caption.textContent = option.path.split('/').pop() + (option.selected ? ' · 已入选' : '') + (option.previous ? ' · 上次参考' : '');
          label.append(checkbox, img, caption);
          const preview = document.createElement('button');
          preview.className = 'small';
          preview.textContent = '放大查看';
          preview.addEventListener('click', () => {
            const overlay = document.createElement('div');
            overlay.className = 'lightbox reference-preview';
            const full = document.createElement('img');
            full.src = img.src;
            full.alt = caption.textContent;
            const close = document.createElement('button');
            close.textContent = '关闭预览';
            const dismiss = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
            const onKey = (e) => { if (e.key === 'Escape') dismiss(); };
            close.addEventListener('click', dismiss);
            overlay.addEventListener('click', (e) => { if (e.target === overlay) dismiss(); });
            document.addEventListener('keydown', onKey);
            overlay.append(full, close);
            document.body.appendChild(overlay);
            close.focus();
          });
          checkbox.addEventListener('change', () => {
            if (checkbox.checked && selectedRefs.size >= 6) {
              checkbox.checked = false;
              toast('最多选择 6 张参考图', 'error');
              return;
            }
            if (checkbox.checked) selectedRefs.add(option.path);
            else selectedRefs.delete(option.path);
            paintRefCount();
          });
          card.append(label, preview);
          referenceOptions.appendChild(card);
        }
        clearRefs.addEventListener('click', () => {
          selectedRefs.clear();
          referenceOptions.querySelectorAll('input').forEach((input) => { input.checked = false; });
          paintRefCount();
        });
        const retryContext = regenPanel.querySelector('.retry-context');
        async function loadContext() {
          retryContext.hidden = true;
          try {
            const context = await API.lastPrompt(project, jobId, opts.kind, opts.episode);
            fillHistory(context.history || []);
            textarea.value = opts.initialPrompt ?? context.prompt ?? '';
            textarea.placeholder = context.prompt ? '' : '没有找到历史原文，请先补充完整提示词';
            regenPanel.querySelector('.prompt-source').textContent = context.prompt
              ? `已加载历史提示词 · 来源：${context.prompt_source} · ${context.prompt.length} 字`
              : '未找到历史原文；补充完整提示词后才能进行改写。';
            if (opts.initialPrompt !== undefined) {
              regenPanel.querySelector('.prompt-source').textContent += '；下方当前版本使用你刚保存的提示词。';
            }
            regenPanel.querySelector('.original-prompt').textContent = context.original_prompt || '暂无历史原文';
            regenPanel.querySelector('.refs-group').textContent = `同栏目：${context.reference_group}。勾选希望参考的图片，可多选；“上次参考”已默认勾选。`;
            referenceOptions.innerHTML = '';
            selectedRefs.clear();
            (context.ref_images || []).slice(0, 6).forEach((path) => selectedRefs.add(path));
            (context.reference_options || []).forEach(addReferenceOption);
            if (!referenceOptions.children.length) referenceOptions.textContent = '该栏目暂时没有可用参考图。';
            paintRefCount();
            textarea.disabled = false;
            clearRefs.disabled = false;
            saveVersion.disabled = false;
            regenPanel.querySelector('.ai-rewrite-btn').disabled = false;
            regenPanel.querySelector('.go-regen').disabled = false;
            if (Object.hasOwn(draft, 'prompt')) {
              textarea.value = draft.prompt;
              regenPanel.querySelector('.ai-instruction').value = draft.instruction || '';
              modeSelect.value = draft.mode || 'edit';
              selectedVersion = draft.selectedVersion || null;
              regenPanel.querySelector('.original-prompt').textContent = draft.original || context.original_prompt || '';
              regenPanel.querySelector('.prompt-source').textContent = draft.source || context.prompt_source || '';
              selectedRefs.clear(); (draft.refs || []).forEach(path => selectedRefs.add(path));
              referenceOptions.querySelectorAll('input').forEach(input => { input.checked = selectedRefs.has(input.value); });
              paintRefCount();
            }
            showMode();
            setBusy(taskBusy);
            TaskUI.refresh();
          } catch (e) {
            regenPanel.querySelector('.prompt-source').textContent = '加载历史提示词失败：' + e.message + '。请重试后再修改。';
            retryContext.hidden = false;
          }
        }
        retryContext.addEventListener('click', loadContext);
        loadContext();

        regenPanel.addEventListener('input', () => { draft.editedAt = Date.now() / 1000; saveDraft(); });
        regenPanel.addEventListener('change', saveDraft);
        regenPanel.addEventListener('click', () => queueMicrotask(saveDraft));
        TaskUI.subscribe(regenPanel, (tasks) => {
          const matching = tasks.filter(t => t.project === project && t.target.job_id === jobId
            && t.target.type === opts.kind && Number(t.target.episode || 0) === Number(opts.episode || 0));
          const texts = matching.filter(t => t.kind === 'prompt');
          const textTask = texts.at(-1);
          const images = matching.filter(t => t.kind === 'image');
          const imageTask = images.at(-1);
          runningTasks = matching.filter(t => t.status === 'running');
          stopGeneration.hidden = !runningTasks.length;
          setBusy(matching.some(t => t.status === 'running'));
          if (textTask) {
            const box = regenPanel.querySelector('.ai-write-status'); box.hidden = false;
            box.textContent = textTask.status === 'running' ? 'Codex 正在后台写提示词，换页或刷新后可继续查看。'
              : textTask.status === 'cancelled' ? '已终止，原编辑内容保留，可重新生成。'
              : textTask.status === 'done' ? '提示词已完成并保存在历史版本和顶部任务栏。' : (textTask.error || '文字任务未完成');
            if (textTask.status !== 'running' && draft.pendingTask === textTask.id && textTask.status !== 'done') {
              draft.pendingTask = null;
              // 换页时历史内容可能仍在加载，不用尚为空的表单覆盖原草稿。
              try { localStorage.setItem(draftKey, JSON.stringify(draft)); } catch {}
            }
            if (textTask.status === 'done' && draft.appliedTask !== textTask.id
                && (!draft.editedAt || draft.editedAt <= textTask.created_at || draft.pendingTask === textTask.id)) {
              textarea.value = textTask.result.prompt;
              addVersion(textTask.result.version);
              draft.appliedTask = textTask.id; draft.pendingTask = null;
              saveDraft();
            }
          }
          if (imageTask) {
            const box = regenPanel.querySelector('.regen-status'); box.hidden = false;
            box.textContent = imageTask.status === 'running' ? '图片正在后台生成，切换页面不会停止任务。'
              : imageTask.status === 'cancelled' ? '已终止，已保存图片保留，可重新审批生成。'
              : imageTask.status === 'done' ? '图片生成已完成。' : (imageTask.error || '图片生成失败，请检查任务记录。');
            for (const fname of imageTask.new_files || []) {
              const rel = `${project}/${opts.baseDirHint}/${jobId}/${fname}`;
              if (!appliedImages.has(rel)) { appliedImages.add(rel); onNewFile(rel, fname); addReferenceOption({path:rel, job_id:jobId}); }
            }
          }
        });

        regenPanel.querySelector('.ai-rewrite-btn').addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          const instrInput = regenPanel.querySelector('.ai-instruction');
          const instruction = instrInput.value.trim();
          if (!instruction) {
            toast(modeSelect.value === 'fresh' ? '请先描述想要的完整画面' : '请先描述想修改的部分', 'error');
            return;
          }
          const before = textarea.value;
          if (!before.trim() && modeSelect.value === 'edit') {
            toast('请先补充完整的原提示词，再让 Codex 改写', 'error');
            return;
          }
          pendingSubmit = true;
          setBusy(true);
          btn.disabled = true;
          textarea.disabled = true;
          historySelect.disabled = true;
          useHistory.disabled = true;
          undoHistory.disabled = true;
          saveVersion.disabled = true;
          instrInput.disabled = true;
          const generateBtn = regenPanel.querySelector('.go-regen');
          generateBtn.disabled = true;
          const writeStatus = regenPanel.querySelector('.ai-write-status');
          writeStatus.hidden = false;
          writeStatus.textContent = 'Codex 正在写提示词，请稍候（最长约 2 分钟）…';
          btn.textContent = 'Codex 正在写…';
          const savedPlaceholder = textarea.placeholder;
          textarea.placeholder = 'Codex 正在写提示词…';
          try {
            const { task } = await guarded(() => API.startPromptTask(project, {
              job_id: jobId, kind: opts.kind, episode: opts.episode,
              instruction, mode: modeSelect.value,
              current_prompt: modeSelect.value === 'fresh' ? '' : before,
              prompt_version_id: modeSelect.value === 'fresh' ? null : selectedVersion,
            }));
            draft.pendingTask = task.id;
            saveDraft();
            writeStatus.textContent = '已提交后台文字任务，可以切换页面。';
            TaskUI.refresh();
          } catch (err) {
            textarea.value = before;
            writeStatus.textContent = '生成失败：' + err.message;
          } finally {
            pendingSubmit = false;
            textarea.placeholder = savedPlaceholder;
            textarea.disabled = false;
            btn.disabled = false;
            btn.textContent = 'Codex 按原文改写';
            instrInput.disabled = false;
            generateBtn.disabled = false;
            historySelect.disabled = false;
            useHistory.disabled = !historySelect.value;
            undoHistory.disabled = false;
            saveVersion.disabled = false;
            showMode();
            setBusy(!!draft.pendingTask);
          }
        });

        regenPanel.querySelector('.go-regen').addEventListener('click', async (e) => {
          const btn = e.currentTarget;
          btn.disabled = true;
          regenPanel.querySelector('.ai-rewrite-btn').disabled = true;
          const refsBox = regenPanel.querySelector('.regen-used-refs');
          const statusBox = regenPanel.querySelector('.regen-status');
          refsBox.hidden = true;
          refsBox.innerHTML = '';
          statusBox.hidden = false;
          statusBox.textContent = '正在准备本次图片任务的审批预览…';
          let imageSubmitted = false;
          try {
            const prompt = regenPanel.querySelector('textarea').value.trim();
            const count = Number(regenPanel.querySelector('input[type=number]').value) || 1;
            const body = { job_id: jobId, kind: opts.kind, count, ref_images: Array.from(selectedRefs) };
            if (prompt) body.prompt = prompt;
            if (opts.episode) body.episode = opts.episode;
            const result = await guarded(() => approveImageGeneration(project, body));
            if (!result) {
              statusBox.textContent = '已取消审批，本次没有执行图片生成。';
              return;
            }
            const { token, used_ref_images } = result;
            imageSubmitted = true;
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
            statusBox.textContent = '图片任务已提交后台，切换页面后可在顶部任务栏继续查看。';
            TaskUI.refresh();
          } catch (err) {
            statusBox.textContent = '失败: ' + err.message;
          } finally {
            btn.disabled = false;
            regenPanel.querySelector('.ai-rewrite-btn').disabled = false;
            setBusy(imageSubmitted);
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
        <button class="small choose-refs">选择参考图并生成…</button>
        <div class="regen-panel" hidden style="width:100%"></div>
        <div class="img-grid"></div>
      `;
      jobsBox.appendChild(row);
      const shown = [];
      row.querySelector('.choose-refs').addEventListener('click', () => {
        const panel = row.querySelector('.regen-panel');
        panel.hidden = !panel.hidden;
        if (!panel.hidden) {
          attachRegenPanel(panel, project, jobId, jobs[jobId], {...opts, initialPrompt: prompt}, (relPath) => {
            shown.push(relPath);
            const card = document.createElement('div');
            card.className = 'img-card';
            card.innerHTML = `<img loading="lazy" src="${API.mediaUrl(relPath)}">`;
            card.addEventListener('click', () => openLightbox(project, jobId, {
              files: shown, index: shown.indexOf(relPath),
            }));
            row.querySelector('.img-grid').appendChild(card);
          });
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
