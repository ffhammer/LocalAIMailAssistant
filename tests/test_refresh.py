import pytest
from fastapi.testclient import TestClient

from api import Application
from src.mail_db import MailDB
from src.testing import load_test_messages
from tests.utils import temp_test_dir, test_app

# in here for ruff
test_app
temp_test_dir

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
@pytest.mark.parametrize("mailbox", ["INBOX", "sent"])
async def test_post_update_account(mailbox: str, test_app: Application):
    # Use the app's settings to load test messages.
    messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
    assert mailbox in messages_by_mailbox
    mails = sorted(messages_by_mailbox[mailbox], key=lambda x: x.Date_Sent)

    client = TestClient(test_app.app)

    resp = client.post(f"/accounts/test/update?mailbox={mailbox}")
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
