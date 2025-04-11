# import pytest
# from fastapi.testclient import TestClient

# from src.api import Application
# from src.database.mail_db import MailDB
# from src.testing import load_test_messages
# from tests.utils import temp_test_dir, test_app

# # in here for ruff
# test_app
# temp_test_dir


# @pytest.mark.asyncio
# @pytest.mark.parametrize("mailbox", ["INBOX", "sent"])
# async def test_post_update_account(mailbox: str, test_app: Application):
#     # Use the app's settings to load test messages.
#     messages_by_mailbox = load_test_messages(test_app.settings.PATH_TO_TEST_DATA)
#     assert mailbox in messages_by_mailbox
#     mails = sorted(messages_by_mailbox[mailbox], key=lambda x: x.date_sent)

#     client = TestClient(test_app.app)

#     resp = client.post(f"/accounts/test/refresh?mailbox={mailbox}")
#     assert resp.status_code == 200
#     stream = []
#     async for line in resp.aiter_lines():
#         if line.startswith("data: "):
#             stream.append(line[len("data: ") :].strip())
#     # Compare by unique message_ids.
#     assert stream == [mail.message_id for mail in mails]

#     context = test_app.context
#     db: MailDB = context.dbs["test"]
#     saved = sorted(db.query_emails(), key=lambda x: x.date_sent)
#     assert [s.message_id for s in saved] == [m.message_id for m in mails]
