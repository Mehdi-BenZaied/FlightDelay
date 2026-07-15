import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    API_V1_STR = os.getenv("API_V1_STR", "/api/v1")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///flight_delay.db",
    )

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))

    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")


settings = Settings()