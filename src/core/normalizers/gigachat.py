import asyncio
import json
import os
import time
import uuid
import warnings
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

load_dotenv()


class GigaChatNormalizer:
    """
    Класс для нормализации данных с использованием GigaChat API.

    Использует AI для приведения неструктурированных данных
    к строгому JSON формату.
    """

    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_URL = "https://gigachat.devices.sberbank.ru/api/v1"
    MODEL = "GigaChat"

    def __init__(self, auth_key: str | None = None):
        """
        Инициализация нормализатора GigaChat.

        Args:
            auth_key: Authorization key для GigaChat. Если не указан, берется из переменной окружения
        """
        self.auth_key = auth_key or os.getenv("GIGACHAT_AUTH_KEY")
        if not self.auth_key:
            raise ValueError(
                "GIGACHAT_AUTH_KEY не найден. Установите его в .env файле "
                "или передайте напрямую в конструктор."
            )

        self._access_token: str | None = None
        self._token_expires_at: float = 0

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

        Токен действует 30 минут, поэтому кешируем его.

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

        # Retry логика для обработки SSL ошибок
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
                    break

                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)  # Экспоненциальная задержка
                    continue

                raise RuntimeError(
                    f"Ошибка получения токена доступа: {response.status_code} - {response.text}"
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
                    f"SSL/Connection ошибка при получении токена (попытка {attempt + 1}/{max_retries}): {e}"
                ) from e

        if last_error and response.status_code != 200:
            raise last_error

        data = response.json()
        self._access_token = data.get("access_token")

        if not self._access_token:
            raise RuntimeError("Не удалось получить access_token из ответа")

        # Токен действует 30 минут (1800 секунд), устанавливаем время истечения с запасом в 1 минуту
        expires_in = 1800
        self._token_expires_at = time.time() + expires_in - 60

        return self._access_token

    async def _make_api_request(
        self, endpoint: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Выполнение запроса к GigaChat API.

        Args:
            endpoint: Конечная точка API (например, "chat/completions")
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

        # Отключаем проверку SSL для запросов к GigaChat API
        # Retry логика для обработки SSL ошибок
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

    async def normalize(
        self,
        data: Any,
        schema: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        """
        Нормализация данных согласно схеме.

        Args:
            data: Данные для нормализации (dict, list, str)
            schema: JSON схема с описанием полей
            description: Дополнительное описание контекста нормализации

        Returns:
            Нормализованные данные в виде словаря
        """
        prompt = self._build_prompt(data, schema, description)

        payload = {
            "model": self.MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты нормализатор данных. Извлекай и очищай данные согласно схеме. "
                        "Верни ТОЛЬКО чистый JSON (без markdown, комментариев, пояснений). "
                        "Ответ начинается с { и заканчивается }.\n\n"
                        "ВСЕГДА соблюдай единообразное форматирование:\n"
                        "• Суммы кредитов: КРИТИЧЕСКИ ВАЖНО - ВСЕГДА указывай единицы измерения (млн ₽, тыс ₽) "
                        "и символ ₽. НЕ используй неинформативные форматы вроде '0 - 30'. "
                        "Вместо этого: 'от 0 до 30 млн ₽' или 'от 0 до 30 тыс ₽' с единицами!\n"
                        "• Денежные суммы (обслуживание, комиссия): ВСЕГДА с символом ₽ (например: '0 ₽', '500 ₽', 'до 3 000 ₽')\n"
                        "• Процентные ставки: ВСЕГДА с символом % и информативным описанием (например: 'от 0% до 10% годовых', 'до 15%', '5% годовых')\n"
                        "• Диапазоны ставок: используй формат 'от X% до Y%' или 'X–Y%' вместо 'X-Y' или 'X Y'\n"
                        "• Периоды времени: указывай единицы (дни, месяцы, годы) - например: 'до 200 дней', 'на 36 месяцев'\n"
                        "• Бесплатные услуги: ВСЕГДА используй '0 ₽' (НЕ 'Бесплатно', 'Бесплатное обслуживание' и т.д.)"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,  # Низкая температура для более детерминированных результатов
        }

        response_text = ""
        try:
            response = await self._make_api_request("chat/completions", payload)

            # Извлекаем текст ответа
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("Пустой ответ от GigaChat API")

            response_text = choices[0].get("message", {}).get("content", "").strip()

            if not response_text:
                raise RuntimeError("Пустой контент в ответе от GigaChat API")

            # Проверка на предупреждения/ограничения от GigaChat
            if (
                "не обладает собственным мнением" in response_text
                or "ограничены" in response_text.lower()
            ):
                raise ValueError(
                    f"GigaChat вернул предупреждение вместо JSON: {response_text[:200]}"
                )

            # Удаление markdown форматирования, если есть
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # Проверка, что ответ начинается с JSON
            if not response_text.startswith("{") and not response_text.startswith("["):
                raise ValueError(
                    f"Ответ от GigaChat не является JSON: {response_text[:200]}"
                )

            # Парсинг JSON
            normalized_data = json.loads(response_text)
            return normalized_data

        except json.JSONDecodeError as e:
            raise ValueError(
                f"Не удалось распарсить JSON ответ от AI: {e}\n"
                f"Ответ: {response_text[:500] if response_text else 'Пустой ответ'}"
            )
        except Exception as e:
            error_msg = f"Ошибка при нормализации данных: {e}"
            if response_text:
                error_msg += f"\nОтвет: {response_text[:200]}"
            raise RuntimeError(error_msg) from e

    def _build_prompt(self, data: Any, schema: dict[str, Any], description: str) -> str:
        """
        Построение промпта для нормализации.

        Args:
            data: Данные для нормализации
            schema: JSON схема
            description: Описание контекста

        Returns:
            Сформированный промпт
        """
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
        data_json = json.dumps(data, ensure_ascii=False, indent=2)

        context = (
            description
            if description
            else "Нормализация данных кредитных продуктов банка"
        )

        prompt = f"""Нормализуй данные по схеме.

Контекст: {context}

Схема:
{schema_json}

Данные:
{data_json}

ПРАВИЛА НОРМАЛИЗАЦИИ:
1. СУММЫ КРЕДИТОВ (поле "price"):
   • КРИТИЧЕСКИ ВАЖНО: ВСЕГДА указывай единицы измерения и символ ₽!
   • Если в исходных данных только числа без единиц (например, "0 - 30"), определи контекст:
     * Для кредитов обычно это миллионы рублей → "от 0 до 30 млн ₽"
     * Для малых кредитов → "от 0 до 30 тыс ₽" или "от 0 до 30 000 ₽"
   • Формат для больших сумм: "от 0 до 30 млн ₽", "от 1 млн ₽ до 10 млн ₽", "до 50 млн ₽"
   • Формат для средних сумм: "от 100 000 ₽ до 500 000 ₽", "от 50 тыс ₽ до 1 млн ₽"
   • НЕ используй: "0 - 30", "0-30 млн", "0 до 30" (неинформативно!)
   • Используй: "от 0 до 30 млн ₽", "от 1 млн ₽ до 10 млн ₽" (информативно!)
   • Если указано "Индивидуально" → используй "Индивидуально"

2. ДЕНЕЖНЫЕ СУММЫ (обслуживание, комиссия, кешбэк):
   • ВСЕГДА добавляй символ рубля ₽ в конце суммы
   • Формат: "0 ₽", "500 ₽", "до 3 000 ₽", "от 1 000 ₽ до 5 000 ₽"
   • Если указано "бесплатно", "Бесплатно", "Бесплатное обслуживание" и т.д. → ВСЕГДА "0 ₽" (НЕ "Бесплатно"!)
   • Если диапазон: "от X ₽ до Y ₽" или "X–Y ₽"
   • КРИТИЧЕСКИ ВАЖНО: для колонки "Комиссия" ВСЕГДА используй формат с ₽, даже если услуга бесплатная → "0 ₽"

3. ПРОЦЕНТНЫЕ СТАВКИ:
   • ВСЕГДА добавляй символ % и уточнение "годовых" где применимо
   • Формат: "от 5% до 10% годовых", "до 15% годовых", "5% годовых"
   • Диапазоны: "от X% до Y% годовых" или "X–Y% годовых" (НЕ "X-Y" или "X Y")
   • Если только одно значение: "до 15%" или "15% годовых"

4. ПЕРИОДЫ ВРЕМЕНИ (льготный период, срок):
   • ВСЕГДА указывай единицы измерения: дни, месяцы, годы
   • Формат: "до 200 дней", "на 36 месяцев", "до 10 лет"
   • Без процентов: "до 200 дней без процентов" (если указано)

5. ОБЩИЕ ПРАВИЛА:
   • Извлеки значения полей, убери лишний рекламный текст
   • Сохрани информативность:
     * Вместо "0-10" → "от 0% до 10% годовых"
     * Вместо "0 - 30" → "от 0 до 30 млн ₽" (с единицами измерения!)
   • Единообразие: все одинаковые типы данных в одном формате
   • Отсутствующие поля → null
   • Ответ: ТОЛЬКО JSON объект ({{...}}), без markdown и пояснений"""

        return prompt

    async def normalize_batch(
        self,
        items: list[Any],
        schema: dict[str, Any],
        description: str = "",
    ) -> list[dict[str, Any]]:
        """
        Нормализация списка элементов.

        Args:
            items: Список элементов для нормализации
            schema: JSON схема для каждого элемента
            description: Описание контекста

        Returns:
            Список нормализованных элементов
        """
        normalized_items = []

        for idx, item in enumerate(items, 1):
            try:
                print(f"Нормализация элемента {idx}/{len(items)}...")
                normalized = await self.normalize(item, schema, description)
                normalized_items.append(normalized)

                # Задержка между запросами для избежания rate limiting
                if idx < len(items):
                    await asyncio.sleep(1.5)  # 1.5 секунды между запросами

            except Exception as e:
                print(f"Ошибка при нормализации элемента {idx}: {e}")
                # Добавляем элемент с ошибкой для отслеживания
                normalized_items.append({"error": str(e), "original_data": item})

                # Задержка даже при ошибке
                if idx < len(items):
                    await asyncio.sleep(1.0)

        return normalized_items


CREDIT_PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Название кредитного продукта",
        },
        "subtitle": {
            "type": "string",
            "description": "Краткое описание продукта",
        },
        "price": {
            "type": "string",
            "description": (
                "Сумма кредита. КРИТИЧЕСКИ ВАЖНО: ВСЕГДА указывай единицы измерения и символ ₽!\n\n"
                "ПРАВИЛА ФОРМАТИРОВАНИЯ:\n"
                "• Для больших сумм (миллионы/миллиарды): ВСЕГДА указывай 'млн ₽' или 'млрд ₽'\n"
                "  Например: 'от 0 до 30 млн ₽', 'от 1 млн ₽ до 5 млрд ₽', 'до 50 млн ₽'\n"
                "• Для средних сумм: 'тыс ₽' или точное число с ₽\n"
                "  Например: 'от 100 000 ₽ до 500 000 ₽', 'от 50 тыс ₽ до 1 млн ₽'\n"
                "• Если в исходных данных только числа без единиц (например, '0 - 30'), "
                "определи контекст из названия/описания продукта:\n"
                "  - Для кредитов обычно это миллионы → 'от 0 до 30 млн ₽'\n"
                "  - Для небольших кредитов → 'от 0 до 30 тыс ₽' или 'от 0 до 30 000 ₽'\n"
                "• НЕ используй неинформативные форматы: '0 - 30', '0-30 млн', '0 до 30'\n"
                "• ВСЕГДА используй информативный формат: 'от 0 до 30 млн ₽', 'от 1 млн ₽ до 5 млрд ₽'\n"
                "• Если указано 'Индивидуально' или 'По договоренности' → используй 'Индивидуально'\n\n"
                "Примеры правильных форматов:\n"
                "- 'от 0 до 30 млн ₽' (вместо '0 - 30')\n"
                "- 'от 1 млн ₽ до 10 млн ₽' (вместо '1-10 млн')\n"
                "- 'до 50 млн ₽'\n"
                "- 'от 100 000 ₽ до 5 млн ₽'\n"
                "- 'Индивидуально'"
            ),
        },
        "term": {
            "type": "string",
            "description": (
                "Срок кредита и условия. ВАЖНО: ВСЕГДА указывай единицы измерения времени!\n"
                "Формат: 'на 36 месяцев', 'до 10 лет', 'от 12 до 60 месяцев', 'до 5 лет без залога'.\n"
                "НЕ используй сокращения без единиц вроде '36' или 'до 10'. "
                "Убери лишний рекламный текст, но сохрани информативность о сроке и условиях."
            ),
        },
        "link": {
            "type": "string",
            "description": "URL ссылка на страницу продукта",
        },
    },
    "required": ["title"],
}

