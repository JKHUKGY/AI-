"""极简 markdown -> HTML，只覆盖仓库里这几类文档实际用到的语法：
# 标题、- 列表、``` 代码块、> 引用、**加粗**、`行内代码`、--- 分隔线、
表格。用于只读展示 characters.md / scenes.md / style_bible.md / guide.md
等正文（分镜表/关键帧表/视频清单这类需要"改单元格"的表格走 md_tables.py，
不走这里）。不追求覆盖完整 CommonMark 规范。
"""
import html
import re

import md_tables

_BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
_CODE_RE = re.compile(r'`([^`]+)`')
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
_HR_RE = re.compile(r'^-{3,}$')
_LIST_RE = re.compile(r'^[-*]\s+(.*)$')
_OLIST_RE = re.compile(r'^\d+[.)]\s+(.*)$')


def _inline(text):
    text = html.escape(text, quote=False)
    text = _BOLD_RE.sub(r'<strong>\1</strong>', text)
    text = _CODE_RE.sub(r'<code>\1</code>', text)
    return text


def _render_table(table_lines):
    header = md_tables.split_row(table_lines[0])
    body_rows = [md_tables.split_row(l) for l in table_lines[2:]]
    out = ['<table class="md-table">', '<thead><tr>']
    for h in header:
        out.append(f'<th>{_inline(h)}</th>')
    out.append('</tr></thead><tbody>')
    for cells in body_rows:
        out.append('<tr>')
        for idx in range(len(header)):
            val = cells[idx] if idx < len(cells) else ''
            out.append(f'<td>{_inline(val)}</td>')
        out.append('</tr>')
    out.append('</tbody></table>')
    return ''.join(out)


def _is_block_start(line):
    s = line.strip()
    if s == '':
        return True
    if s.startswith('```'):
        return True
    if s.startswith('|'):
        return True
    if _HEADING_RE.match(s):
        return True
    if _HR_RE.match(s):
        return True
    if s.startswith('>'):
        return True
    if _LIST_RE.match(s):
        return True
    if _OLIST_RE.match(s):
        return True
    return False


def _consume_list(lines, i, n, item_re):
    """从第 i 行开始吃一个列表：命中 item_re 开新的 <li>，普通非空、且不是
    别的块起始的行当作上一个 <li> 的换行延续（源文档习惯手动换行到 ~72
    列，同一条列表项的后续文字不会重复写 - 前缀）。返回 (每项文本片段的
    列表, 下一个待处理的行号)。"""
    items = []
    while i < n:
        stripped = lines[i].strip()
        m = item_re.match(stripped)
        if m:
            items.append([m.group(1)])
            i += 1
        elif items and stripped and not _is_block_start(lines[i]):
            items[-1].append(stripped)
            i += 1
        else:
            break
    return items, i


_H2_RE = re.compile(r'^##\s+(.*)$')


def split_h2_sections(text):
    """把正文按二级标题（## ）切成 [{title, body}]；第一段（H1 标题、
    简介等）title 为 None。characters.md/scenes.md 里一个角色/场景就是
    一个二级标题段落，供 app.py 按段落匹配对应的资产图片。"""
    lines = text.replace('\r\n', '\n').split('\n')
    sections = []
    title = None
    buf = []
    for line in lines:
        m = _H2_RE.match(line.strip())
        if m:
            if title is not None or buf:
                sections.append({'title': title, 'body': '\n'.join(buf)})
            title = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if title is not None or buf:
        sections.append({'title': title, 'body': '\n'.join(buf)})
    return sections


def set_h2_section_body(text, title, new_body):
    """把标题为 title 的二级标题段落的正文整体替换成 new_body，标题行本身
    不能改——标题文本被 app.py 用来跟 assets/ 目录做前缀匹配，找对应的
    立绘/场景图，改了标题会让图片对不上。找不到这个标题抛 ValueError。"""
    sections = split_h2_sections(text)
    found = False
    for sec in sections:
        if sec['title'] == title:
            sec['body'] = new_body
            found = True
            break
    if not found:
        raise ValueError(f'找不到标题为“{title}”的段落')
    parts = [sec['body'] if sec['title'] is None else f"## {sec['title']}\n{sec['body']}" for sec in sections]
    return '\n'.join(parts)


def render(text):
    lines = text.replace('\r\n', '\n').split('\n')
    out = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        if stripped == '':
            i += 1
            continue

        if stripped.startswith('```'):
            out.append('<pre><code>')
            i += 1
            while i < n and not lines[i].strip().startswith('```'):
                out.append(html.escape(lines[i]))
                i += 1
            out.append('</code></pre>')
            i += 1
            continue

        if stripped.startswith('|') and i + 1 < n and md_tables.is_separator_line(lines[i + 1]):
            table_lines = [lines[i], lines[i + 1]]
            j = i + 2
            while j < n and md_tables.looks_like_row(lines[j]):
                table_lines.append(lines[j])
                j += 1
            out.append(_render_table(table_lines))
            i = j
            continue

        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            out.append(f'<h{level}>{_inline(m.group(2))}</h{level}>')
            i += 1
            continue

        if _HR_RE.match(stripped):
            out.append('<hr>')
            i += 1
            continue

        if stripped.startswith('>'):
            quote_lines = []
            while i < n and lines[i].strip().startswith('>'):
                quote_lines.append(_inline(re.sub(r'^>\s?', '', lines[i].strip())))
                i += 1
            out.append('<blockquote>' + '<br>'.join(quote_lines) + '</blockquote>')
            continue

        if _LIST_RE.match(stripped):
            items, i = _consume_list(lines, i, n, _LIST_RE)
            out.append('<ul>' + ''.join(f'<li>{_inline(" ".join(parts))}</li>' for parts in items) + '</ul>')
            continue

        if _OLIST_RE.match(stripped):
            items, i = _consume_list(lines, i, n, _OLIST_RE)
            out.append('<ol>' + ''.join(f'<li>{_inline(" ".join(parts))}</li>' for parts in items) + '</ol>')
            continue

        para = [stripped]
        i += 1
        while i < n and not _is_block_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append('<p>' + _inline(' '.join(para)) + '</p>')

    return '\n'.join(out)
