import os

import pytest
from httpx import ASGITransport, AsyncClient

from api import ApiSettings, Application, create_app
from src.mail_db import MailDB
from src.testing import load_test_messages

pytestmark = pytest.mark.asyncio


# Function-scoped temp folder fixture.
@pytest.fixture(scope="function")
def temp_test_dir(tmp_path_factory) -> str:
    d = tmp_path_factory.mktemp("test_db")
    os.environ["TEST_DB_PATH"] = str(d)
    return str(d)


# Function-scoped app fixture.
@pytest.fixture(scope="function")
def test_app(temp_test_dir: str) -> Application:
    test_settings = ApiSettings(
        TEST_BACKEND="True", TEST_DB_PATH=temp_test_dir, LOAD_TEST_DATA=True
    )
    app = create_app(settings=test_settings)
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("mailbox", ["INBOX", "sent"])
async def test_post_update_account(mailbox: str, test_app: Application):
    # Use the app's settings to load test messages.
    messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
    assert mailbox in messages_by_mailbox
    mails = sorted(messages_by_mailbox[mailbox], key=lambda x: x.Date_Sent)

    async with AsyncClient(
        transport=ASGITransport(app=test_app.app), base_url="http://test"
    ) as ac:
        resp = await ac.post(f"/accounts/test/update?mailbox={mailbox}")
        assert resp.status_code == 200
        stream = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                stream.append(line[len("data: ") :].strip())
        # Compare by unique Message_IDs.
        assert stream == [mail.Message_ID for mail in mails]

    context = test_app.context
    db: MailDB = context.dbs["test"]
    saved = sorted(db.query_emails(), key=lambda x: x.Date_Sent)
    assert [s.Message_ID for s in saved] == [m.Message_ID for m in mails]
