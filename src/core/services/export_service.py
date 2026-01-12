from typing import List
from pathlib import Path
from ..models import BankProduct


class ExportService:
    """Сервис для экспорта данных."""

    async def export_to_csv(self, products: List[BankProduct], file_path: Path) -> None:
        """
        Экспортирует продукты в CSV файл.
        TODO: Реализовать экспорт в CSV.
        """
        import csv

        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ID', 'Банк', 'Продукт', 'Категория', 'Ставка мин', 'Ставка макс',
                'Сумма мин', 'Сумма макс', 'Срок', 'Валюта', 'Confidence', 'Дата сбора'
            ])

            for product in products:
                writer.writerow([
                    product.id,
                    product.bank,
                    product.product,
                    product.category.value,
                    product.rate_min,
                    product.rate_max,
                    product.amount_min,
                    product.amount_max,
                    product.term,
                    product.currency.value,
                    product.confidence.value,
                    product.collected_at.isoformat(),
                ])

    async def export_to_excel(self, products: List[BankProduct], file_path: Path) -> None:
        """
        Экспортирует продукты в Excel файл.
        Использует pandas для экспорта в Excel.
        """
        import pandas as pd
        from datetime import datetime

        # Подготавливаем данные для DataFrame
        data = []
        for product in products:
            data.append({
                'ID': product.id,
                'Банк': product.bank,
                'Продукт': product.product,
                'Категория': product.category.value,
                'Ставка мин (%)': product.rate_min,
                'Ставка макс (%)': product.rate_max,
                'Сумма мин': product.amount_min,
                'Сумма макс': product.amount_max,
                'Срок': product.term or "",
                'Валюта': product.currency.value,
                'Confidence': product.confidence.value,
                'Льготный период': product.grace_period or "",
                'Кешбэк': product.cashback or "",
                'Комиссия': product.commission or "",
                'Дата сбора': product.collected_at.isoformat() if product.collected_at else "",
            })

        df = pd.DataFrame(data)
        
        # Экспортируем в Excel
        # Пробуем использовать openpyxl (предпочтительный вариант)
        try:
            df.to_excel(file_path, index=False, engine='openpyxl')
        except ImportError:
            # Если openpyxl нет, используем xlsxwriter
            try:
                df.to_excel(file_path, index=False, engine='xlsxwriter')
            except ImportError:
                # Если ни один из движков не доступен, выбрасываем ошибку
                raise ImportError(
                    "Для экспорта в Excel требуется библиотека openpyxl. "
                    "Установите: pip install openpyxl или uv add openpyxl"
                )
        except Exception as e:
            # Обрабатываем другие ошибки (например, проблемы с записью файла)
            raise RuntimeError(f"Ошибка при экспорте в Excel: {str(e)}") from e

    async def export_to_json(self, products: List[BankProduct], file_path: Path) -> None:
        """
        Экспортирует продукты в JSON файл.
        TODO: Реализовать экспорт в JSON.
        """
        import json
        from datetime import datetime

        data = []
        for product in products:
            data.append({
                'id': product.id,
                'bank': product.bank,
                'product': product.product,
                'category': product.category.value,
                'rate_min': product.rate_min,
                'rate_max': product.rate_max,
                'amount_min': product.amount_min,
                'amount_max': product.amount_max,
                'term': product.term,
                'currency': product.currency.value,
                'confidence': product.confidence.value,
                'collected_at': product.collected_at.isoformat(),
                'grace_period': product.grace_period,
                'cashback': product.cashback,
                'commission': product.commission,
            })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
