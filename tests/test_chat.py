import asyncio

import pytest
import pytest_asyncio

from src.models import JOB_TYPE, STATUS, EmailChat, JobStatusSQL, MailMessage
from src.testing import load_test_messages
from tests.utils import (
    check_job_status,
    get_test_client,
    save_mails,
    temp_test_dir,
    test_app,
)

# for formatter explictly include here
test_app
temp_test_dir
pytest_asyncio


@pytest.mark.asyncio
async def test_get_default_chat_when_none_exists(test_app):
    """
    GET /accounts/{account_id}/chats/{message_id} should return a default chat
    for an email without a reply (i.e. no chat exists).
    """
    async with get_test_client(test_app) as client:
        settings = test_app.settings
        messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)

        # Pick a mailbox and an email without Reply_To.
        mailbox = next(iter(messages_by_mailbox))
        save_mails(test_app, messages_by_mailbox[mailbox])

        email = next(
            (m for m in messages_by_mailbox[mailbox] if m.reply_to is None), None
        )
        assert email, "No email found without Reply_To in test data."

        resp = await client.get(f"/accounts/test/chats/{email.message_id}")
        assert resp.status_code == 200

        chat = EmailChat.model_validate(resp.json())
        chat.entries[0].author == email.sender


@pytest.mark.asyncio
@pytest.mark.ollama
async def test_queue_chat_job_via_generate_endpoint(test_app):
    """
    POST /accounts/{account_id}/chats/generate/{message_id} should queue a chat job.
    Then GET /background/status should return a job for that email.
    """
    async with get_test_client(test_app) as client:
        settings = test_app.settings
        messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)

        # Pick an email with a reply (so that generate_email_chat_with_ollama is applicable)
        mailbox = next(iter(messages_by_mailbox))
        email: MailMessage = next(
            (m for m in messages_by_mailbox[mailbox] if m.reply_to is not None), None
        )
        save_mails(test_app, messages_by_mailbox[mailbox])

        assert email, "No email with Reply_To found in test data."
        assert email.reply_to is not None

        # Queue the chat job.
        resp = await client.post(f"/accounts/test/chats/generate/{email.message_id}")
        assert resp.status_code == 200
        job_status = JobStatusSQL.model_validate(resp.json())
        assert job_status.status == STATUS.pending

        while True:
            inprogress = await check_job_status(
                client,
                message_id=email.message_id,
                status=str(STATUS.in_progress),
                job_type=str(JOB_TYPE.chat),
            )
            if inprogress:
                break
            await asyncio.sleep(0.1)

        while True:
            completed = await check_job_status(
                client,
                message_id=email.message_id,
                status=str(STATUS.completed),
                job_type=str(JOB_TYPE.chat),
            )
            if completed:
                print("completed")
                return
            failed = await check_job_status(
                client,
                message_id=email.message_id,
                status=str(STATUS.failed),
                job_type=str(JOB_TYPE.chat),
            )
            if failed:
                print("failed")
                return
            await asyncio.sleep(0.2)


@pytest.mark.asyncio
@pytest.mark.ollama
async def test_queue_chat_jobs_for_all(test_app):
    """
    POST /accounts/{account_id}/chats/generate should queue chat jobs for all emails with a Reply_To.
    Verify that the background status endpoint returns jobs.
    """
    async with get_test_client(test_app) as client:
        messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
        mailbox = next(iter(messages_by_mailbox))
        save_mails(test_app, messages_by_mailbox[mailbox])
        resp = await client.post("/accounts/test/chats/generate")

        assert resp.status_code == 200
        detail = resp.json()["detail"]
        assert "queued" in detail.lower()

        # Wait a moment for jobs to register.
        await asyncio.sleep(1)

        jobs = await check_job_status(client=client, job_type="chat", account_id="test")
        assert any(job.job_type == "chat" for job in jobs)
