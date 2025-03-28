import os

import pytest

from api import ApiSettings, Application, MailMessage, create_app

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def temp_test_dir(tmp_path_factory) -> str:
    d = tmp_path_factory.mktemp("test_db")
    os.environ["TEST_DB_PATH"] = str(d)
    return str(d)


@pytest.fixture(scope="function")
def test_app(temp_test_dir: str) -> Application:
    test_settings = ApiSettings(
        TEST_BACKEND="True", TEST_DB_PATH=temp_test_dir, LOAD_TEST_DATA=True
    )
    app = create_app(settings=test_settings)
    return app


def save_mails(test_app: Application, mails: list[MailMessage]):
    db = test_app.context.dbs["test"]
    for mail in mails:
        db.save_email(mail)
