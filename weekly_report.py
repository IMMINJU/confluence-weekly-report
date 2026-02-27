"""
Confluence 주간보고 자동화 스크립트.

사용법:
    python weekly_report.py create       # 이번 주 빈 라이브문서 생성
    python weekly_report.py carry-over   # 지난주 차주예정 → 이번주 금주진행 복사
    python weekly_report.py archive      # 지난주 라이브문서 → 완료 폴더에 일반 페이지로 복제 후 원본 삭제
    python weekly_report.py new-week     # archive + create + carry-over 한번에
"""

import sys
from bs4 import BeautifulSoup

from config import (
    MEMBERS,
    PARENT_PAGE_ID,
    ARCHIVE_FOLDER_ID,
    SPACE_KEY,
    get_week_range,
    get_last_week_range,
    format_page_title,
)
from confluence_api import ConfluenceAPI


def build_empty_template() -> str:
    """담당자 4명이 포함된 빈 주간보고 표 HTML을 생성한다 (실제 Confluence storage format)."""
    rows = ""
    for member in MEMBERS:
        rows += (
            '<tr><td><p>{member}</p></td>'
            '<td><p /></td>'
            '<td><p /></td>'
            '<td><p /></td></tr>\n'
        ).format(member=member)

    return (
        '<table data-table-width="1800" data-layout="align-start">'
        '<colgroup>'
        '<col style="width: 96.0px;" />'
        '<col style="width: 632.0px;" />'
        '<col style="width: 744.0px;" />'
        '<col style="width: 324.0px;" />'
        '</colgroup>'
        '<tbody>'
        '<tr>'
        '<th><p><strong>담당자</strong></p></th>'
        '<th><p><strong>금주 진행 내역</strong></p></th>'
        '<th><p><strong>차주 예정 내역</strong></p></th>'
        '<th><p><strong>비고</strong></p></th>'
        '</tr>\n'
        f'{rows}'
        '</tbody></table>'
    )


def move_to_top(api: ConfluenceAPI, page_id: str):
    """생성된 페이지를 사이드바 맨 위로 이동한다."""
    siblings = api.get_child_pages(PARENT_PAGE_ID)
    for sibling in siblings:
        if sibling["id"] != page_id:
            api.move_page_before(page_id, sibling["id"])
            print(f"[OK] 사이드바 맨 위로 이동 완료")
            return
    print(f"[INFO] 이미 맨 위에 있습니다")


def cmd_create(api: ConfluenceAPI) -> str | None:
    """이번 주 빈 라이브문서를 생성한다. 생성된 page_id 반환."""
    monday, friday = get_week_range()
    title = format_page_title(monday, friday)

    existing = api.get_page_by_title(title, SPACE_KEY)
    if existing:
        print(f"[SKIP] 이미 존재합니다: '{title}' (id={existing['id']})")
        return existing["id"]

    body = build_empty_template()
    result = api.create_live_doc(title, body, PARENT_PAGE_ID)
    page_id = result["id"]
    links = result.get("_links", {})
    page_url = links.get("base", "") + links.get("webui", "")
    print(f"[OK] 라이브문서 생성 완료: '{title}' (id={page_id})")
    if page_url:
        print(f"     URL: {page_url}")

    move_to_top(api, page_id)
    return page_id


def cmd_archive(api: ConfluenceAPI):
    """지난주 문서를 완료 폴더로 아카이브한다.

    - 라이브문서인 경우: 완료 폴더에 [완료] 프리픽스 일반 페이지로 복제 후 원본 삭제
    - 이미 일반 페이지인 경우: 완료 폴더로 이동만
    """
    last_mon, last_fri = get_last_week_range()
    last_title = format_page_title(last_mon, last_fri)

    last_page = api.get_page_by_title(last_title, SPACE_KEY)
    if not last_page:
        print(f"[SKIP] 지난주 페이지가 없습니다: '{last_title}'")
        print(f"        (이미 아카이브되었거나 삭제된 상태)")
        return

    last_id = last_page["id"]

    # 이미 완료 폴더에 있으면 스킵
    parent_id = api.get_page_parent_id(last_id)
    if parent_id == ARCHIVE_FOLDER_ID:
        print(f"[SKIP] 이미 완료 폴더에 있습니다: '{last_title}'")
        return

    # subtype 확인: 라이브문서 vs 일반 페이지
    subtype = api.get_page_subtype(last_id)

    if subtype == "live":
        # 라이브문서 → 완료 폴더에 일반 페이지로 복제 후 원본 삭제
        # 같은 스페이스에 동일 제목 불가 → 임시 제목으로 생성 → 원본 삭제 → 제목 복원
        body = api.get_page_content(last_id)
        print(f"[INFO] 라이브문서 내용 읽기 완료: '{last_title}'")

        temp_title = f"_archive_{last_title}"
        result = api.create_page(temp_title, body, ARCHIVE_FOLDER_ID)
        new_id = result["id"]
        print(f"[OK] 완료 폴더에 임시 페이지 생성 (id={new_id})")

        api.delete_page(last_id)
        print(f"[OK] 원본 라이브문서 삭제: '{last_title}' (id={last_id})")

        version = api.get_page_version(new_id)
        api.update_page(new_id, last_title, body, version)
        print(f"[OK] 페이지 제목 복원: '{last_title}' (id={new_id})")
    else:
        # 이미 일반 페이지 → 완료 폴더로 이동만
        print(f"[INFO] 일반 페이지 감지: '{last_title}' → 완료 폴더로 이동")
        api.move_page(last_id, ARCHIVE_FOLDER_ID)
        print(f"[OK] 완료 폴더로 이동 완료: '{last_title}' (id={last_id})")


