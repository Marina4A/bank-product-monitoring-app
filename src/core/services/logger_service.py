from typing import List, Optional
from datetime import datetime
from ..models import LogEntry


class LoggerService:
    """Сервис для работы с логами."""

    def __init__(self, max_logs: int = 1000):
        self._logs: List[LogEntry] = []
        self._max_logs = max_logs

    def add_log(self, level: str, message: str) -> None:
        """Добавляет запись в лог."""
        log_entry = LogEntry(
            id=str(datetime.now().timestamp()),
            timestamp=datetime.now(),
            level=level,
            message=message
        )
        self._logs.insert(0, log_entry)

        # Ограничиваем количество логов
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[:self._max_logs]

    def get_logs(
        self,
        level: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[LogEntry]:
        """
        Получает логи с фильтрацией.

        Args:
            level: Фильтр по уровню ("INFO", "WARNING", "ERROR" или None для всех)
            search_query: Поисковый запрос
            limit: Максимальное количество записей
        """
        logs = self._logs

        if level and level != "ALL":
            logs = [log for log in logs if log.level == level]

        if search_query:
            query = search_query.lower()
            logs = [log for log in logs if query in log.message.lower()]

        if limit:
            logs = logs[:limit]

        return logs

    def clear_logs(self) -> None:
        """Очищает все логи."""
        self._logs.clear()
