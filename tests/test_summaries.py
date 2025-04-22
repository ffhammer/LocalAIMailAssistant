import time

import pytest
from fastapi.testclient import TestClient

from src.models import (
    JOB_TYPE,
    STATUS,
    ChatEntry,
    EmailChat,
    EmailChatSQL,
    JobStatusSQL,
    MailMessage,
)
from src.testing import TEST_ACCOUNT, load_test_messages
from tests.utils import check_job_status, save_mails, temp_test_dir, test_app

test_app
temp_test_dir


def test_get_summary_none_exists(test_app):
    client = TestClient(test_app.app)
    messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
    mailbox = next(iter(messages_by_mailbox))
    save_mails(test_app, messages_by_mailbox[mailbox])

    email = messages_by_mailbox[mailbox][0]
    resp = client.get(f"/accounts/test/summaries/{email.message_id}")
    assert resp.status_code == 200
    assert resp.json() is None


@pytest.mark.ollama
def test_queue_summary_job_via_generate_endpoint(test_app):
    with TestClient(test_app.app) as client:
        messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
        mailbox = next(iter(messages_by_mailbox))
        email: MailMessage = messages_by_mailbox[mailbox][0]
        save_mails(test_app, messages_by_mailbox[mailbox])

        # feed chat
        test_app.context.dbs[TEST_ACCOUNT.name].add_value(
            EmailChatSQL(
                email_message_id=email.message_id,
                authors=[email.sender],
                chat_json=EmailChat(
                    entries=[
                        ChatEntry(
                            author=email.sender,
                            date_sent=email.date_sent,
                            entry_content=email.plain_text,
                        )
                    ],
                    authors=[email.sender],
                ).model_dump_json(),
            )
        )
        time.sleep(0.2)
        resp = client.get(f"/accounts/test/chats/{email.message_id}")
        assert resp.status_code == 200

        resp = client.post(f"/accounts/test/summaries/generate/{email.message_id}")
        assert resp.status_code == 200
        job_status = JobStatusSQL.model_validate(resp.json())
        assert job_status.status == STATUS.pending

        while check_job_status(
            test_app,
            message_id=email.message_id,
            status=str(STATUS.completed),
            job_type=str(JOB_TYPE.summary),
        ) or check_job_status(
            test_app,
            message_id=email.message_id,
            status=str(STATUS.failed),
            job_type=str(JOB_TYPE.summary),
        ):
            time.sleep(1)


@pytest.mark.ollama
def test_queue_summary_jobs_for_all(test_app):
    client = TestClient(test_app.app)
    messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
    mailbox = next(iter(messages_by_mailbox))
    save_mails(test_app, messages_by_mailbox[mailbox])
    resp = client.post("/accounts/test/summaries/generate")

    assert resp.status_code == 200
    detail = resp.json()["detail"]
    assert "queued" in detail.lower()

    time.sleep(1)

    jobs = check_job_status(test_app, job_type="summary", account_id="test")
    assert any(job.job_type == "summary" for job in jobs)
