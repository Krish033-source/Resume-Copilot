import os

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


class Authed:
    def __init__(self, client):
        self.c = client

    def _h(self):
        tok = self.c.get_cookie("csrf_access_token")
        return {"X-CSRF-TOKEN": tok.value} if tok else {}

    def get(self, *a, **k):
        return self.c.get(*a, **k)

    def post(self, *a, **k):
        k.setdefault("headers", {}).update(self._h())
        return self.c.post(*a, **k)

    def put(self, *a, **k):
        k.setdefault("headers", {}).update(self._h())
        return self.c.put(*a, **k)

    def patch(self, *a, **k):
        k.setdefault("headers", {}).update(self._h())
        return self.c.patch(*a, **k)

    def delete(self, *a, **k):
        k.setdefault("headers", {}).update(self._h())
        return self.c.delete(*a, **k)


@pytest.fixture()
def user(client):
    r = client.post("/api/auth/register", json={"name": "Test User", "email": "Test@Example.com", "password": "Passw0rd!x"})
    assert r.status_code == 201, r.get_json()
    return Authed(client)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_bytes(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()
