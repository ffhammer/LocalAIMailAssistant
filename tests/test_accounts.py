from fastapi.testclient import TestClient

from api import Application
from src.testing import TEST_ACCOUNT, load_test_messages
from tests.utils import temp_test_dir, test_app

# in here for ruff
test_app
temp_test_dir


def test_get_accounts(test_app: Application):
    # Expected account list is built from TEST_ACCOUNT
    expected = [
        {
            "account_id": "test",
            "apple_mail_name": TEST_ACCOUNT.apple_mail_name,
            "imap_server": TEST_ACCOUNT.imap_server,
            "user": TEST_ACCOUNT.user,
            "name": TEST_ACCOUNT.user_for_mail,
        }
    ]

    client = TestClient(test_app.app)

    resp = client.get("/accounts")
    assert resp.status_code == 200
    data = resp.json()
    # Compare the expected test account is in the response
    assert data == expected


def test_get_mailboxes_valid_account(test_app: Application):
    # Use the test data to dynamically load mailboxes from test messages
    settings = test_app.settings
    messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)
    expected_mailboxes = list(messages_by_mailbox.keys())
    client = TestClient(test_app.app)

    resp = client.get("/accounts/test/mailboxes")
    assert resp.status_code == 200
    data = resp.json()
    # Assert the returned mailbox list matches expected (order may vary)
    assert set(data) == set(expected_mailboxes)


def test_get_mailboxes_invalid_account(test_app: Application):
    client = TestClient(test_app.app)

    resp = client.get("/accounts/nonexistent/mailboxes")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Account not found"
