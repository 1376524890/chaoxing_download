#!/usr/bin/env python3
"""
超星课件/PPT/PDF下载小工具

功能：
1. 单页下载：打开一个 studentstudy 链接，提取当前章节课件真实下载链接并保存；
2. 批量下载：从课程目录自动发现同一课程全部章节，逐章打开并下载资料；
3. 目录结构：按「一级章节/二级章节」保存，避免文件混在一起；
4. 文本提取：可选将 PDF 文字提取为 Markdown；
5. 预览图保存：可选保存每页 PNG 缩略图。

依赖：
- browser-use CLI；
- requests；
- 如需文字提取：python3 -m pip install --user pypdf

单页示例：
python3 chaoxing_ppt_downloader.py "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --out-dir . --extract-text

批量示例：
python3 chaoxing_ppt_downloader.py "https://mooc1.chaoxing.com/mycourse/studentstudy?..." \
  --out-dir ./超星课程资料 --batch --extract-text --save-thumbs

如果页面需要登录：
- 加 --wait-login；
- 脚本打开浏览器后，在浏览器里手动登录/确认课件加载；
- 回终端按 Enter 后继续。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import requests


DEFAULT_BROWSER_USE = shutil.which("browser-use") or "/Users/marktom/miniconda3/bin/browser-use"


EXTRACT_JS = r"""
(() => {
  function cleanText(s) { return (s || '').replace(/\s+/g, ' ').trim(); }

  const result = {
    pageUrl: location.href,
    pageTitle: document.title,
    courseTitle: cleanText(document.body && document.body.innerText).slice(0, 300),
    chapterTitle: '',
    frames: [],
    files: [],
    file: null,
    error: null
  };

  try {
    const selected = document.querySelector('span[title][class*=\"cur\"], span[title].current');
    const titleNode = selected || [...document.querySelectorAll('span[title]')].find(x => cleanText(x.innerText) && location.href.includes(x.closest('[id^=cur]')?.id?.replace('cur','')));
    result.chapterTitle = cleanText((titleNode && (titleNode.getAttribute('title') || titleNode.innerText)) || '');
  } catch (e) {}

  const seen = new Set();

  function addFile(win, doc, source) {
    try {
      if (!win.fileinfo || !win.fileinfo.download) return;
      const key = win.fileinfo.download || win.fileinfo.objectId || win.fileinfo.objectid;
      if (seen.has(key)) return;
      seen.add(key);

      const imgs = [...doc.querySelectorAll('img')].map((img, i) => ({
        i: i + 1,
        src: img.src || '',
        w: img.naturalWidth || 0,
        h: img.naturalHeight || 0
      })).filter(x => /\/thumb\/\d+\.png/.test(x.src));

      result.files.push({
        source,
        viewerUrl: win.location.href,
        download: win.fileinfo.download,
        objectId: win.fileinfo.objectId || win.fileinfo.objectid || '',
        suffix: win.fileinfo.suffix || '',
        filesize: win.fileinfo.filesize || '',
        name: win.fileinfo.name || '',
        pagenum: win.pagenum || win.totalPage || imgs.length || 0,
        thumbs: imgs.map(x => x.src)
      });
    } catch (e) {}
  }

  function addFallbackFile(win) {
    try {
      if (result.files.length || !win.curObjectId) return;
      result.files.push({
        source: 'ananas_pdf_vars',
        viewerUrl: win.ypPreviewUrl || win.ypInitUrl || win.location.href,
        download: '',
        objectId: win.curObjectId || '',
        suffix: '',
        filesize: '',
        name: win.fileNameStr || '',
        pagenum: 0,
        thumbs: []
      });
    } catch (e) {}
  }

  function walk(win, path) {
    try {
      const doc = win.document;
      result.frames.push({
        path,
        url: win.location.href,
        title: doc.title,
        text: cleanText(doc.body && doc.body.innerText).slice(0, 200),
        iframes: [...doc.querySelectorAll('iframe')].map((f, i) => ({
          i, id: f.id || '', src: f.src || '', w: f.clientWidth, h: f.clientHeight
        }))
      });

      addFile(win, doc, 'window.fileinfo');
      addFallbackFile(win);

      [...doc.querySelectorAll('iframe')].forEach((f, i) => {
        try { walk(f.contentWindow, path + '.f' + i + '#' + (f.id || '')); } catch (e) {}
      });
    } catch (e) {}
  }

  walk(window, 'top');
  result.file = result.files[0] || null;
  if (!result.file) result.error = '未找到文档预览器 fileinfo；请确认已登录且课件已加载。';
  return JSON.stringify(result);
})()
"""


CHAPTERS_JS = r"""
(() => {
  function cleanText(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function absStudentUrl(chapterId) {
    const u = new URL(location.href);
    u.searchParams.set('chapterId', chapterId);
    return u.toString();
  }

  const chapters = [];
  const seen = new Set();
  let currentTop = '';

  const items = [...document.querySelectorAll('#content1 li[level], li[level]')];
  for (const li of items) {
    const level = li.getAttribute('level') || '';
    const span = li.querySelector('span[title]');
    const title = cleanText(span && (span.getAttribute('title') || span.innerText));
    if (!title) continue;

    if (level === '1') {
      currentTop = title;
      continue;
    }

    const cur = li.querySelector('[id^="cur"]');
    const m = cur && (cur.id || '').match(/^cur(\d+)/);
    if (!m) continue;
    const chapterId = m[1];
    if (seen.has(chapterId)) continue;
    seen.add(chapterId);

    const numNode = span.querySelector('em');
    const number = cleanText(numNode && numNode.innerText);
    const name = title.replace(new RegExp('^' + number.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*'), '').trim() || title;
    chapters.push({
      chapterId,
      level,
      number,
      title,
      name,
      section: currentTop,
      url: absStudentUrl(chapterId)
    });
  }

  // 兜底：如果目录 DOM 结构变化，从所有 id=cur数字 的节点提取。
  // browser-use 的可访问性快照里能看到 level，但真实 DOM 有时没有 level 属性；
  // 这里按当前课程标题关键词做一次稳定分组，至少能得到「一级目录/二级目录」结构。
  if (!chapters.length) {
    const sectionByTitle = (title) => {
      if (/导论|公共产品|公共提供|偏好显示|外部性|公共选择/.test(title)) return '1 公共支出分析基本理论';
      if (/规模与结构|成本收益|利益归宿/.test(title)) return '2 支出分析视角与工具';
      if (/环境保护|公共教育|财政科技/.test(title)) return '3 公共支出分析专题探讨';
      return '未分组';
    };
    for (const cur of [...document.querySelectorAll('[id^="cur"]')]) {
      const m = (cur.id || '').match(/^cur(\d+)/);
      if (!m || seen.has(m[1])) continue;
      const span = cur.querySelector('span[title]') || cur.closest('li')?.querySelector('span[title]');
      const title = cleanText(span && (span.getAttribute('title') || span.innerText));
      if (!title) continue;
      seen.add(m[1]);
      chapters.push({chapterId: m[1], level: '', number: '', title, name: title, section: sectionByTitle(title), url: absStudentUrl(m[1])});
    }
  }

  return JSON.stringify({
    pageUrl: location.href,
    pageTitle: document.title,
    courseTitle: cleanText(document.body && document.body.innerText).slice(0, 300),
    chapters
  });
})()
"""


@dataclass
class DownloadResult:
    ok: bool
    chapter_title: str
    files: int = 0
    message: str = ""


def run_browser_use(args: list[str], timeout: int = 120) -> str:
    cmd = [DEFAULT_BROWSER_USE] + args
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"browser-use failed: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc.stdout.strip()


def parse_eval_result(stdout: str) -> dict:
    s = stdout.strip()
    if s.startswith("result:"):
        s = s[len("result:"):].strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        try:
            s = json.loads(s)
        except Exception:
            s = s[1:-1]
    return json.loads(s)


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name or "未命名"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 2
    while True:
        p = path.with_name(f"{stem} ({i}){suffix}")
        if not p.exists():
            return p
        i += 1


def guess_filename(info: dict) -> str:
    name = (info.get("name") or "").strip()
    if name:
        return sanitize_filename(name)

    download = info.get("download") or ""
    qs = parse_qs(urlparse(download).query)
    if qs.get("fn"):
        return sanitize_filename(unquote(qs["fn"][0]))

    object_id = info.get("objectId") or "chaoxing_document"
    suffix = (info.get("suffix") or "pdf").lstrip(".") or "pdf"
    return sanitize_filename(f"{object_id}.{suffix}")


def with_chapter_id(url: str, chapter_id: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["chapterId"] = [str(chapter_id)]
    query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=query))


def download_file(url: str, referer: str, out_path: Path, overwrite: bool = False) -> Path:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Referer": referer,
        "Origin": f"{urlparse(referer).scheme}://{urlparse(referer).netloc}" if referer else "https://pan-yz.chaoxing.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    }
    if out_path.exists() and not overwrite:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    with requests.get(url, headers=headers, stream=True, timeout=90, allow_redirects=True) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(out_path)
    return out_path


def extract_pdf_text(pdf_path: Path, md_path: Path) -> tuple[int, list[int], int]:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("缺少 pypdf，请先运行：python3 -m pip install --user pypdf") from e

    reader = PdfReader(str(pdf_path))
    empty_pages: list[int] = []
    parts = [f"# {pdf_path.stem} 文字提取\n\n来源文件：`{pdf_path.name}`\n\n总页数：{len(reader.pages)}\n"]
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
        if not text:
            empty_pages.append(i)
            text = "（未提取到可复制文字，可能是图片页）"
        parts.append(f"\n\n## 第 {i} 页\n\n{text}\n")
    md_path.write_text("".join(parts), encoding="utf-8")
    return len(reader.pages), empty_pages, len(md_path.read_text(encoding="utf-8"))


def save_thumbs(thumbs: list[str], out_dir: Path, referer: str, limit: int | None = None, overwrite: bool = False) -> int:
    if not thumbs:
        return 0
    img_dir = out_dir / "slides_png"
    img_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": referer or "https://pan-yz.chaoxing.com/"}
    count = 0
    for idx, url in enumerate(thumbs[:limit], 1):
        target = img_dir / f"{idx:03d}.png"
        if target.exists() and not overwrite:
            count += 1
            continue
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        target.write_bytes(r.content)
        count += 1
    return count


def open_page(url: str, session: str, headed: bool, wait_seconds: float = 3) -> None:
    args = []
    if headed:
        args.append("--headed")
    args += ["--session", session, "open", url]
    run_browser_use(args, timeout=180)
    if wait_seconds:
        time.sleep(wait_seconds)


def extract_current_page(session: str) -> dict:
    raw = run_browser_use(["--session", session, "eval", EXTRACT_JS], timeout=180)
    return parse_eval_result(raw)


def discover_chapters(session: str) -> dict:
    raw = run_browser_use(["--session", session, "eval", CHAPTERS_JS], timeout=180)
    return parse_eval_result(raw)


def chapter_dir_name(chapter: dict, index: int) -> str:
    number = sanitize_filename(chapter.get("number") or f"{index:02d}")
    name = sanitize_filename(chapter.get("name") or chapter.get("title") or chapter.get("chapterId") or str(index))
    if number and not name.startswith(number):
        return f"{number} {name}"
    return name


def section_dir_name(chapter: dict) -> str:
    return sanitize_filename(chapter.get("section") or "未分组")


def download_files_from_data(
    data: dict,
    out_dir: Path,
    extract_text_flag: bool,
    save_thumbs_flag: bool,
    thumb_limit: int | None,
    overwrite: bool,
) -> int:
    files = data.get("files") or ([data["file"]] if data.get("file") else [])
    meta_path = out_dir / "chaoxing_fileinfo.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    downloaded = 0
    for idx, info in enumerate(files, 1):
        download_url = info.get("download") or ""
        viewer_url = info.get("viewerUrl") or data.get("pageUrl") or ""
        if not download_url:
            continue

        filename = guess_filename(info)
        if len(files) > 1:
            p = Path(filename)
            filename = f"{idx:02d}_{p.stem}{p.suffix}"
        file_path = out_dir / filename
        if file_path.exists() and not overwrite:
            saved_path = file_path
        else:
            saved_path = download_file(download_url, viewer_url, file_path, overwrite=overwrite)
        downloaded += 1
        print(f"    保存：{saved_path.name} ({saved_path.stat().st_size} bytes)")

        if save_thumbs_flag:
            thumb_dir = out_dir if len(files) == 1 else out_dir / Path(filename).stem
            n = save_thumbs(info.get("thumbs") or [], thumb_dir, viewer_url, thumb_limit, overwrite=overwrite)
            if n:
                print(f"    预览图：{n} 张")

        if extract_text_flag and saved_path.suffix.lower() == ".pdf":
            md_path = saved_path.with_name(saved_path.stem + "_文字提取.md")
            if md_path.exists() and not overwrite:
                print(f"    文字：已存在 {md_path.name}")
            else:
                pages, empty, chars = extract_pdf_text(saved_path, md_path)
                msg = f"    文字：{md_path.name} ({chars} chars, {pages} 页)"
                if empty:
                    msg += "；空页/图片页：" + ",".join(map(str, empty))
                print(msg)
    return downloaded


def download_one_url(
    url: str,
    out_dir: Path,
    session: str,
    headed: bool,
    wait_login: bool,
    extract_text_flag: bool,
    save_thumbs_flag: bool,
    thumb_limit: int | None,
    overwrite: bool,
) -> DownloadResult:
    open_page(url, session=session, headed=headed)
    if wait_login:
        input("如需登录/等待课件加载，请在浏览器完成后回到这里按 Enter 继续...")
    data = extract_current_page(session)
    title = data.get("chapterTitle") or data.get("pageTitle") or url
    if not (data.get("files") or data.get("file")):
        (out_dir / "chaoxing_fileinfo.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return DownloadResult(False, title, 0, data.get("error") or "未找到可下载资料")
    n = download_files_from_data(data, out_dir, extract_text_flag, save_thumbs_flag, thumb_limit, overwrite)
    return DownloadResult(True, title, n, "ok")


def load_url_list(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def main() -> int:
    global DEFAULT_BROWSER_USE

    ap = argparse.ArgumentParser(description="下载超星学生学习页中的 PPT/PDF 课件，支持同课程批量下载。")
    ap.add_argument("url", nargs="?", help="超星 studentstudy 链接；批量模式下作为发现课程目录的入口")
    ap.add_argument("--out-dir", default=".", help="输出目录，默认当前目录")
    ap.add_argument("--session", default="default", help="browser-use session 名称")
    ap.add_argument("--browser-use", default=DEFAULT_BROWSER_USE, help="browser-use CLI 路径")
    ap.add_argument("--no-headed", action="store_true", help="不显示浏览器窗口")
    ap.add_argument("--wait-login", action="store_true", help="打开后等待手动登录/加载，再继续提取")
    ap.add_argument("--extract-text", action="store_true", help="下载 PDF 后提取文字到 Markdown")
    ap.add_argument("--save-thumbs", action="store_true", help="同时保存预览 PNG 图片")
    ap.add_argument("--thumb-limit", type=int, default=None, help="最多保存多少张预览图")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已存在文件")
    ap.add_argument("--batch", action="store_true", help="从课程目录自动发现并下载全部章节资料")
    ap.add_argument("--urls-file", help="从文本文件读取 URL 列表，每行一个；会按顺序批量下载")
    ap.add_argument("--chapter-ids", nargs="*", help="指定 chapterId 列表批量下载，会基于入口 URL 替换 chapterId")
    ap.add_argument("--list-only", action="store_true", help="只发现并打印章节列表，不下载")
    ap.add_argument("--limit", type=int, default=None, help="批量模式最多处理多少个章节，便于测试")
    args = ap.parse_args()

    DEFAULT_BROWSER_USE = args.browser_use
    if not Path(DEFAULT_BROWSER_USE).exists() and not shutil.which(DEFAULT_BROWSER_USE):
        print(f"找不到 browser-use：{DEFAULT_BROWSER_USE}", file=sys.stderr)
        return 2

    if not args.url and not args.urls_file:
        ap.error("需要提供 url，或使用 --urls-file")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    headed = not args.no_headed

    if args.urls_file:
        urls = load_url_list(Path(args.urls_file).expanduser())
        chapters = [{"url": u, "title": f"URL {i:02d}", "name": f"URL {i:02d}", "section": "批量URL", "number": f"{i:02d}"} for i, u in enumerate(urls, 1)]
    elif args.chapter_ids:
        base_url = args.url or ""
        chapters = [{"url": with_chapter_id(base_url, cid), "chapterId": cid, "title": cid, "name": cid, "section": "指定章节", "number": f"{i:02d}"} for i, cid in enumerate(args.chapter_ids, 1)]
    elif args.batch or args.list_only:
        print("[1/3] 打开入口页面并发现课程目录...")
        open_page(args.url, session=args.session, headed=headed)
        if args.wait_login:
            input("如需登录/等待目录加载，请在浏览器完成后回到这里按 Enter 继续...")
        discovered = discover_chapters(args.session)
        chapters = discovered.get("chapters") or []
        (out_dir / "chaoxing_chapters.json").write_text(json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"发现章节：{len(chapters)} 个；列表已保存：{out_dir / 'chaoxing_chapters.json'}")
    else:
        print("[1/4] 单页下载...")
        result = download_one_url(
            args.url,
            out_dir,
            args.session,
            headed,
            args.wait_login,
            args.extract_text,
            args.save_thumbs,
            args.thumb_limit,
            args.overwrite,
        )
        if result.ok:
            print(f"完成：{result.chapter_title}；文件数：{result.files}")
            return 0
        print(f"失败：{result.chapter_title}；{result.message}", file=sys.stderr)
        return 3

    if args.limit:
        chapters = chapters[: args.limit]

    if args.list_only:
        for i, ch in enumerate(chapters, 1):
            print(f"{i:02d}. [{ch.get('section','')}] {ch.get('number','')} {ch.get('name') or ch.get('title')}  chapterId={ch.get('chapterId','')}  {ch.get('url')}")
        return 0

    if not chapters:
        print("没有可处理的章节。", file=sys.stderr)
        return 4

    print(f"[2/3] 开始批量下载：{len(chapters)} 个章节")
    summary = []
    ok_count = 0
    file_count = 0
    for i, ch in enumerate(chapters, 1):
        sec = section_dir_name(ch)
        cdir = chapter_dir_name(ch, i)
        target_dir = out_dir / sec / cdir
        title = ch.get("title") or ch.get("name") or ch.get("chapterId") or str(i)
        print(f"\n[{i}/{len(chapters)}] {sec} / {cdir}")
        try:
            res = download_one_url(
                ch["url"],
                target_dir,
                args.session,
                headed,
                False,  # 批量中只在入口等待一次；每章不再打断
                args.extract_text,
                args.save_thumbs,
                args.thumb_limit,
                args.overwrite,
            )
            ok_count += 1 if res.ok else 0
            file_count += res.files
            summary.append({**ch, "ok": res.ok, "files": res.files, "message": res.message, "outDir": str(target_dir)})
            if res.ok:
                print(f"    完成：{res.files} 个文件")
            else:
                print(f"    跳过/失败：{res.message}")
        except Exception as e:
            summary.append({**ch, "ok": False, "files": 0, "message": str(e), "outDir": str(target_dir)})
            print(f"    失败：{e}")

    summary_path = out_dir / "chaoxing_batch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[3/3] 批量完成：章节成功 {ok_count}/{len(chapters)}，文件 {file_count} 个")
    print(f"汇总：{summary_path}")
    return 0 if file_count else 5


if __name__ == "__main__":
    raise SystemExit(main())
