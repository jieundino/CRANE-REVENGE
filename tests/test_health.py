"""STEP 2: FastAPI 기본 서버 및 /health 엔드포인트 테스트."""

import unittest

from backend.main import app
from tests import ASGIClient


class TestHealthEndpoint(unittest.TestCase):
    """FastAPI 기본 상태 확인 및 잘못된 경로 응답 검증."""

    def setUp(self) -> None:
        self.client = ASGIClient(app)

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_docs_accessible(self) -> None:
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Swagger UI", response.text)

    def test_invalid_route_returns_404(self) -> None:
        response = self.client.get("/invalid-path-check")
        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())


if __name__ == "__main__":
    unittest.main()
