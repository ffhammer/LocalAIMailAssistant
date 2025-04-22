import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api import Application, create_app
from src.models import JobStatus, MailMessage
from src.settings import Settings


def get_test_client(test_app) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=test_app.app), base_url="http://test"
    )


@pytest.fixture(scope="function")
def temp_test_dir(tmp_path_factory) -> str:
    d = tmp_path_factory.mktemp("test_db")
    os.environ["TEST_DB_PATH"] = str(d)
    return str(d)


@pytest_asyncio.fixture(scope="function")
async def test_app(temp_test_dir: str) -> Application:
    test_settings = Settings(
        TEST_BACKEND="True",
        TEST_DB_PATH=temp_test_dir,
        LOAD_TEST_DATA=True,
        LOG_LEVEL="DEBUG",
    )
    app = create_app(settings=test_settings)

    # Start the background manager
    async with app.app.router.lifespan_context(app.app):
        yield app
        app.context.background_task.cancel()


def save_mails(test_app: Application, mails: list[MailMessage]):
    db = test_app.context.dbs["test"]
    for mail in mails:
        db.add_value(mail)


async def check_job_status(client: AsyncClient, **filters) -> list[JobStatus]:
    """
    Helper to query the background status endpoint with given filters.
    Returns the JSON response.
    """
    query = "&".join(f"{key}={value}" for key, value in filters.items())
    resp = await client.get(f"/background/status?{query}")

    return [JobStatus.model_validate(i) for i in resp.json()]
