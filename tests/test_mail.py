import pytest
from fastapi.testclient import TestClient

from src.testing import load_test_messages
from tests.utils import save_mails, temp_test_dir, test_app

# in here for ruff
test_app
temp_test_dir


# GET /accounts/{account_id}/mailboxes/{mailbox}/emails
@pytest.mark.ollama
def test_list_emails(test_app):
    settings = test_app.settings
    # Dynamically load expected test messages
    messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)
    # For the "test" account, ensure we have at least one mailbox
    assert messages_by_mailbox, "No mailboxes found in test data."
    # Pick one mailbox (for example, the first)
    mailbox = list(messages_by_mailbox.keys())[0]
    expected_emails = messages_by_mailbox[mailbox]

    save_mails(test_app=test_app, mails=expected_emails)

    client = TestClient(test_app.app)

    resp = client.get(f"/accounts/test/mailboxes/{mailbox}/emails")
    assert resp.status_code == 200
    data = resp.json()
    returned_ids = sorted(email["message_id"] for email in data)
    expected_ids = sorted(email.message_id for email in expected_emails)
    assert returned_ids == expected_ids


# GET /accounts/{account_id}/mailboxes/{mailbox}/emails with filtering
@pytest.mark.ollama
def test_list_emails_filtering(test_app):
    settings = test_app.settings
    messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)
    mailbox = list(messages_by_mailbox.keys())[0]
    expected_emails = sorted(messages_by_mailbox[mailbox], key=lambda x: x.date_sent)
    if len(expected_emails) < 2:
        pytest.skip("Not enough emails to test filtering.")
    from_date = expected_emails[1].date_sent
    to_date = expected_emails[-2].date_sent
    filtered_expected = [
        email for email in expected_emails if from_date < email.date_sent < to_date
    ]

    save_mails(test_app=test_app, mails=expected_emails)

    client = TestClient(test_app.app)

    # Use ISO format for query parameters
    url = f"/accounts/test/mailboxes/{mailbox}/emails?from_date={from_date.isoformat()}&to_date={to_date.isoformat()}"
    resp = client.get(url)
    assert resp.status_code == 200
    data = resp.json()
    returned_ids = sorted(email["message_id"] for email in data)
    expected_ids = sorted(email.message_id for email in filtered_expected)
    assert returned_ids == expected_ids


# GET /accounts/{account_id}/emails/{message_id}
@pytest.mark.ollama
def test_get_email_details_valid(test_app):
    settings = test_app.settings
    messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)
    mailbox = list(messages_by_mailbox.keys())[0]
    email = messages_by_mailbox[mailbox][0]

    save_mails(test_app=test_app, mails=messages_by_mailbox[mailbox])

    client = TestClient(test_app.app)

    resp = client.get(f"/accounts/test/emails/{email.message_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["message_id"] == email.message_id


@pytest.mark.ollama
def test_get_email_details_invalid(test_app):
    client = TestClient(test_app.app)

    resp = client.get("/accounts/test/emails/invalid_id")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Email not found"
