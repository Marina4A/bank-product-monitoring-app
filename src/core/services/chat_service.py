"""Сервис для общения с AI аналитиком через GigaChat."""

import asyncio
import json
import os
import time
import uuid
import warnings
from typing import Any, List, Optional

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

load_dotenv()


class ChatService:
    """Сервис для общения с AI аналитиком банковских продуктов через GigaChat."""

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1"
    MODEL = "GigaChat"

    SYSTEM_PROMPT = """Ты - AI аналитик банковских продуктов. Твоя задача помогать пользователю анализировать и сравнивать банковские продукты (кредиты, дебетовые карты, кредитные карты, вклады).

ПРАВИЛА ОБЩЕНИЯ:
1. Будь профессиональным, вежливым и полезным
2. Отвечай на русском языке
3. Дай конкретные рекомендации на основе данных о банковских продуктах
4. Если информации недостаточно для ответа, честно об этом скажи
5. Используй конкретные цифры (ставки, суммы) при сравнении продуктов
6. Предлагай несколько вариантов, если это уместно
7. Объясняй финансовые термины простым языком
8. Будь кратким, но информативным - избегай лишних объяснений
9. Если пользователь спрашивает о конкретном банке или продукте, используй доступные данные
10. Помогай с выбором продукта на основе целей пользователя (например: "Мне нужен кредит на 500 тысяч" - предложи подходящие варианты)
11. ВАЖНО: Отвечай простым текстом БЕЗ markdown разметки. Не используй символы *, _, #, ```, [](), и другие элементы markdown. Пиши обычный текст.

КОНТЕКСТ ДАННЫХ:
У тебя есть доступ к данным о банковских продуктах различных банков (Альфа-Банк, ТБанк, ВТБ, Газпромбанк, Сбербанк и другие).
Данные включают: ставки, суммы, сроки, условия, кешбэк, льготные периоды, комиссии.

НАЧНИ ОБЩЕНИЕ:
Поприветствуй пользователя и предложи помощь в выборе банковского продукта."""

    def __init__(self, auth_key: Optional[str] = None):
        """
        Инициализация сервиса чата.

        Args:
            auth_key: Authorization key для GigaChat. Если не указан, берется из переменной окружения
        """
        self.auth_key = auth_key or os.getenv("GIGACHAT_AUTH_KEY")
        if not self.auth_key:
            raise ValueError(
                "GIGACHAT_AUTH_KEY не найден. Установите его в .env файле "
                "или передайте напрямую в конструктор."
            )

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # История сообщений для контекста
        self._message_history: List[dict[str, Any]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]

        # Настройка сессии с retry для обработки SSL ошибок
        self._session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    async def _get_access_token(self) -> str:
        """
        Получение токена доступа (с кешированием).

        Returns:
            Access token для авторизации запросов
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        rq_uid = str(uuid.uuid4())

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": rq_uid,
            "Authorization": f"Basic {self.auth_key}",
        }

        payload = {"scope": "GIGACHAT_API_PERS"}

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self._session.post(
                        self.OAUTH_URL,
                        headers=headers,
                        data=payload,
                        verify=False,
                        timeout=30,
                    ),
                )

                if response.status_code == 200:
                    data = response.json()
                    self._access_token = data.get("access_token")
                    expires_in = data.get("expires_at", 1800) - int(time.time())
                    self._token_expires_at = time.time() + expires_in - 60
                    if self._access_token:
                        return self._access_token

                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

                raise RuntimeError(
                    f"Ошибка получения токена: {response.status_code} - {response.text}"
                )

            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"SSL/Connection ошибка при получении токена (попытка {attempt + 1}/{max_retries}): {e}"
                ) from e

        if last_error:
            raise last_error

        raise RuntimeError("Не удалось получить access_token")

    async def _make_api_request(
        self, endpoint: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Выполнение запроса к GigaChat API.

        Args:
            endpoint: Конечная точка API
            payload: Тело запроса

        Returns:
            Ответ от API в виде словаря
        """
        access_token = await self._get_access_token()

        url = f"{self.API_URL}/{endpoint}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self._session.post(
                        url, headers=headers, json=payload, verify=False, timeout=60
                    ),
                )

                if response.status_code == 200:
                    return response.json()

                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue

                raise RuntimeError(
                    f"Ошибка запроса к GigaChat API: {response.status_code} - {response.text}"
                )

            except (
                requests.exceptions.SSLError,
                requests.exceptions.ConnectionError,
            ) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"SSL/Connection ошибка при запросе к API (попытка {attempt + 1}/{max_retries}): {e}"
                ) from e

        if last_error:
            raise last_error

        raise RuntimeError("Не удалось выполнить запрос к GigaChat API")

    async def send_message(
        self, user_message: str, products_context: Optional[List[Any]] = None
    ) -> str:
        """
        Отправляет сообщение пользователя AI и получает ответ.

        Args:
            user_message: Сообщение пользователя
            products_context: Список банковских продуктов для контекста (опционально)

        Returns:
            Ответ от AI
        """
        # Добавляем сообщение пользователя в историю
        self._message_history.append({"role": "user", "content": user_message})

        # Если есть контекст продуктов, добавляем его к сообщению
        if products_context:
            context_text = self._format_products_context(products_context)
            # Обновляем последнее сообщение пользователя с контекстом
            self._message_history[-1]["content"] = f"{user_message}\n\nКонтекст данных:\n{context_text}"

        # Формируем запрос к API
        payload = {
            "model": self.MODEL,
            "messages": self._message_history,
            "temperature": 0.7,
            "max_tokens": 1000,
        }

        try:
            response = await self._make_api_request("chat/completions", payload)
            
            # Извлекаем ответ от AI
            # GigaChat API может возвращать ответы в разных форматах
            assistant_message = ""
            if "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                if "message" in choice:
                    assistant_message = choice["message"].get("content", "")
                elif "delta" in choice and "content" in choice["delta"]:
                    # Стриминг ответа (если используется)
                    assistant_message = choice["delta"]["content"]
            
            if not assistant_message:
                # Пробуем альтернативный формат ответа
                if "content" in response:
                    assistant_message = response["content"]
                elif "text" in response:
                    assistant_message = response["text"]
            
            if assistant_message and assistant_message.strip():
                # Удаляем markdown разметку из ответа
                cleaned_message = self._remove_markdown(assistant_message)
                # Добавляем очищенный ответ AI в историю
                self._message_history.append({"role": "assistant", "content": cleaned_message})
                return cleaned_message
            else:
                error_msg = "AI не вернул ответ. Возможно, проблема с форматом ответа API."
                # Не добавляем ошибку в историю, чтобы не засорять контекст
                return error_msg

        except Exception as e:
            error_msg = f"Ошибка при общении с AI: {str(e)}"
            # Не добавляем ошибку в историю, чтобы не засорять контекст
            return error_msg

    def _remove_markdown(self, text: str) -> str:
        """
        Удаляет markdown разметку из текста.

        Args:
            text: Текст с markdown разметкой

        Returns:
            Очищенный текст без markdown
        """
        import re

        # Удаляем блоки кода (```language ... ``` или ``` ... ```)
        text = re.sub(r'```[\w]*\n?', '', text)
        text = re.sub(r'```', '', text)

        # Удаляем инлайн код (`...`)
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Удаляем заголовки (#, ##, ###, и т.д.)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Удаляем жирный текст (**текст** или __текст__)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)

        # Удаляем курсив (*текст* или _текст_)
        text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'\1', text)
        text = re.sub(r'(?<!_)_([^_]+?)_(?!_)', r'\1', text)

        # Удаляем ссылки [текст](url) -> текст
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Удаляем изображения ![alt](url)
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)

        # Удаляем зачеркнутый текст (~~текст~~)
        text = re.sub(r'~~([^~]+)~~', r'\1', text)

        # Удаляем горизонтальные линии (---, ***, ___) в отдельной строке
        text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)

        # Удаляем списки (маркированные - и *, нумерованные 1. 2. и т.д.)
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Удаляем таблицы (| заголовок | заголовок | и |---|)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Пропускаем строки с разделителями таблиц (|---|---|)
            if re.match(r'^\s*\|[-:\s|]+\|\s*$', line):
                continue
            # Очищаем строки таблиц от символов |
            if '|' in line and line.strip().startswith('|'):
                # Заменяем разделители таблиц пробелами
                cleaned_line = re.sub(r'\|\s*', ' ', line).strip()
                if cleaned_line:
                    cleaned_lines.append(cleaned_line)
            else:
                cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)

        # Удаляем лишние пробелы и переносы строк
        text = re.sub(r'\n{3,}', '\n\n', text)  # Максимум 2 переноса подряд
        text = text.strip()

        return text

    def _format_products_context(self, products: List[Any]) -> str:
        """
        Форматирует список продуктов для добавления в контекст сообщения.

        Args:
            products: Список банковских продуктов

        Returns:
            Отформатированный текст с информацией о продуктах
        """
        if not products:
            return "Нет доступных данных о продуктах."

        context_lines = []
        context_lines.append(f"Доступно {len(products)} банковских продуктов:\n")

        # Ограничиваем количество продуктов для контекста (первые 20)
        products_for_context = products[:20]

        for idx, product in enumerate(products_for_context, 1):
            product_info = f"{idx}. {product.bank} - {product.product}"
            if product.category:
                product_info += f" ({product.category.value})"
            if product.rate_min > 0 or product.rate_max > 0:
                if product.rate_min == product.rate_max:
                    product_info += f", ставка: {product.rate_min}%"
                else:
                    product_info += f", ставка: {product.rate_min}-{product.rate_max}%"
            if product.amount_min > 0 or product.amount_max > 0:
                if product.amount_min == product.amount_max:
                    product_info += f", сумма: {product.amount_min:,.0f} ₽"
                else:
                    product_info += f", сумма: {product.amount_min:,.0f} - {product.amount_max:,.0f} ₽"
            if product.cashback:
                product_info += f", кешбэк: {product.cashback}"
            if product.grace_period:
                product_info += f", льготный период: {product.grace_period}"
            if product.commission:
                product_info += f", комиссия: {product.commission}"
            
            context_lines.append(product_info)

        if len(products) > 20:
            context_lines.append(f"\n... и еще {len(products) - 20} продуктов")

        return "\n".join(context_lines)

    def clear_history(self):
        """Очищает историю сообщений, оставляя только системный промпт."""
        self._message_history = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]

    def get_welcome_message(self) -> str:
        """
        Возвращает приветственное сообщение от AI.

        Returns:
            Приветственное сообщение
        """
        return (
            "Привет! Я AI аналитик банковских продуктов. "
            "Я помогу тебе выбрать подходящий кредит, дебетовую или кредитную карту, "
            "сравнить условия разных банков и найти лучшие предложения. "
            "Задавай вопросы, и я помогу с выбором!"
        )
