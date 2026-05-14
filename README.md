# 超星课程资料下载器

一个用于下载超星/学习通课程资料的命令行工具。支持从 `studentstudy` 章节页面中定位课件预览器，提取真实下载链接，下载原始 PDF/PPT 等资料，并可批量下载同一门课程的全部章节资料。

## 功能特性

- 下载单个超星章节中的课件/附件。
- 自动发现同一课程目录下的全部章节并批量下载。
- 按课程目录结构保存文件：
  - 一级章节目录
  - 二级章节目录
  - 原始课件文件
  - Markdown 文字提取结果
  - 元数据 JSON
- 支持 PDF 文字提取，输出 `*_文字提取.md`。
- 支持保存每页预览图 PNG。
- 支持手动指定 `chapterId` 列表下载。
- 支持从文本文件读取 URL 列表批量下载。
- 自动处理超星云盘下载链接需要 `Referer` 否则返回 `403` 的情况。

## 工作原理

工具通过 `browser-use` 打开超星课程页面，利用已登录浏览器会话访问课程资料，然后递归检查页面中的嵌套 iframe：

```text
studentstudy 页面
└── knowledge/cards
    └── ananas/modules/pdf
        └── pan-yz.chaoxing.com/screen/v2/file_xxx
```

在最终的云盘预览页中读取 `window.fileinfo`，提取：

- `fileinfo.download`：真实下载链接
- `fileinfo.objectId`：文件 ID
- `fileinfo.suffix`：文件类型
- `pagenum`：页数
- `thumb/*.png`：页面预览图

随后用预览页 URL 作为 `Referer` 下载原始文件。

## 环境要求

- Python 3.10+
- 已安装 `browser-use` CLI
- 如果课程非公开，需要浏览器中已有登录态，或使用 `--wait-login` 手动登录

检查 `browser-use`：

```bash
browser-use doctor
```

如果 `browser-use` 不在 `PATH`，运行时可以用 `--browser-use` 指定路径：

```bash
--browser-use /Users/marktom/miniconda3/bin/browser-use
```

## 安装

进入项目目录：

```bash
cd chaoxing-course-downloader
```

安装基础依赖：

```bash
python3 -m pip install -e .
```

如果需要 PDF 文字提取：

```bash
python3 -m pip install -e '.[pdf]'
```

如果需要开发/测试依赖：

```bash
python3 -m pip install -e '.[dev,pdf]'
```

安装后会得到命令：

```bash
chaoxing-course-downloader --help
```

也可以不安装，直接用源码运行：

```bash
PYTHONPATH=src python3 -m chaoxing_course_downloader.cli --help
```

## 使用方法

### 下载单个章节

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --out-dir ./downloads \
  --extract-text
```

### 批量下载整门课程

只需要提供课程中的任意一个章节链接，工具会从左侧课程目录自动发现全部章节：

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --out-dir ./course-materials \
  --batch \
  --extract-text
```

### 只列出章节，不下载

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --list-only
```

输出示例：

```text
01. [1 公共支出分析基本理论] 公共支出分析导论 chapterId=1121418479 ...
02. [1 公共支出分析基本理论] 公共产品与公共提供 chapterId=1136150633 ...
```

### 只下载指定章节 ID

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --chapter-ids 1167203522 1166407802 1161919249 \
  --extract-text
```

工具会基于入口 URL 替换 `chapterId`，保留 `courseId`、`clazzid`、`cpi`、`enc` 等参数。

### 从 URL 文件批量下载

准备 `urls.txt`，每行一个链接：

```text
https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=...
https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=...
```

运行：

```bash
chaoxing-course-downloader \
  --urls-file urls.txt \
  --out-dir ./downloads \
  --extract-text
```

### 需要手动登录时

如果页面需要登录或验证码，使用：

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --batch \
  --wait-login \
  --extract-text
```

流程：

1. 工具打开一个可见浏览器窗口。
2. 在浏览器中手动登录超星。
3. 确认课程资料页面已经加载出来。
4. 回到终端按 Enter。
5. 工具继续发现目录并下载。

### 保存预览图

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --batch \
  --save-thumbs
```

限制最多保存前 5 页预览图：

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --batch \
  --save-thumbs \
  --thumb-limit 5
```

### 覆盖已存在文件

默认情况下，已存在文件不会重复下载。需要重新下载时加：

```bash
--overwrite
```

### 测试前几个章节

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --batch \
  --limit 2 \
  --extract-text
```

## 输出结构

批量下载后，输出目录类似：

```text
course-materials/
├── 1 公共支出分析基本理论/
│   ├── 01 公共支出分析导论/
│   │   ├── 第1讲 公共支出分析导论.pdf
│   │   ├── 第1讲 公共支出分析导论_文字提取.md
│   │   └── chaoxing_fileinfo.json
│   └── ...
├── 2 支出分析视角与工具/
│   └── ...
├── 3 公共支出分析专题探讨/
│   └── ...
├── chaoxing_chapters.json
└── chaoxing_batch_summary.json
```

每个章节目录中：

- 原始课件文件：通常是 `.pdf`
- `*_文字提取.md`：PDF 文字提取结果，仅在 `--extract-text` 时生成
- `chaoxing_fileinfo.json`：该章节页面和文件的元信息

批量输出根目录中：

- `chaoxing_chapters.json`：发现到的章节列表
- `chaoxing_batch_summary.json`：批量下载结果汇总

## 常用参数

| 参数 | 说明 |
| --- | --- |
| `--batch` | 自动发现并下载整门课程 |
| `--list-only` | 只列出章节，不下载 |
| `--extract-text` | 对 PDF 提取文字到 Markdown |
| `--save-thumbs` | 保存课件预览图 PNG |
| `--thumb-limit N` | 限制预览图保存页数 |
| `--wait-login` | 打开浏览器后等待手动登录 |
| `--chapter-ids ...` | 指定章节 ID 下载 |
| `--urls-file FILE` | 从文件读取 URL 列表 |
| `--overwrite` | 覆盖已存在文件 |
| `--no-headed` | 不显示浏览器窗口 |
| `--browser-use PATH` | 指定 browser-use 路径 |

## 注意事项

- 本工具不会绕过账号权限；只能下载当前登录账号有权访问的课程资料。
- 部分 PDF 页面可能是图片页，`pypdf` 只能提取可复制文字，图片页会在 Markdown 中标记为“未提取到可复制文字”。
- 如需 OCR 图片页，需要额外接入 OCR 工具，本项目当前不内置 OCR。
- 超星下载链接通常有时效性，建议发现后立即下载。
- 请仅用于你有权访问和保存的课程资料。

## 开发

安装开发依赖：

```bash
python3 -m pip install -e '.[dev,pdf]'
```

运行测试：

```bash
pytest
```

运行静态检查：

```bash
ruff check .
```

## 许可证

MIT
