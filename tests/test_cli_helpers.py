from pathlib import Path

from chaoxing_course_downloader.cli import sanitize_filename, with_chapter_id


def test_sanitize_filename_removes_invalid_chars():
    assert sanitize_filename('a/b:c*?"<>|.pdf') == 'a_b_c_.pdf'


def test_with_chapter_id_replaces_existing_value():
    url = 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=1&courseId=2&enc=abc'
    assert with_chapter_id(url, '999') == 'https://mooc1.chaoxing.com/mycourse/studentstudy?chapterId=999&courseId=2&enc=abc'
