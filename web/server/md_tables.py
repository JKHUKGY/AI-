"""解析/改写 GFM pipe-table（每个分镜表/关键帧表/视频清单文件里的那种表）。

设计约束：这些 markdown 文件是 Claude 手写的，除了表格还有大量前后文
（标题、元信息、成本记录段落等），改一个单元格时绝不能整篇重新生成，
只替换目标那一行文本，其余字节保持不变。当前只处理"每个文件第一张表"，
这符合 storyboard/keyframes/video_jobs 这几类文件的实际结构（一个文件
一张主表）。
"""
import re

_SEP_CELL_RE = re.compile(r'^:?-+:?$')


def _split_row(line):
    inner = line.strip()
    if inner.startswith('|'):
        inner = inner[1:]
    if inner.endswith('|'):
        inner = inner[:-1]
    cells = []
    buf = []
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch == '\\' and i + 1 < n and inner[i + 1] == '|':
            buf.append('|')
            i += 2
            continue
        if ch == '|':
            cells.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append(''.join(buf).strip())
    return cells


def _looks_like_row(line):
    s = line.strip()
    return s.startswith('|') and s.endswith('|') and len(s) >= 2


def _is_separator_line(line):
    if not _looks_like_row(line):
        return False
    cells = _split_row(line)
    return len(cells) > 0 and all(_SEP_CELL_RE.match(c.replace(' ', '')) for c in cells)


# 供 md_render.py 复用的公开别名（渲染只读表格不需要重新走一遍写回逻辑）。
split_row = _split_row
is_separator_line = _is_separator_line
looks_like_row = _looks_like_row


def _find_table(lines):
    """返回第一张表的 (header_idx, data_start, data_end_exclusive, header_cells)，找不到返回 None。"""
    n = len(lines)
    for i in range(n - 1):
        if _looks_like_row(lines[i]) and _is_separator_line(lines[i + 1]):
            header = _split_row(lines[i])
            j = i + 2
            while j < n and _looks_like_row(lines[j]):
                j += 1
            return i, i + 2, j, header
    return None


def parse_table(text):
    """解析文本里第一张表，返回 dict：header/rows/位置信息；没有表格返回 None。"""
    lines = text.splitlines()
    loc = _find_table(lines)
    if not loc:
        return None
    header_idx, start, end, header = loc
    rows = []
    for k in range(start, end):
        cells = _split_row(lines[k])
        if len(cells) < len(header):
            cells = cells + [''] * (len(header) - len(cells))
        rows.append({header[idx]: cells[idx] if idx < len(cells) else '' for idx in range(len(header))})
    return {
        'header': header,
        'rows': rows,
        'header_idx': header_idx,
        'start': start,
        'end': end,
    }


def _escape_cell(value):
    value = '' if value is None else str(value)
    value = value.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    value = value.replace('|', '\\|')
    return value.strip()


def _render_row(header, row):
    cells = [_escape_cell(row.get(h, '')) for h in header]
    return '| ' + ' | '.join(cells) + ' |'


def set_cell(text, key_col, key_value, updates):
    """把 key_col==key_value 的那一行里的 updates(col->new_value) 写进去。

    只重写目标那一物理行，返回 (new_text, old_row)。找不到行/列时抛 ValueError。
    """
    lines = text.splitlines()
    loc = _find_table(lines)
    if not loc:
        raise ValueError('文件里没有找到表格')
    _header_idx, start, end, header = loc

    if key_col not in header:
        raise ValueError(f'表格没有列: {key_col}')
    for col in updates:
        if col not in header:
            raise ValueError(f'表格没有列: {col}')

    target_idx = None
    old_row = None
    for k in range(start, end):
        cells = _split_row(lines[k])
        row = {header[idx]: cells[idx] if idx < len(cells) else '' for idx in range(len(header))}
        if str(row.get(key_col, '')).strip() == str(key_value).strip():
            target_idx = k
            old_row = row
            break

    if target_idx is None:
        raise ValueError(f'找不到 {key_col}={key_value} 对应的行')

    new_row = dict(old_row)
    new_row.update(updates)
    lines[target_idx] = _render_row(header, new_row)

    newline = '\n'
    new_text = newline.join(lines)
    if text.endswith('\n'):
        new_text += '\n'
    return new_text, old_row
