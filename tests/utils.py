import os

import pytest
from fastapi.testclient import TestClient

from src.api import Application, create_app
from src.models import JobStatus, MailMessage
from src.settings import Settings


@pytest.fixture(scope="function")
def temp_test_dir(tmp_path_factory) -> str:
    d = tmp_path_factory.mktemp("test_db")
    os.environ["TEST_DB_PATH"] = str(d)
    return str(d)


@pytest.fixture(scope="function")
def test_app(temp_test_dir: str) -> Application:
    test_settings = Settings(
        TEST_BACKEND="True",
        TEST_DB_PATH=temp_test_dir,
        LOAD_TEST_DATA=True,
        LOG_LEVEL="DEBUG",
    )
    app = create_app(settings=test_settings)
    return app


def save_mails(test_app: Application, mails: list[MailMessage]):
    db = test_app.context.dbs["test"]
    for mail in mails:
        db.save_email(mail)


def check_job_status(test_app: Application, **filters) -> list[JobStatus]:
    """
    Helper to query the background status endpoint with given filters.
    Returns the JSON response.
    """
    client = TestClient(test_app.app)
    query = "&".join(f"{key}={value}" for key, value in filters.items())
    resp = client.get(f"/background/status?{query}")

    return [JobStatus.model_validate(i) for i in resp.json()]
