from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config import Config


def add_book(client, auth, isbn="978-1", copies=2, title="Clean Code"):
    payload = {"isbn": isbn, "title": title, "author": "R. Martin", "copies": copies}
    return client.post("/api/books", json=payload, headers=auth)


def add_member(client, auth, email="asha@example.com"):
    return client.post("/api/members", json={"name": "Asha", "email": email}, headers=auth)


def test_health_and_readiness(client):
    assert client.get("/healthz").get_json()["status"] == "ok"
    assert client.get("/readyz").status_code == 200


def test_readiness_fails_without_database(make_app):
    app = make_app(database_url="postgresql://nobody:x@127.0.0.1:1/none")
    assert app.test_client().get("/readyz").status_code == 503
    assert app.test_client().get("/healthz").status_code == 200


def test_page_and_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("method,path", [
    ("get", "/api/members"), ("get", "/api/loans"), ("post", "/api/books"),
    ("post", "/api/members"), ("post", "/api/loans"), ("post", "/api/loans/1/return"),
])
def test_protected_routes_need_key(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers={"X-API-Key": "wrong"}).status_code == 401


def test_add_search_and_duplicate_book(client, auth):
    assert add_book(client, auth).status_code == 201
    assert add_book(client, auth).status_code == 409
    assert len(client.get("/api/books?q=clean").get_json()) == 1
    assert client.get("/api/books?q=%25zzz").get_json() == []


def test_search_treats_wildcards_literally(client, auth):
    add_book(client, auth)
    assert client.get("/api/books?q=_").get_json() == []


@pytest.mark.parametrize("payload", [
    None, [], {"isbn": "1"}, {"isbn": "1", "title": "t", "author": "a", "copies": 0},
    {"isbn": "1", "title": "t", "author": "a", "copies": True},
    {"isbn": "1", "title": "x" * 201, "author": "a", "copies": 1},
])
def test_invalid_book_is_rejected(client, auth, payload):
    assert client.post("/api/books", json=payload, headers=auth).status_code == 400


def test_borrow_and_return(client, auth):
    book = add_book(client, auth).get_json()
    member = add_member(client, auth).get_json()
    payload = {"book_id": book["id"], "member_id": member["id"]}

    loan = client.post("/api/loans", json=payload, headers=auth)
    assert loan.status_code == 201
    assert client.get("/api/books").get_json()[0]["available_copies"] == 1
    # Same member, same book: refused, and the stock change is rolled back.
    assert client.post("/api/loans", json=payload, headers=auth).status_code == 409
    assert client.get("/api/books").get_json()[0]["available_copies"] == 1

    url = f"/api/loans/{loan.get_json()['id']}/return"
    assert client.post(url, headers=auth).status_code == 200
    assert client.post(url, headers=auth).status_code == 404
    assert client.get("/api/books").get_json()[0]["available_copies"] == 2
    assert client.get("/api/loans", headers=auth).get_json()[0]["overdue"] is False


def test_unknown_member_does_not_consume_a_copy(client, auth):
    book = add_book(client, auth).get_json()
    response = client.post(
        "/api/loans", json={"book_id": book["id"], "member_id": 999}, headers=auth)
    assert response.status_code == 404
    assert client.get("/api/books").get_json()[0]["available_copies"] == 2


def test_last_copy_cannot_be_lent_twice(app, auth):
    client = app.test_client()
    book = add_book(client, auth, copies=1).get_json()
    members = [add_member(client, auth, f"m{i}@example.com").get_json()["id"] for i in range(6)]

    def borrow(member_id):
        return app.test_client().post(
            "/api/loans", json={"book_id": book["id"], "member_id": member_id}, headers=auth
        ).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = sorted(pool.map(borrow, members))
    assert results == [201, 409, 409, 409, 409, 409]


def test_duplicate_and_invalid_member(client, auth):
    assert add_member(client, auth).status_code == 201
    assert add_member(client, auth).status_code == 409
    assert add_member(client, auth, "not-an-email").status_code == 400


def test_fault_injection_is_off_by_default(client, make_app):
    assert client.get("/api/books").status_code == 200
    assert make_app(fault_rate=1.0).test_client().get("/api/books").status_code == 500


def test_unknown_route_returns_json_404(client):
    response = client.get("/nope")
    assert response.status_code == 404 and "error" in response.get_json()


def test_request_id_is_sanitised(client):
    assert client.get("/", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    assert client.get("/", headers={"X-Request-ID": "<x>"}).headers["X-Request-ID"] != "<x>"


def test_weak_api_key_is_refused(monkeypatch):
    monkeypatch.setenv("API_KEY", "short")
    with pytest.raises(RuntimeError):
        Config.from_env()
