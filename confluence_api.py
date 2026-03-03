import requests
from requests.auth import HTTPBasicAuth

from config import (
    CONFLUENCE_BASE_URL,
    CONFLUENCE_API_URL,
    CONFLUENCE_EMAIL,
    CONFLUENCE_API_TOKEN,
    SPACE_KEY,
    SPACE_ID,
)


class ConfluenceAPI:
    """Confluence Cloud REST API 래퍼."""

    def __init__(self):
        if not CONFLUENCE_API_TOKEN:
            raise ValueError(
                "CONFLUENCE_API_TOKEN 환경변수가 설정되지 않았습니다.\n"
                ".env 파일에 설정하거나 export CONFLUENCE_API_TOKEN=... 을 실행하세요."
            )
        self.auth = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}

    def _v1(self, method: str, path: str, **kwargs) -> dict:
        """v1 REST API 호출."""
        url = f"{CONFLUENCE_API_URL}{path}"
        resp = requests.request(method, url, auth=self.auth, headers=self.headers, **kwargs)
        if not resp.ok:
            print(f"[API ERROR] {resp.status_code} {resp.reason}")
            print(f"[API ERROR] URL: {url}")
            print(f"[API ERROR] Response: {resp.text[:500]}")
            resp.raise_for_status()
        if resp.status_code == 204 or not resp.text:
            return {}
        return resp.json()

    def _v2(self, method: str, path: str, **kwargs) -> dict:
        """v2 REST API 호출."""
        url = f"{CONFLUENCE_BASE_URL}/wiki/api/v2{path}"
        resp = requests.request(method, url, auth=self.auth, headers=self.headers, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.text:
            return {}
        return resp.json()

    def get_page_by_title(self, title: str, space_key: str = SPACE_KEY) -> dict | None:
        """제목으로 페이지를 조회한다. 없으면 None."""
        data = self._v1(
            "GET",
            "/content",
            params={
                "spaceKey": space_key,
                "title": title,
                "expand": "version,body.storage",
            },
        )
        results = data.get("results", [])
        return results[0] if results else None

    def get_page_content(self, page_id: str) -> str:
        """페이지 본문(storage format)을 가져온다."""
        data = self._v1(
            "GET",
            f"/content/{page_id}",
            params={"expand": "body.storage,version"},
        )
        return data["body"]["storage"]["value"]

    def get_page_version(self, page_id: str) -> int:
        """페이지 현재 버전 번호를 가져온다."""
        data = self._v1(
            "GET",
            f"/content/{page_id}",
            params={"expand": "version"},
        )
        return data["version"]["number"]

    def create_live_doc(self, title: str, body: str, parent_id: str) -> dict:
        """라이브문서를 생성한다 (v2 API, subtype=live)."""
        payload = {
            "spaceId": SPACE_ID,
            "parentId": parent_id,
            "status": "current",
            "title": title,
            "subtype": "live",
            "body": {
                "representation": "storage",
                "value": body,
            },
        }
        return self._v2("POST", "/pages", json=payload)

    def update_page(self, page_id: str, title: str, body: str, version: int) -> dict:
        """페이지 본문을 업데이트한다 (v2 API)."""
        payload = {
            "id": page_id,
            "status": "current",
            "title": title,
            "version": {"number": version + 1},
            "body": {
                "representation": "storage",
                "value": body,
            },
        }
        return self._v2("PUT", f"/pages/{page_id}", json=payload)

    def get_child_pages(self, parent_id: str) -> list[dict]:
        """하위 페이지 목록을 가져온다."""
        data = self._v1(
            "GET",
            f"/content/{parent_id}/child/page",
            params={"limit": 100},
        )
        return data.get("results", [])

    def move_page_before(self, page_id: str, target_id: str) -> dict:
        """페이지를 target 페이지 앞으로 이동한다 (사이드바 순서 조정)."""
        return self._v1("PUT", f"/content/{page_id}/move/before/{target_id}")

    def create_page(self, title: str, body: str, parent_id: str, space_key: str = SPACE_KEY) -> dict:
        """일반 페이지를 생성한다 (v1 API)."""
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "ancestors": [{"id": parent_id}],
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
        }
        return self._v1("POST", "/content", json=payload)

    def get_page_parent_id(self, page_id: str) -> str | None:
        """페이지의 부모 페이지 ID를 반환한다."""
        data = self._v1(
            "GET",
            f"/content/{page_id}",
            params={"expand": "ancestors"},
        )
        ancestors = data.get("ancestors", [])
        return ancestors[-1]["id"] if ancestors else None

    def get_page_subtype(self, page_id: str) -> str | None:
        """페이지의 subtype을 조회한다 (v2 API). 라이브문서면 'live', 일반 페이지면 None."""
        data = self._v2("GET", f"/pages/{page_id}")
        return data.get("subtype") or None

    def move_page(self, page_id: str, new_parent_id: str) -> dict:
        """페이지를 다른 부모 아래로 이동한다 (v1 API)."""
        version = self.get_page_version(page_id)
        data = self._v1(
            "GET",
            f"/content/{page_id}",
            params={"expand": "body.storage"},
        )
        title = data["title"]
        body = data["body"]["storage"]["value"]
        payload = {
            "type": "page",
            "title": title,
            "ancestors": [{"id": new_parent_id}],
            "version": {"number": version + 1},
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
        }
        return self._v1("PUT", f"/content/{page_id}", json=payload)

    def delete_page(self, page_id: str) -> dict:
        """페이지를 삭제한다 (v2 API)."""
        return self._v2("DELETE", f"/pages/{page_id}")