DEBIT_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Название дебетовой карты",
        },
        "description": {
            "type": "string",
            "description": "Краткое описание карты",
        },
        "badge": {
            "type": "string",
            "description": "Бейдж карты (например: 'Лимитированный тираж'), если есть",
        },
        "features": {
            "type": "array",
            "description": (
                "Список особенностей карты. Каждый элемент содержит 'value' (значение) "
                "и 'label' (описание). ВАЖНО: Форматируй значения единообразно!\n"
                "• Денежные суммы (комиссия, обслуживание): ВСЕГДА с символом ₽ (например: '0 ₽', '500 ₽', 'до 3 000 ₽')\n"
                "  КРИТИЧЕСКИ ВАЖНО: если услуга бесплатная ('бесплатно', 'Бесплатно', 'Бесплатное обслуживание') → ВСЕГДА '0 ₽' (НЕ 'Бесплатно'!)\n"
                "• Процентные ставки: ВСЕГДА с % и уточнением (например: 'от 5% до 10% годовых', 'до 15% годовых')\n"
                "• Периоды: с единицами измерения (например: 'до 200 дней', 'на 36 месяцев')\n"
                "Примеры: [{'value': 'до 3 000 ₽', 'label': 'Кешбэк за покупки ежемесячно'}, "
                "{'value': '0 ₽', 'label': 'Выпуск и обслуживание'}, "
                "{'value': 'от 0% до 10% годовых', 'label': 'Процентная ставка'}, "
                "{'value': 'до 200 дней', 'label': 'Без процентов'}]"
            ),
            "items": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": (
                            "Значение особенности. ОБЯЗАТЕЛЬНО форматируй единообразно:\n"
                            "- Деньги (комиссия, обслуживание): ВСЕГДА с ₽ ('0 ₽', '500 ₽', 'до 3 000 ₽')\n"
                            "  Если бесплатно → ВСЕГДА '0 ₽' (НЕ 'Бесплатно'!)\n"
                            "- Проценты: ВСЕГДА с % и 'годовых' ('от 5% до 10% годовых', 'до 15% годовых')\n"
                            "- Периоды: с единицами измерения ('до 200 дней', 'на 36 месяцев')\n"
                            "НЕ используй сокращения вроде '0-10', вместо этого 'от 0% до 10% годовых'."
                        ),
                    },
                    "label": {
                        "type": "string",
                        "description": "Описание особенности (например: 'Кешбэк', 'Обслуживание', 'Льготный период')",
                    },
                },
                "required": ["value", "label"],
            },
        },
        "apply_link": {
            "type": "string",
            "description": "URL ссылка на оформление карты",
        },
        "details_link": {
            "type": "string",
            "description": "URL ссылка на страницу с подробностями о карте",
        },
    },
    "required": ["title"],
}

