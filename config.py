import os
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

# Confluence Cloud 설정
CONFLUENCE_BASE_URL = "https://twolinecloud.atlassian.net"
CONFLUENCE_API_URL = f"{CONFLUENCE_BASE_URL}/wiki/rest/api"
SPACE_KEY = "AccuInsight"

# 인증 (환경변수 또는 .env 파일)
CONFLUENCE_EMAIL = os.environ.get("CONFLUENCE_EMAIL", "minju.lim@twolinecloud.com")
CONFLUENCE_API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", "")

# 담당자 목록
MEMBERS = ["이명호", "이병진", "임성래", "임민주"]

# "2026년" 부모 페이지 ID (AccuInsight+ 3.0 인수/인계 > 1. 투라인클라우드 자료 > 00. 주간 보고 > 2026년)
PARENT_PAGE_ID = "109838412"
SPACE_ID = "1441823"
ARCHIVE_FOLDER_ID = "130744354"  # "완료" 폴더


def get_week_range(target_date: date = None) -> tuple[date, date]:
    """주어진 날짜가 속한 주의 월요일~금요일을 반환한다."""
    if target_date is None:
        target_date = date.today()
    monday = target_date - timedelta(days=target_date.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def get_last_week_range(target_date: date = None) -> tuple[date, date]:
    """지난주 월요일~금요일을 반환한다."""
    if target_date is None:
        target_date = date.today()
    monday = target_date - timedelta(days=target_date.weekday() + 7)
    friday = monday + timedelta(days=4)
    return monday, friday


def format_page_title(monday: date, friday: date) -> str:
    """페이지 제목 형식: 2026.02.16 ~ 2026.02.20"""
    return f"{monday.strftime('%Y.%m.%d')} ~ {friday.strftime('%Y.%m.%d')}"