def parse_table(html: str) -> dict[str, dict[str, str]]:
    """
    주간보고 표 HTML을 파싱하여 담당자별 데이터를 반환한다.

    Returns:
        {"이명호": {"금주": "<inner html>", "차주": "<inner html>", "비고": "<inner html>"}, ...}
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return {}

    result = {}
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        member = cells[0].get_text(strip=True)
        if member in MEMBERS:
            result[member] = {
                "금주": cells[1].decode_contents(),
                "차주": cells[2].decode_contents(),
                "비고": cells[3].decode_contents(),
            }
    return result


def build_carried_over_body(last_week_data: dict[str, dict[str, str]]) -> str:
    """지난주 차주예정을 이번주 금주진행에 넣은 표 HTML을 생성한다."""
    rows = ""
    for member in MEMBERS:
        carry = last_week_data.get(member, {}).get("차주", "<p />")
        if not carry.strip():
            carry = "<p />"
        rows += (
            f'<tr><td><p>{member}</p></td>'
            f'<td>{carry}</td>'
            f'<td><p /></td>'
            f'<td><p /></td></tr>\n'
        )

    return (
        '<table data-table-width="1800" data-layout="align-start">'
        '<colgroup>'
        '<col style="width: 96.0px;" />'
        '<col style="width: 632.0px;" />'
        '<col style="width: 744.0px;" />'
        '<col style="width: 324.0px;" />'
        '</colgroup>'
        '<tbody>'
        '<tr>'
        '<th><p><strong>담당자</strong></p></th>'
        '<th><p><strong>금주 진행 내역</strong></p></th>'
        '<th><p><strong>차주 예정 내역</strong></p></th>'
        '<th><p><strong>비고</strong></p></th>'
        '</tr>\n'
        f'{rows}'
        '</tbody></table>'
    )


def cmd_carry_over(api: ConfluenceAPI):
    """지난주 차주예정 내역을 이번주 금주진행에 복사한다."""
    last_mon, last_fri = get_last_week_range()
    last_title = format_page_title(last_mon, last_fri)

    # 원본 또는 아카이브 페이지에서 내용 조회
    last_page = api.get_page_by_title(last_title, SPACE_KEY)
    if not last_page:
        print(f"[ERROR] 지난주 페이지를 찾을 수 없습니다: '{last_title}'")
        sys.exit(1)

    last_content = api.get_page_content(last_page["id"])
    last_data = parse_table(last_content)
    if not last_data:
        print(f"[ERROR] 지난주 페이지에서 표를 파싱할 수 없습니다.")
        sys.exit(1)

    print(f"[INFO] 지난주 페이지: '{last_page['title']}'")
    has_content = False
    for member in MEMBERS:
        carry = last_data.get(member, {}).get("차주", "")
        text = BeautifulSoup(carry, "html.parser").get_text(strip=True)
        if text:
            has_content = True
            preview = text[:80] + ("..." if len(text) > 80 else "")
            print(f"  {member}: {preview}")
        else:
            print(f"  {member}: (비어있음)")
    if not has_content:
        print("[SKIP] 지난주 차주 예정 내역이 모두 비어 있습니다.")
        return

    this_mon, this_fri = get_week_range()
    this_title = format_page_title(this_mon, this_fri)
    this_page = api.get_page_by_title(this_title, SPACE_KEY)
    if not this_page:
        print(f"[ERROR] 이번주 페이지를 찾을 수 없습니다: '{this_title}'")
        print("        먼저 'python weekly_report.py create'를 실행하세요.")
        sys.exit(1)

    new_body = build_carried_over_body(last_data)
    version = api.get_page_version(this_page["id"])
    api.update_page(this_page["id"], this_title, new_body, version)
    print(f"\n[OK] 캐리오버 완료: '{last_page['title']}' → '{this_title}'")


def cmd_new_week(api: ConfluenceAPI):
    """새 주 시작: 지난주 아카이브 + 이번주 생성 + 캐리오버."""
    print("=== 1/3: 지난주 문서 아카이브 ===")
    cmd_archive(api)
    print()
    print("=== 2/3: 이번 주 라이브문서 생성 ===")
    cmd_create(api)
    print()
    print("=== 3/3: 지난주 차주예정 → 이번주 금주진행 ===")
    cmd_carry_over(api)


COMMANDS = {
    "create": cmd_create,
    "carry-over": cmd_carry_over,
    "archive": cmd_archive,
    "new-week": cmd_new_week,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"사용 가능한 명령: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    command = sys.argv[1]
    api = ConfluenceAPI()
    COMMANDS[command](api)


if __name__ == "__main__":
    main()
