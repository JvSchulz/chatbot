"""
Testes de integração garantindo que a documentação automática da API não é exposta.
"""

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_documentation_routes_return_404(path: str):
    """
    /docs, /redoc e /openapi.json devem responder 404 para qualquer cliente.
    """
    client = TestClient(app, follow_redirects=False)

    response = client.get(path)

    assert response.status_code == 404
