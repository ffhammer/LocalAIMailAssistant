from src.api import Application, create_app
from src.settings import Settings

application: Application = create_app(
    Settings(TEST_BACKEND="True", LOAD_TEST_DATA=True)
)
app = application.app