CREDIT_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Название кредитной карты",
        },
        "description": {
            "type": "string",
            "description": "Краткое описание карты",
            "nullable": True,
        },
        "features": {
            "type": "array",
            "description": (
                "Список особенностей карты. Каждый элемент содержит 'value' (значение) "
                "и 'label' (описание). ВАЖНО: Форматируй значения единообразно!\n"
                "• Денежные суммы (комиссия, обслуживание): ВСЕГДА с символом ₽ (например: '0 ₽', '500 ₽', 'до 3 000 ₽')\n"
                "  КРИТИЧЕСКИ ВАЖНО: если услуга бесплатная ('бесплатно', 'Бесплатно', 'Бесплатное обслуживание') → ВСЕГДА '0 ₽' (НЕ 'Бесплатно'!)\n"
                "• Процентные ставки: ВСЕГДА с % и уточнением 'годовых' (например: 'от 5% до 10% годовых', 'до 15% годовых')\n"
                "• Периоды: с единицами измерения (например: 'до 200 дней', 'на 36 месяцев')\n"
                "• Льготные периоды: 'до 200 дней без процентов' (если применимо)\n"
                "НЕ используй непонятные сокращения вроде '0-10' или '10 15'. "
                "Вместо этого используй информативные форматы: 'от 0% до 10% годовых'.\n"
                "Примеры: [{'value': 'до 200 дней без процентов', 'label': 'Льготный период'}, "
                "{'value': '0 ₽', 'label': 'Обслуживание и доставка карты'}, "
                "{'value': 'от 5% до 10% годовых', 'label': 'Процентная ставка'}, "
                "{'value': 'до 15% годовых', 'label': 'Кешбэк рублями в категориях'}]"
            ),
            "items": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": (
                            "Значение особенности. ОБЯЗАТЕЛЬНО форматируй единообразно:\n"
                            "- Деньги (комиссия, обслуживание): ВСЕГДА с ₽ ('0 ₽', '500 ₽', 'до 3 000 ₽', 'от 500 ₽ до 1 000 ₽')\n"
                            "  Если бесплатно → ВСЕГДА '0 ₽' (НЕ 'Бесплатно', 'Бесплатное обслуживание' и т.д.!)\n"
                            "- Ставки: ВСЕГДА с % и 'годовых' где применимо ('от 0% до 10% годовых', 'до 15% годовых', '5% годовых')\n"
                            "- Периоды: с единицами ('до 200 дней', 'на 36 месяцев', 'до 10 лет')\n"
                            "НЕ используй: '0-10', '10 15', 'X-Y' - вместо этого: 'от X% до Y% годовых' или 'X–Y% годовых'"
                        ),
                    },
                    "label": {
                        "type": "string",
                        "description": "Описание особенности (например: 'Без процентов', 'Обслуживание', 'Кешбэк', 'Льготный период')",
                    },
                },
                "required": ["value", "label"],
            },
            "nullable": True,
        },
        "apply_link": {
            "type": "string",
            "description": "URL ссылка для оформления карты",
            "format": "uri",
            "nullable": True,
        },
        "details_link": {
            "type": "string",
            "description": "URL ссылка на страницу с подробностями о карте",
            "format": "uri",
            "nullable": True,
        },
    },
    "required": ["title"],
}
