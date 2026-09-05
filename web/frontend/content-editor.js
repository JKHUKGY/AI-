const ContentEditor = (() => {
  function modal(title) {
    const overlay = document.createElement('div'); overlay.className = 'lightbox content-dialog';
    const box = document.createElement('div'); box.className = 'lightbox-panel'; box.setAttribute('role','dialog'); box.setAttribute('aria-modal','true'); box.setAttribute('aria-label',title);
    const h = document.createElement('h2'); h.textContent = title; box.appendChild(h);
    const close = document.createElement('button'); close.textContent = '取消'; close.className = 'content-cancel';
    function done() { overlay.remove(); document.removeEventListener('keydown', escape); }
    function escape(e) { if (e.key === 'Escape') done(); }
    close.addEventListener('click', done); document.addEventListener('keydown', escape);
    overlay.appendChild(box); document.body.appendChild(overlay);
    return {box,close,done};
  }
  async function add(project, kind, episode, header, after) {
    const names = {character:'角色',scene:'场景',episode:'分集',shot:'镜头'};
    const dialog = modal('新增' + names[kind]);
    const form = document.createElement('form'); form.className = 'content-form';
    const fields = kind === 'shot' ? header.filter(k => k !== '镜号') : ['名称', ...(kind === 'episode' ? [] : ['描述'])];
    const inputs = {};
    fields.forEach(field => {
      const label = document.createElement('label'); label.textContent = field;
      const input = document.createElement(field === '名称' ? 'input' : 'textarea'); input.name = field;
      input.maxLength = field === '名称' ? 80 : kind === 'shot' ? 8000 : 30000;
      if (input.tagName === 'TEXTAREA') input.rows = field === '描述' ? 7 : 2;
      input.required = ['名称','描述','画面描述'].includes(field);
      if (field === '分级') input.value = 'B';
      if (field === '时长(秒)') input.value = '5';
      label.appendChild(input); form.appendChild(label); inputs[field] = input;
    });
    const hint = document.createElement('p'); hint.className = 'muted'; hint.textContent = kind === 'shot' ? '自动分配新镜号，现有镜号保持不变。新增镜头需另行制作和审批图片。' : '只新增文字内容，图片仍需单独审批。';
    const error = document.createElement('p'); error.className = 'notice error'; error.hidden = true;
    const submit = document.createElement('button'); submit.className = 'primary content-submit'; submit.textContent = '保存新增';
    dialog.close.type = 'button'; form.append(hint,error,submit,dialog.close); dialog.box.appendChild(form);
    form.addEventListener('submit', async e => {
      e.preventDefault(); submit.disabled = true;
      try {
        const body = {kind, episode};
        if (kind === 'shot') { body.row = Object.fromEntries(fields.map(k => [k,inputs[k].value])); if (after !== undefined) body.after = after; }
        else { body.name = inputs['名称'].value; if (inputs['描述']) body.text = inputs['描述'].value; }
        const result = await API.contentChange(project,'add',body); dialog.done();
        if (kind === 'episode') location.hash = `#/p/${encodeURIComponent(project)}/episodes/${result.episode}`;
        else render();
        UI.toast('已新增' + names[kind]);
      } catch (err) { error.hidden = false; error.textContent = err.message; }
      finally { submit.disabled = false; }
    });
    form.querySelector('input,textarea')?.focus();
  }
  async function remove(project, body) {
    let preview;
    try { preview = await API.contentChange(project,'preview-delete',body); }
    catch (err) { UI.toast(err.message,'error'); return; }
    const dialog = modal('移入回收站');
    const name = document.createElement('p'); name.textContent = preview.title || (body.kind === 'episode' ? `第 ${body.episode} 集` : `第 ${body.episode} 集 · 镜 ${body.shot}`);
    const notice = document.createElement('p'); notice.textContent = preview.notice;
    const refs = document.createElement('p'); refs.className = 'notice'; refs.textContent = preview.references.length ? '仍被以下分镜引用：' + preview.references.slice(0,30).join('、') + (preview.references.length > 30 ? ` 等 ${preview.references.length} 处` : '') : '已有图片、视频和制作记录会保留。';
    const details = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
    summary.textContent = '查看将移除的文字'; pre.textContent = preview.content; details.append(summary,pre);
    const error = document.createElement('p'); error.className = 'notice error'; error.hidden = true;
    const confirm = document.createElement('button'); confirm.className = 'primary content-delete-confirm'; confirm.textContent = '确认移入回收站';
    confirm.addEventListener('click',async () => {
      confirm.disabled = true;
      try { await API.contentChange(project,'delete',{preview_id:preview.id,confirmed:true}); dialog.done(); render(); UI.toast('已移入回收站，可恢复'); }
      catch (err) { error.hidden = false; error.textContent = err.message; confirm.disabled = false; }
    });
    dialog.box.append(name,notice,refs,details,error,confirm,dialog.close);
  }
  async function trash(project) {
    const dialog = modal('回收站'); dialog.close.textContent = '关闭'; dialog.box.appendChild(dialog.close);
    try {
      const data = await API.contentTrash(project);
      const list = document.createElement('div'); dialog.box.appendChild(list);
      if (!data.items.length) list.textContent = '回收站为空';
      for (const item of data.items) {
        const row = document.createElement('div'); row.className = 'trash-row';
        const title = document.createElement('span'); title.textContent = item.title || (item.kind === 'episode' ? `第 ${item.episode} 集` : `第 ${item.episode} 集 · 镜 ${item.key}`);
        const button = document.createElement('button'); button.className = 'small restore-item'; button.textContent = '恢复';
        button.addEventListener('click',async () => {
          button.disabled = true;
          try { await API.contentChange(project,'restore',{id:item.id}); row.remove(); render(); UI.toast('已恢复'); }
          catch (err) { UI.toast(err.message,'error'); button.disabled = false; }
        }); row.append(title,button); list.appendChild(row);
      }
    } catch (err) { UI.toast(err.message,'error'); dialog.done(); }
  }
  function toolbar(container, project, kind, options={}) {
    const bar = document.createElement('div'); bar.className = 'toolbar content-toolbar';
    const button = document.createElement('button'); button.className = 'primary add-content';
    button.textContent = '＋ 新增' + ({character:'角色',scene:'场景',episode:'分集',shot:'镜头'})[kind];
    button.addEventListener('click',() => add(project,kind,options.episode,options.header));
    const recycle = document.createElement('button'); recycle.className = 'open-trash'; recycle.textContent = '回收站'; recycle.addEventListener('click',() => trash(project));
    bar.append(button,recycle); container.appendChild(bar);
  }
  function deleteButton(container,project,body) {
    const button = document.createElement('button'); button.className = 'small delete-content'; button.textContent = '删除';
    button.addEventListener('click',() => remove(project,body)); container.appendChild(button);
  }
  return {toolbar,deleteButton,add,remove};
})();
