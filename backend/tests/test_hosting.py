import pytest
from app.db import database_url
@pytest.mark.parametrize('prefix',['postgres://','postgresql://','postgresql+psycopg://'])
def test_hosting_connection_uses_installed_driver(prefix):
    assert database_url(prefix+'user:password@db:5432/football')=='postgresql+psycopg://user:password@db:5432/football'
def test_sqlite_connection_preserved():
    assert database_url('sqlite:///./football.db')=='sqlite:///./football.db'
