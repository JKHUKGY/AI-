# v3 候选图片归档与恢复

2026-09-05 已将 205 张待处理图和 65 张未选历史素材图上传到 Google Drive：

[打开云盘归档文件夹](https://drive.google.com/drive/folders/1qoUMokq90gehvgFGOSpLEqLMPw6pvdWb)

`gdrive:AI-短剧归档/出狱后我成为了非洲矿王_v3/历史候选/2026-09-05`

图片直接保存在“待处理图片”和“未选历史候选”文件夹，支持云盘预览。270 张图片上传后逐文件比对大小与 MD5，全部一致；再次检查本地 SHA-256 未改变后才移除本地源文件。释放 576,912,108 字节（550.19 MiB）。109 张已选图片和两张额外生成引用均保留。

[逐文件清单](2026-09-05-v3-candidates.json) 的 `source` 是原仓库相对路径，`remote` 是云端日期目录内的路径，`sha256` 用于恢复核验。`pending_link` 和 `pending_link_target` 记录原待处理图片链接。清单同时保存在云端 `归档清单.json`。剧本、卡片、提示词及审查记录留在本地；历史候选链接需取回图片后查看。

需要取回单张图片时，从清单复制该条的 `remote`，使用 `rclone copyto` 下载到仓库 `tmp/` 中，再用 `sha256sum` 与该条 `sha256` 比对；一致后移到 `source` 对应路径。目标路径已有文件时先比较，不覆盖新结果。

整批取回时，先下载到独立目录：

```bash
rclone copy 'gdrive:AI-短剧归档/出狱后我成为了非洲矿王_v3/历史候选/2026-09-05' tmp/v3-candidates-restore --checksum
```

然后按清单逐条校验 `tmp/v3-candidates-restore/<remote>` 的 SHA-256，并复制到 `<仓库>/<source>`。需要恢复待处理图片目录时，再按清单重建相对软链接。不要用项目整卷的 `archive.py restore`，本批是选择性归档。

在配置目录只读的会话中，可将 rclone 配置复制到任务临时目录并设置权限 0600，通过 `--config` 使用，使 OAuth 刷新能正常保存；完成后移除这份临时凭证。配置不得随归档上传或提交。
