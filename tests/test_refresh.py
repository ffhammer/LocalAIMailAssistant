import pytest

from src.api import Application
from src.testing import load_test_messages
from tests.utils import get_test_client, temp_test_dir, test_app

# in here for ruff
test_app
temp_test_dir


@pytest.mark.asyncio
@pytest.mark.parametrize("mailbox", ["INBOX", "sent"])
async def test_post_update_account(mailbox: str, test_app: Application):
    # Use the app's settings to load test messages.
    messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
    assert mailbox in messages_by_mailbox
    mails = sorted(messages_by_mailbox[mailbox], key=lambda x: x.date_sent)

    async with get_test_client(test_app) as client:
        resp = await client.post(f"/accounts/test/refresh?mailbox={mailbox}")
        assert resp.status_code == 200

        assert resp.json() == {"status": "sync started"}
