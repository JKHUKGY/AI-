"""受限静态文件服务：只把 /media/<相对 output/ 的路径> 映射到
output/ 目录下真实存在的文件，路径穿越校验交给 projects.resolve_media_path。
支持基本的 Range 请求（视频 <video> 标签拖动进度条需要）。
"""
import mimetypes
import os

CHUNK = 256 * 1024


def guess_content_type(path):
    ctype, _ = mimetypes.guess_type(path)
    return ctype or 'application/octet-stream'


def parse_range(range_header, file_size):
    """只支持 'bytes=start-end' 单一区间这一种最常见形式，其它一律当作
    不带 Range 处理（返回 None），足够 <video>/<img> 场景使用。"""
    if not range_header or not range_header.startswith('bytes='):
        return None
    spec = range_header[len('bytes='):].split(',')[0].strip()
    if '-' not in spec:
        return None
    start_s, end_s = spec.split('-', 1)
    try:
        if start_s == '':
            suffix_len = int(end_s)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else file_size - 1
    except ValueError:
        return None
    end = min(end, file_size - 1)
    if start > end or start < 0:
        return None
    return start, end


def iter_file(path, start, end):
    with open(path, 'rb') as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
