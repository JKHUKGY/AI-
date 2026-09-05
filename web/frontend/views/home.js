window.Views = window.Views || {};

Views.home = async function home(app) {
  const { projects } = await API.projects();
  app.innerHTML = `
    <h1>选择一个项目</h1>
    <section class="card production-entry"><h2>租显卡 / 生成视频</h2><p>进入制作中心，查看视频任务是否准备好、租用显卡或手动关卡。</p>
      <div class="toolbar"><a class="action-link primary" href="#/production">进入视频制作中心</a><a class="action-link" href="#/gpu">租用 / 关闭显卡</a></div></section>
    <button class="primary" id="newProjectBtn">＋ 新建项目</button>
    <form class="card new-project-form" id="newProjectForm" hidden>
      <h2>从剧本开始</h2>
      <label>项目名称<input name="name" maxlength="80" required placeholder="为这部剧起一个项目名"></label>
      <label>导入剧本文件（可选）<input name="file" type="file" accept=".txt,.md,.docx"></label>
      <p class="muted">支持 TXT、Markdown、DOCX，最多 5 MB；选择文件后以文件内容为准。</p>
      <label>或粘贴剧本<textarea name="script" rows="9" maxlength="150000" placeholder="粘贴剧本正文，包含人物、场景和台词…"></textarea></label>
      <div class="toolbar"><label>目标集数<input name="episodes" type="number" min="1" max="30" value="1" required></label><label>每集时长（秒）<input name="duration" type="number" min="15" max="600" value="90" required></label></div>
      <label>画风与画幅<input name="style" maxlength="1000" value="写实电影质感，竖屏9:16" required></label>
      <p>自动生成文字基础文件：风格简报、人物与场景设计、分集规划、逐集分镜和制作清单。</p>
      <p class="notice">图片一律先预览再由你批准；租显卡需要另行审阅具体方案。创建项目不会自动出图或租卡。</p>
      <button class="primary create-project" type="submit">创建项目并生成文字文件</button>
      <p class="create-status" role="status"></p>
    </form>
    <p class="muted">第一次来先看看<a href="#/guide">使用指南</a>，了解每一步该看什么、该怎么留意见。</p>
    <div class="grid-cards">
      ${projects.map((p) => `
        <a class="project-card card" href="#/p/${encodeURIComponent(p.name)}/${p.has_setup ? 'setup' : 'characters'}">
          <h3>${UI.esc(p.name)}</h3>
          <div class="muted">${p.episodes.length ? `共 ${p.episodes.length} 集分镜表` : '分镜表待补充'}</div>
          <div class="badge-row">
            <span class="badge ${p.has_storyboard ? 'on' : ''}">分镜表</span>
            <span class="badge ${p.has_assets ? 'on' : ''}">人物/场景图</span>
            <span class="badge ${p.has_keyframes ? 'on' : ''}">关键帧</span>
            <span class="badge ${p.has_videos ? 'on' : ''}">视频</span>
          </div>
        </a>
      `).join('') || '<div class="empty-hint">还没有项目，点击“新建项目”导入第一份剧本。</div>'}
    </div>
  `;
  const form = app.querySelector('#newProjectForm');
  app.querySelector('#newProjectBtn').addEventListener('click', () => { form.hidden = !form.hidden; });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const button = form.querySelector('.create-project');
    const status = form.querySelector('.create-status');
    button.disabled = true;
    status.textContent = '正在保存剧本并创建项目…';
    try {
      const body = {name: form.elements.name.value.trim(), script: form.elements.script.value,
        episodes: Number(form.elements.episodes.value), duration: Number(form.elements.duration.value), style: form.elements.style.value};
      const file = form.elements.file.files[0];
      if (file) {
        if (file.size > 5 * 1024 * 1024) throw new Error('文件最多 5 MB');
        const data = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result.split(',')[1]);
          reader.onerror = () => reject(new Error('无法读取文件'));
          reader.readAsDataURL(file);
        });
        body.upload = {name: file.name, base64: data};
      }
      const created = await API.createProject(body);
      try { await API.startSetup(created.name); }
      catch (err) { UI.toast('项目已创建：' + err.message + '。可在项目页继续。', 'error'); }
      location.hash = `#/p/${encodeURIComponent(created.name)}/setup`;
    } catch (err) { status.textContent = err.message; }
    finally { button.disabled = false; }
  });
};
