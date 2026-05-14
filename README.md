# Chaoxing Course Downloader

A small command-line tool for downloading Chaoxing/超星 course materials from `studentstudy` pages.

It uses [`browser-use`](https://github.com/browser-use/browser-use) to open an authenticated course page, discovers the nested document viewer, extracts the real cloud-disk download URL, and downloads the original file with the required `Referer` header. It can also batch-discover all chapters in the same course and extract text from downloaded PDFs.

## Features

- Download a single Chaoxing chapter attachment.
- Batch-discover all chapters from the course directory.
- Preserve course-like directory structure:
  - first-level section
  - chapter folder
  - original file
  - extracted Markdown text
  - metadata JSON
- Optional PDF text extraction with `pypdf`.
- Optional preview slide PNG download.
- Supports explicit `chapterId` lists and URL-list files.

## Requirements

- Python 3.10+
- `browser-use` CLI available in `PATH`, or pass `--browser-use /path/to/browser-use`
- A logged-in Chaoxing session if the course is not public

Install Python dependencies:

```bash
python3 -m pip install -e .
```

For PDF text extraction:

```bash
python3 -m pip install -e '.[pdf]'
```

## Usage

### Single chapter

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --out-dir ./downloads \
  --extract-text
```

### Batch download all chapters in the course

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --out-dir ./course-materials \
  --batch \
  --extract-text
```

### List chapters only

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --list-only
```

### Download selected chapter IDs

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --chapter-ids 1167203522 1166407802 1161919249 \
  --extract-text
```

### Download URLs from a file

`urls.txt`:

```text
https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=...
https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=...
```

Run:

```bash
chaoxing-course-downloader --urls-file urls.txt --out-dir ./downloads --extract-text
```

### Manual login flow

If the page requires login:

```bash
chaoxing-course-downloader "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --batch \
  --wait-login \
  --extract-text
```

A headed browser window opens. Log in and wait until the course material is visible, then return to the terminal and press Enter.

## Output files

For each chapter, the tool writes:

- original downloaded file, usually `.pdf`
- `*_文字提取.md` when `--extract-text` is enabled
- `chaoxing_fileinfo.json` metadata

For batch runs, the output root also includes:

- `chaoxing_chapters.json`
- `chaoxing_batch_summary.json`

## Notes

- Some pages are image-only or partially image-based. `pypdf` can only extract embedded/copyable text; image-only pages are marked as empty in the Markdown output.
- Direct cloud-disk download links may return `403` unless downloaded with the viewer URL as `Referer`; this tool handles that automatically.
- Use this only for courses/materials you are authorized to access.

## License

MIT
