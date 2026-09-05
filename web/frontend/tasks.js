// 任务状态独立于页面路由；刷新浏览器后从服务端恢复。
const TaskUI = (() => {
  let tasks = [], timer, refreshing = false, container, signature;
  const listeners = new Set();
  const labels = {running:'进行中', done:'已完成', failed:'失败', interrupted:'已中断'};
  function render() {
    if (!container) return;
    const running = tasks.filter(t => t.status === 'running').length;
    container.querySelector('summary').textContent = `生成任务 · ${running} 个进行中 · 切换页面后继续保留`;
    const nextSignature = JSON.stringify(tasks.map(t => [t.id, t.status, t.result, t.error, t.new_files]));
    if (signature === nextSignature) return;
    signature = nextSignature;
    const list = container.querySelector('.task-list');
    const opened = new Set([...list.querySelectorAll('details[open]')].map(el => el.dataset.task));
    list.replaceChildren();
    if (!tasks.length) list.textContent = '暂无生成任务';
    [...tasks].reverse().slice(0, 40).forEach(task => {
      const row = document.createElement('div'); row.className = 'task-row';
      const title = document.createElement('span');
      title.textContent = `${task.project} · ${task.target.job_id} · ${task.kind === 'prompt' ? '提示词' : '图片'} · ${labels[task.status] || task.status}`;
      const link = document.createElement('a');
      const target = task.target;
      const route = target.type === 'keyframe' ? `keyframes/${target.episode}` : (target.job_id.startsWith('SC') ? 'scenes' : 'characters');
      link.href = `#/p/${encodeURIComponent(task.project)}/${route}`; link.textContent = '打开项目';
      row.append(title, link);
      if (task.result?.prompt || task.error) {
        const details = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
        details.dataset.task = task.id; details.open = opened.has(task.id);
        summary.textContent = task.result?.prompt ? '查看生成结果' : '查看原因';
        pre.textContent = task.result?.prompt || task.error; details.append(summary, pre); row.appendChild(details);
      }
      list.appendChild(row);
    });
  }
  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      tasks = (await API.tasks()).tasks;
      render();
      for (const listener of listeners) listener(tasks);
    } catch (err) {
      if (container) container.querySelector('summary').textContent = '任务状态暂时无法更新，将自动重试；后台任务继续运行';
    } finally {
      refreshing = false;
      clearTimeout(timer); timer = setTimeout(refresh, 3000);
    }
  }
  function init() {
    if (container) return;
    container = document.createElement('details'); container.className = 'global-tasks';
    container.innerHTML = '<summary>正在恢复生成任务…</summary><div class="task-list"></div>';
    document.querySelector('main').before(container);
    refresh();
  }
  function subscribe(element, fn) {
    const listener = (items) => {
      if (!element.isConnected) { listeners.delete(listener); return; }
      fn(items);
    };
    listeners.add(listener); listener(tasks);
  }
  return {init, refresh, subscribe};
})();
