from api import ApiSettings, Application, create_app

application: Application = create_app(
    ApiSettings(TEST_BACKEND="True", LOAD_TEST_DATA=True)
)
app = application.app
