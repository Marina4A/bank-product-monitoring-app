"""Конфигурация приложения с загрузкой переменных окружения."""

import os
from typing import Optional

from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()


class DatabaseConfig:
    """Конфигурация подключения к базе данных PostgreSQL."""

    def __init__(self):
        """Инициализация конфигурации из переменных окружения."""
        self.host: str = os.getenv("DB_HOST", "localhost")
        self.port: int = int(os.getenv("DB_PORT", "5432"))
        self.database: str = os.getenv("DB_NAME", "bank_monitor")
        self.user: str = os.getenv("DB_USER", "postgres")
        self.password: str = os.getenv("DB_PASSWORD", "postgres")

    @property
    def database_url(self) -> str:
        """Возвращает URL подключения к БД."""
        return (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
        )

    def validate(self) -> bool:
        """
        Проверяет корректность конфигурации.

        Returns:
            True если конфигурация корректна, иначе False
        """
        if not all([self.host, self.database, self.user]):
            return False
        return True


class AppConfig:
    """Общая конфигурация приложения."""

    def __init__(self):
        """Инициализация конфигурации."""
        self.database = DatabaseConfig()

        # Настройки парсинга
        self.parsing_timeout: float = float(os.getenv("PARSING_TIMEOUT", "30.0"))
        self.parsing_retries: int = int(os.getenv("PARSING_RETRIES", "3"))
        self.parsing_headless: bool = (
            os.getenv("PARSING_HEADLESS", "true").lower() == "true"
        )

        # Настройки обновления данных
        self.auto_refresh_interval_minutes: int = int(
            os.getenv("AUTO_REFRESH_INTERVAL_MINUTES", "360")
        )

        # GigaChat API (для нормализации)
        self.gigachat_auth_key: Optional[str] = os.getenv("GIGACHAT_AUTH_KEY")


# Глобальный экземпляр конфигурации
config = AppConfig()
