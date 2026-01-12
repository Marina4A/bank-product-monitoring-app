import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QDate, QTimer, Qt
from PyQt6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QLabel

from core.config import config
from core.database import DatabaseManager
from core.models import BankProduct, Filters
from core.services.chat_service import ChatService
from core.services.currency_rates_service import CurrencyRatesService
from core.services.data_service import DataService
from core.services.database_service import DatabaseService
from core.services.export_service import ExportService
from core.services.logger_service import LoggerService
from core.services.parsing_service import ParsingService
from ui.ui_main_window import Ui_MainWindow
from ui.widgets.charts_widget import ChartsWidget
from ui.widgets.currency_tab_widget import CurrencyTabWidget
from ui.widgets.logs_widget import LogsWidget
from ui.widgets.moex_charts_widget import MoexChartsWidget
from ui.widgets.settings_widget import SettingsWidget
from ui.widgets.table_widget import TableWidget
from ui.widgets.banki_ratings_widget import BankiRatingsWidget


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        # Используем сгенерированный UI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Сервисы
        # Инициализируем LoggerService сначала
        self.logger_service = LoggerService()

        # Инициализируем DatabaseManager и DatabaseService
        try:
            db_manager = DatabaseManager(config.database.database_url)
            self.database_service = DatabaseService(db_manager)
            self.currency_rates_service = CurrencyRatesService(db_manager)
            self.logger_service.add_log(
                "INFO",
                f"Подключение к БД: {config.database.host}:{config.database.port}/{config.database.database}",
            )
        except Exception as e:
            self.logger_service.add_log(
                "ERROR", f"Ошибка подключения к БД: {e}. Работа без БД."
            )
            self.database_service = None
            self.currency_rates_service = None

        # Инициализируем ParsingService с callback для обновления UI
        self.parsing_service = ParsingService(
            timeout=config.parsing_timeout,
            retries=config.parsing_retries,
            headless=config.parsing_headless,
            on_product_parsed=self._on_products_parsed,
        )

        # Инициализируем DataService с database_service и parsing_service
        self.data_service = DataService(
            database_service=self.database_service,
            parsing_service=self.parsing_service,
        )

        self.export_service = ExportService()

        # AI Chat Service
        try:
            self.chat_service = ChatService()
        except Exception as e:
            self.logger_service.add_log(
                "WARNING", f"Не удалось инициализировать AI чат: {e}. Чат будет недоступен."
            )
            self.chat_service = None

        # Данные
        self._products: List[BankProduct] = []
        self._filters = Filters()
        self._is_dark_theme = False

        # Виджеты вкладок
        self.table_widget: Optional[TableWidget] = None
        self.charts_widget: Optional[ChartsWidget] = None
        self.settings_widget: Optional[SettingsWidget] = None
        self.logs_widget: Optional[LogsWidget] = None

        # Таймеры
        self._auto_refresh_timer: Optional[QTimer] = None
        self._parsing_timer: Optional[QTimer] = None

        self._setup_ui()
        self._connect_signals()
        self._load_initial_data()

    def _setup_ui(self):
        """Настройка UI."""
        # Устанавливаем заголовок
        self.setWindowTitle("BankMonitor - Мониторинг банковских продуктов")

        # Вкладка "Таблица" - заменяем только dataTableWidget на TableWidget
        # Остальные виджеты (фильтры, статистика, пагинация) остаются из UI
        self.table_widget = TableWidget()
        # Заменяем dataTableWidget на наш виджет
        # Находим позицию dataTableWidget в layout
        table_layout = self.ui.tableTabLayout
        data_table_index = -1
        for i in range(table_layout.count()):
            item = table_layout.itemAt(i)
            if item and item.widget() == self.ui.dataTableWidget:
                data_table_index = i
                break

        if data_table_index >= 0:
            # Удаляем старый виджет
            self.ui.dataTableWidget.setParent(None)
            # Вставляем наш виджет на его место
            table_layout.insertWidget(data_table_index, self.table_widget)
        else:
            # Если не нашли, добавляем в конец (перед пагинацией)
            # Находим paginationLayout
            pagination_index = -1
            for i in range(table_layout.count()):
                item = table_layout.itemAt(i)
                if item and item.layout() == self.ui.paginationLayout:
                    pagination_index = i
                    break
            if pagination_index >= 0:
                table_layout.insertWidget(pagination_index, self.table_widget)
            else:
                table_layout.addWidget(self.table_widget)

        # Вкладка "Графики" - заменяем на MoexChartsWidget для отображения данных MOEX
        # Используем существующую структуру из UI
        self.moex_charts_widget = MoexChartsWidget()
        # Заменяем chartsTabLayout содержимое
        charts_layout = self.ui.chartsTabLayout
        while charts_layout.count():
            child = charts_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())
        charts_layout.addWidget(self.moex_charts_widget)

        # Старый ChartsWidget больше не используется, но оставляем для совместимости
        self.charts_widget = None

        # Вкладка "Анализ" - добавляем виджет рейтингов Banki.ru
        self.banki_ratings_widget = BankiRatingsWidget()
        analysis_layout = self.ui.analysisTabLayout
        # Очищаем layout, если там что-то есть
        while analysis_layout.count():
            child = analysis_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())
        analysis_layout.addWidget(self.banki_ratings_widget)

        # Вкладка "Настройки" - заменяем содержимое на SettingsWidget
        # Используем существующую структуру из UI
        self.settings_widget = SettingsWidget()
        settings_layout = self.ui.settingsTabLayout
        while settings_layout.count():
            child = settings_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())
        settings_layout.addWidget(self.settings_widget)

        # Логи (внизу окна)
        # Полностью очищаем logWidget и пересоздаем layout
        # Это гарантирует, что все старые виджеты и layout'ы будут удалены

        # Сначала удаляем все виджеты напрямую, если они существуют
        # Не устанавливаем в None, чтобы retranslateUi не падал
        for widget_name in [
            "logsSearchLineEdit",
            "logsAllButton",
            "logsInfoButton",
            "logsWarningButton",
            "logsErrorButton",
            "logsListWidget",
        ]:
            if hasattr(self.ui, widget_name):
                widget = getattr(self.ui, widget_name)
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
                    # Удаляем атрибут вместо установки в None
                    delattr(self.ui, widget_name)

        # Удаляем logsFiltersLayout, если он существует
        if hasattr(self.ui, "logsFiltersLayout"):
            filters_layout = self.ui.logsFiltersLayout
            if filters_layout:
                # Удаляем все содержимое
                self._clear_layout(filters_layout)
                filters_layout.setParent(None)
                # Удаляем атрибут вместо установки в None
                delattr(self.ui, "logsFiltersLayout")

        # Полностью очищаем существующий layout из logWidget
        # Используем существующий layout вместо создания нового
        logs_layout = self.ui.logWidget.layout()
        if logs_layout:
            # Удаляем все элементы из существующего layout
            while logs_layout.count():
                child = logs_layout.takeAt(0)
                if child:
                    if child.widget():
                        widget = child.widget()
                        widget.setParent(None)
                        widget.deleteLater()
                    elif child.layout():
                        layout_to_remove = child.layout()
                        self._clear_layout(layout_to_remove)
                        layout_to_remove.setParent(None)
            # Очищаем spacing и margins
            logs_layout.setContentsMargins(0, 0, 0, 0)
            logs_layout.setSpacing(0)
        else:
            # Если layout не существует, создаем новый
            from PyQt6.QtWidgets import QVBoxLayout

            logs_layout = QVBoxLayout(self.ui.logWidget)
            logs_layout.setContentsMargins(0, 0, 0, 0)
            logs_layout.setSpacing(0)

        # Обновляем ссылку на layout в UI, чтобы использовать новый
        self.ui.logsContentLayout = logs_layout

        # Создаем наш виджет логов
        self.logs_widget = LogsWidget()
        # Удаляем кнопку переключения из LogsWidget, так как используем UI кнопку
        if hasattr(self.logs_widget, "toggle_button") and self.logs_widget.toggle_button:
            self.logs_widget.toggle_button.setParent(None)
            self.logs_widget.toggle_button.deleteLater()
            # Устанавливаем в None, чтобы избежать ошибок
            self.logs_widget.toggle_button = None

        # Дополнительно: удаляем все дочерние виджеты из logWidget напрямую
        # Это гарантирует, что не останется лишних виджетов (например, старых QWidget без objectName)
        from PyQt6.QtWidgets import QWidget as QW

        for child in self.ui.logWidget.findChildren(QW):
            # Пропускаем content_widget из LogsWidget (он будет добавлен позже)
            # Удаляем все остальные виджеты
            if child != self.logs_widget.content_widget:
                child.setParent(None)
                child.deleteLater()

        # Обновляем ссылку на layout в UI, чтобы использовать новый
        self.ui.logsContentLayout = logs_layout

        # Добавляем только content_widget в layout (без кнопки переключения)
        # content_widget должен быть виден, когда logWidget виден
        logs_layout.addWidget(self.logs_widget.content_widget)

        # Скрываем logWidget по умолчанию
        self.ui.logWidget.setVisible(False)
        # content_widget должен быть виден внутри logWidget
        self.logs_widget.content_widget.setVisible(True)

        # Обновляем текст кнопки при изменении количества логов
        def update_logs_button_text():
            count = len(self.logs_widget._logs) if self.logs_widget else 0
            is_visible = self.ui.logWidget.isVisible()
            self.ui.logsToggleButton.setText(
                f"{'▲' if is_visible else '▼'} Логи системы ({count})"
            )

        # Сохраняем функцию для обновления текста кнопки
        self._update_logs_button_text = update_logs_button_text

        # Подключаем кнопку переключения из UI к показу/скрытию logWidget
        def on_logs_toggle(checked):
            self.ui.logWidget.setVisible(checked)
            update_logs_button_text()

        self.ui.logsToggleButton.clicked.connect(on_logs_toggle)

        # Добавляем вкладку с валютами после "Таблица"
        currency_tab = CurrencyTabWidget(currency_rates_service=self.currency_rates_service)
        # Находим индекс вкладки "Таблица" и добавляем после неё
        table_tab_index = self.ui.mainTabWidget.indexOf(self.ui.tableTab)
        self.ui.mainTabWidget.insertTab(table_tab_index + 1, currency_tab, "Валюты")

        # Настраиваем фильтры (они находятся в tableTab, а не в header)
        self._setup_filters()

        # Настраиваем AI Chat DockWidget
        self._setup_chat_dock()

        # Устанавливаем начальные значения
        self._update_ui_texts()

    def _setup_filters(self):
        """Настройка фильтров."""
        # Фильтры находятся в tableTab, а не в header
        # Заполняем комбобоксы в tableTab
        self.ui.bankComboBox.clear()
        self.ui.bankComboBox.addItems(
            ["Все банки", "Sberbank", "TBank", "VTB", "Alfa-Bank", "Gazprombank"]
        )

        self.ui.categoryComboBox.clear()
        self.ui.categoryComboBox.addItems(
            ["Все", "Вклады", "Кредиты", "Дебетовые карты", "Кредитные карты"]
        )

        # В UI файле нет currencyComboBox в tableTab, только bankComboBox и categoryComboBox
        # Если нужен currencyComboBox, его нужно добавить в UI файл или использовать другой способ

        # Устанавливаем даты по умолчанию (если есть dateFromEdit и dateToEdit в UI)
        # Проверяем наличие этих виджетов
        if hasattr(self.ui, "dateFromEdit") and hasattr(self.ui, "dateToEdit"):
            date_from = datetime.now() - timedelta(days=30)
            self.ui.dateFromEdit.setDate(
                QDate.fromString(date_from.strftime("%Y-%m-%d"), "yyyy-MM-dd")
            )
            self.ui.dateToEdit.setDate(QDate.currentDate())

    def _setup_chat_dock(self):
        """Настройка AI Chat DockWidget."""
        if not self.chat_service:
            # Если чат недоступен, отключаем виджеты
            self.ui.chatInputLineEdit.setEnabled(False)
            self.ui.chatSendButton.setEnabled(False)
            self.ui.chatInputLineEdit.setPlaceholderText("AI чат недоступен (нет GIGACHAT_AUTH_KEY)")
            return

        # Очищаем приветственный label и добавляем приветственное сообщение от AI
        if hasattr(self.ui, "chatWelcomeLabel"):
            welcome_msg = self.chat_service.get_welcome_message()
            self.ui.chatWelcomeLabel.setText(welcome_msg)
            self.ui.chatWelcomeLabel.setWordWrap(True)
            self.ui.chatWelcomeLabel.setStyleSheet(
                "padding: 10px; background-color: #e3f2fd; border-radius: 5px; margin: 5px;"
            )

        # Подключаем сигналы
        self.ui.chatSendButton.clicked.connect(self._on_chat_send)
        self.ui.chatInputLineEdit.returnPressed.connect(self._on_chat_send)

        # Устанавливаем placeholder
        self.ui.chatInputLineEdit.setPlaceholderText("Введите вопрос...")

        # Настраиваем layout для сообщений
        # chatMessagesLayout уже есть в UI, мы будем добавлять в него QLabels через QHBoxLayout

    def _connect_signals(self):
        """Подключение сигналов."""
        # Кнопки в header (из UI)
        self.ui.refreshButton.clicked.connect(self._on_refresh)
        self.ui.exportButton.clicked.connect(self._on_export)
        if hasattr(self.ui, "themeToggleButton"):
            self.ui.themeToggleButton.clicked.connect(self._on_toggle_theme)

        # Фильтры (находятся в tableTab)
        self.ui.bankComboBox.currentTextChanged.connect(self._on_filter_changed)
        self.ui.categoryComboBox.currentTextChanged.connect(self._on_filter_changed)
        # currencyComboBox нет в UI, пропускаем
        # if hasattr(self.ui, "currencyComboBox"):
        #     self.ui.currencyComboBox.currentTextChanged.connect(self._on_filter_changed)

        # Даты (если есть в UI)
        if hasattr(self.ui, "dateFromEdit"):
            self.ui.dateFromEdit.dateChanged.connect(self._on_filter_changed)
        if hasattr(self.ui, "dateToEdit"):
            self.ui.dateToEdit.dateChanged.connect(self._on_filter_changed)

        # Поиск (если есть в UI)
        if hasattr(self.ui, "searchLineEdit"):
            self.ui.searchLineEdit.textChanged.connect(self._on_search_changed)

        # Виджеты
        if self.table_widget:
            self.table_widget.refresh_requested.connect(self._on_refresh)
            self.table_widget.export_requested.connect(self._on_export)

        if self.settings_widget:
            self.settings_widget.settings_saved.connect(self._on_settings_saved)
            self.settings_widget.settings_reset.connect(self._on_settings_reset)

    def _load_initial_data(self):
        """Загружает начальные данные из БД при старте приложения."""
        self.logger_service.add_log("INFO", "Приложение запущено")
        self.logger_service.add_log("INFO", "Загрузка данных из БД...")
        self._update_logs()

        # Загружаем данные из БД (не запускаем парсинг автоматически)
        asyncio.create_task(self._load_data_from_db())

        # НЕ настраиваем таймер для автоматического парсинга
        # Парсинг будет запускаться только по кнопке refreshButton

    async def _load_data_from_db(self):
        """Загружает данные из БД при старте приложения."""
        try:
            self.logger_service.add_log("INFO", "Загрузка данных из БД...")
            self._update_logs()

            # Загружаем продукты из БД через data_service
            products = await self.data_service.load_products()
            self._products = products

            # Обновляем UI
            self._update_all_widgets()

            self.logger_service.add_log(
                "INFO", f"Загружено {len(products)} продуктов из БД"
            )
            self._update_logs()
        except Exception as e:
            self.logger_service.add_log(
                "ERROR", f"Ошибка загрузки данных из БД: {str(e)}"
            )
            self._update_logs()

    async def _on_products_parsed(self, products: List[BankProduct]) -> None:
        """
        Callback вызываемый после парсинга каждого банка.
        Только логирует прогресс парсинга, не обновляет UI.

        Args:
            products: Список новых продуктов
        """
        if not products:
            return

        self.logger_service.add_log("INFO", f"Спарсено {len(products)} продуктов")
        self._update_logs()

    async def _refresh_data(self):
        """
        Обновляет данные через парсинг и сохраняет в БД.
        Вызывается только при нажатии на кнопку refreshButton.
        """
        try:
            self.logger_service.add_log("INFO", "Начало парсинга данных...")
            self.logger_service.add_log("INFO", "Это может занять некоторое время...")
            self._update_logs()

            # Обновляем данные через парсинг (парсинг + сохранение в БД + обновление статусов)
            products = await self.data_service.refresh_products()
            self._products = products

            # Обновляем UI с актуальными данными из БД
            self._update_all_widgets()

            self.logger_service.add_log(
                "INFO", f"Парсинг завершен. Всего продуктов в БД: {len(products)}"
            )

            # Удаляем старые неактуальные записи (старше 7 дней)
            if self.database_service:
                deleted = await self.database_service.delete_inactive_products(
                    older_than_days=7
                )
                if deleted > 0:
                    self.logger_service.add_log(
                        "INFO", f"Удалено {deleted} неактуальных записей (старше 7 дней)"
                    )
                    # Перезагружаем данные из БД после удаления
                    products = await self.data_service.load_products()
                    self._products = products
                    self._update_all_widgets()

            self._update_logs()
        except Exception as e:
            self.logger_service.add_log("ERROR", f"Ошибка парсинга данных: {str(e)}")
            self._update_logs()

            # В случае ошибки, пытаемся загрузить данные из БД
            try:
                if self.database_service:
                    products = await self.data_service.load_products()
                    self._products = products
                    self._update_all_widgets()
            except Exception as db_error:
                self.logger_service.add_log(
                    "ERROR", f"Ошибка загрузки из БД: {str(db_error)}"
                )

    def _update_all_widgets(self):
        """Обновляет все виджеты с текущими данными."""
        # Применяем фильтры
        filtered = self.data_service.filter_products(self._products, self._filters)

        # Обновляем статистику в UI (только оставшиеся виджеты statCard1 и statCard3, если они есть)
        if filtered:
            total = len(filtered)

            # Обновляем stat1ValueLabel (statCard1) - он точно есть
            if hasattr(self.ui, "stat1ValueLabel"):
                self.ui.stat1ValueLabel.setText(str(total))

            # Проверяем наличие stat3ValueLabel (statCard3) перед обновлением
            # (если пользователь удалил statCard3 и statCard4, этот виджет может отсутствовать)
            if hasattr(self.ui, "stat3ValueLabel"):
                banks = len(set(p.bank for p in filtered))
                self.ui.stat3ValueLabel.setText(str(banks))
        else:
            # Обновляем stat1ValueLabel (statCard1) - он точно есть
            if hasattr(self.ui, "stat1ValueLabel"):
                self.ui.stat1ValueLabel.setText("0")

            # Проверяем наличие stat3ValueLabel перед обновлением
            if hasattr(self.ui, "stat3ValueLabel"):
                self.ui.stat3ValueLabel.setText("0")

        # Обновляем количество записей
        self.ui.recordsCountLabel.setText(f"{len(filtered)} записей найдено")

        if self.table_widget:
            self.table_widget.set_products(filtered)

        # MoexChartsWidget не использует метод set_products, работает независимо
        # Графики MOEX управляются через вкладку "Графики"

        # Вкладка "Анализ" остается пустой, не обновляем её

    def _update_logs(self):
        """Обновляет виджет логов."""
        if self.logs_widget:
            logs = self.logger_service.get_logs(limit=100)
            self.logs_widget.set_logs(logs)
            # Обновляем текст кнопки
            if hasattr(self, "_update_logs_button_text"):
                self._update_logs_button_text()

    def _on_refresh(self):
        """Обработчик кнопки обновления."""
        asyncio.create_task(self._refresh_data())

    def _on_export(self, format: str = "csv"):
        """Обработчик экспорта."""
        # Определяем формат из расширения файла, если format не указан явно
        if format == "csv":
            file_filter = "CSV Files (*.csv);;All Files (*.*)"
        elif format == "json":
            file_filter = "JSON Files (*.json);;All Files (*.*)"
        elif format == "excel" or format == "xlsx":
            file_filter = "Excel Files (*.xlsx);;All Files (*.*)"
        else:
            file_filter = "CSV Files (*.csv);;JSON Files (*.json);;Excel Files (*.xlsx);;All Files (*.*)"

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Сохранить данные...",
            f"bank_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            file_filter,
        )

        if file_path:
            # Определяем формат из расширения файла или выбранного фильтра
            if file_path.endswith('.xlsx'):
                export_format = "excel"
            elif file_path.endswith('.json'):
                export_format = "json"
            elif file_path.endswith('.csv'):
                export_format = "csv"
            elif selected_filter:
                # Определяем по выбранному фильтру, если расширение не указано
                if "xlsx" in selected_filter.lower() or "excel" in selected_filter.lower():
                    export_format = "excel"
                    if not file_path.endswith('.xlsx'):
                        file_path += '.xlsx'
                elif "json" in selected_filter.lower():
                    export_format = "json"
                    if not file_path.endswith('.json'):
                        file_path += '.json'
                else:
                    # По умолчанию CSV
                    export_format = "csv"
                    if not file_path.endswith('.csv'):
                        file_path += '.csv'
            else:
                # По умолчанию CSV
                export_format = "csv"
                if not file_path.endswith('.csv'):
                    file_path += '.csv'

            asyncio.create_task(self._do_export(export_format, Path(file_path)))

    async def _do_export(self, format: str, file_path: Path):
        """Выполняет экспорт."""
        try:
            # Получаем отфильтрованные продукты для экспорта
            filtered = self.data_service.filter_products(self._products, self._filters)

            if not filtered:
                QMessageBox.information(
                    self, "Информация", "Нет данных для экспорта. Примените другие фильтры."
                )
                return

            if format == "csv":
                await self.export_service.export_to_csv(filtered, file_path)
            elif format == "json":
                await self.export_service.export_to_json(filtered, file_path)
            elif format == "excel" or format == "xlsx":
                await self.export_service.export_to_excel(filtered, file_path)
            else:
                raise ValueError(f"Неподдерживаемый формат экспорта: {format}")

            self.logger_service.add_log("INFO", f"Данные экспортированы в {file_path}")
            self._update_logs()
            QMessageBox.information(
                self, "Успех", f"Данные успешно экспортированы в {file_path}"
            )
        except Exception as e:
            self.logger_service.add_log("ERROR", f"Ошибка экспорта: {str(e)}")
            self._update_logs()
            QMessageBox.critical(
                self, "Ошибка", f"Не удалось экспортировать данные: {str(e)}"
            )

    def _on_toggle_theme(self):
        """Переключение темы."""
        self._is_dark_theme = not self._is_dark_theme
        # TODO: Реализовать переключение темы
        self.logger_service.add_log(
            "INFO", f"Тема изменена на {'темную' if self._is_dark_theme else 'светлую'}"
        )
        self._update_logs()

    def _on_filter_changed(self):
        """Обработчик изменения фильтров."""
        # Обновляем фильтры
        bank_text = self.ui.bankComboBox.currentText()
        self._filters.bank = "all" if bank_text == "Все банки" else bank_text

        category_text = self.ui.categoryComboBox.currentText()
        category_map = {
            "Все": "all",
            "Вклады": "deposit",
            "Кредиты": "credit",
            "Дебетовые карты": "debitcard",
            "Кредитные карты": "creditcard",
        }
        self._filters.category = category_map.get(category_text, "all")

        # Валюта - если есть в UI
        if hasattr(self.ui, "currencyComboBox"):
            currency_text = self.ui.currencyComboBox.currentText()
            self._filters.currency = (
                "all" if currency_text == "Все валюты" else currency_text
            )

        # Даты - если есть в UI
        if hasattr(self.ui, "dateFromEdit") and hasattr(self.ui, "dateToEdit"):
            self._filters.date_from = datetime.combine(
                self.ui.dateFromEdit.date().toPyDate(), datetime.min.time()
            )
            self._filters.date_to = datetime.combine(
                self.ui.dateToEdit.date().toPyDate(), datetime.min.time()
            )

        # Обновляем виджеты
        self._update_all_widgets()

    def _on_search_changed(self, text: str):
        """Обработчик изменения поискового запроса."""
        self._filters.search_query = text
        self._update_all_widgets()

    def _on_settings_saved(self, settings: dict):
        """Обработчик сохранения настроек."""
        # TODO: Сохранить настройки в файл/БД
        self.logger_service.add_log("INFO", "Настройки сохранены")
        self._update_logs()

        # Обновляем настройки парсинга
        timeout = settings.get("timeout", 30)
        retries = settings.get("retries", 3)
        self.parsing_service.timeout = timeout
        self.parsing_service.retries = retries

        # Парсинг запускается только по кнопке refreshButton
        # Таймер парсинга не запускается автоматически
        # Если в будущем понадобится автоматический парсинг, можно включить здесь:
        # update_interval = settings.get("update_interval", 360)
        # if settings.get("auto_parsing", False):  # Опция для включения автопарсинга
        #     self._setup_parsing_timer(update_interval_minutes=update_interval)

        # Обновляем автообновление UI
        if settings.get("auto_refresh"):
            interval = (
                settings.get("auto_refresh_interval", 300) * 1000
            )  # в миллисекундах
            if self._auto_refresh_timer:
                self._auto_refresh_timer.stop()
            self._auto_refresh_timer = QTimer(self)
            self._auto_refresh_timer.timeout.connect(self._on_refresh_ui_only)
            self._auto_refresh_timer.start(interval)
        else:
            if self._auto_refresh_timer:
                self._auto_refresh_timer.stop()

    def _setup_parsing_timer(self, update_interval_minutes: int = 360):
        """
        Настраивает таймер для периодического парсинга.
        По умолчанию НЕ запускается - парсинг только по кнопке refreshButton.

        Args:
            update_interval_minutes: Интервал парсинга в минутах (по умолчанию 6 часов)
        """
        if self._parsing_timer:
            self._parsing_timer.stop()

        # Конвертируем минуты в миллисекунды
        interval_ms = update_interval_minutes * 60 * 1000
        self._parsing_timer = QTimer(self)
        self._parsing_timer.timeout.connect(
            lambda: asyncio.create_task(self._refresh_data())
        )
        self._parsing_timer.start(interval_ms)

        self.logger_service.add_log(
            "INFO",
            f"Таймер парсинга настроен на интервал {update_interval_minutes} минут",
        )
        self._update_logs()

    def _on_refresh_ui_only(self):
        """Обновляет только UI без парсинга (для автообновления)."""
        self._update_all_widgets()

    def _on_settings_reset(self):
        """Обработчик сброса настроек."""
        self.logger_service.add_log("INFO", "Настройки сброшены")
        self._update_logs()

    def _on_chat_send(self):
        """Обработчик отправки сообщения в AI чат."""
        if not self.chat_service:
            QMessageBox.warning(
                self, "Ошибка", "AI чат недоступен. Проверьте настройки GIGACHAT_AUTH_KEY."
            )
            return

        user_message = self.ui.chatInputLineEdit.text().strip()
        if not user_message:
            return

        # Добавляем сообщение пользователя в чат
        self._add_chat_message("user", user_message)

        # Очищаем поле ввода
        self.ui.chatInputLineEdit.clear()

        # Отключаем кнопку отправки во время обработки
        self.ui.chatSendButton.setEnabled(False)
        self.ui.chatInputLineEdit.setEnabled(False)

        # Отправляем сообщение асинхронно
        asyncio.create_task(self._send_chat_message_async(user_message))

    async def _send_chat_message_async(self, user_message: str):
        """Асинхронная отправка сообщения в AI чат."""
        try:
            # Получаем отфильтрованные продукты для контекста
            filtered_products = self.data_service.filter_products(
                self._products, self._filters
            )

            # Отправляем сообщение в AI с контекстом продуктов
            response = await self.chat_service.send_message(
                user_message, products_context=filtered_products if filtered_products else None
            )

            # Добавляем ответ AI в чат
            self._add_chat_message("assistant", response)

        except Exception as e:
            error_msg = f"Ошибка при общении с AI: {str(e)}"
            self._add_chat_message("assistant", error_msg)
            self.logger_service.add_log("ERROR", error_msg)
            self._update_logs()
        finally:
            # Включаем кнопку отправки обратно
            self.ui.chatSendButton.setEnabled(True)
            self.ui.chatInputLineEdit.setEnabled(True)
            self.ui.chatInputLineEdit.setFocus()

    def _add_chat_message(self, role: str, message: str):
        """
        Добавляет сообщение в чат в виде QLabel.

        Args:
            role: Роль отправителя ("user" или "assistant")
            message: Текст сообщения
        """

        # Скрываем приветственный label, если он есть и еще виден
        if hasattr(self.ui, "chatWelcomeLabel") and self.ui.chatWelcomeLabel.isVisible():
            self.ui.chatWelcomeLabel.setVisible(False)

        # Создаем QLabel для сообщения
        message_label = QLabel(self.ui.chatMessagesWidget)
        message_label.setText(message)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Получаем ширину виджета для установки максимальной ширины сообщений
        widget_width = self.ui.chatMessagesWidget.width()
        if widget_width <= 0:
            # Если виджет еще не отрисован, используем ширину scroll area
            widget_width = self.ui.chatMessagesScrollArea.width() - 20  # Минус отступы
        if widget_width <= 0:
            widget_width = 300  # Значение по умолчанию

        max_message_width = max(150, int(widget_width * 0.75))
        message_label.setMaximumWidth(max_message_width)

        # Стилизуем в зависимости от роли
        if role == "user":
            # Сообщение пользователя - справа, синий цвет
            message_label.setStyleSheet(
                """
                QLabel {
                    background-color: #2196F3;
                    color: white;
                    padding: 8px 12px;
                    border-radius: 12px;
                    margin: 5px;
                }
            """
            )
            # Текст внутри QLabel выровнен по правому краю
            message_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        else:
            # Сообщение AI - слева, серый цвет
            message_label.setStyleSheet(
                """
                QLabel {
                    background-color: #f5f5f5;
                    color: black;
                    padding: 8px 12px;
                    border-radius: 12px;
                    margin: 5px;
                }
            """
            )
            # Текст внутри QLabel выровнен по левому краю
            message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Добавляем в layout (перед спейсером, если он есть)
        layout = self.ui.chatMessagesLayout

        # Для выравнивания сообщений используем горизонтальный layout для каждого сообщения
        from PyQt6.QtWidgets import QHBoxLayout, QWidget

        # Создаем горизонтальный layout для выравнивания сообщения
        message_row = QHBoxLayout()
        message_row.setContentsMargins(5, 2, 5, 2)
        message_row.setSpacing(0)

        if role == "user":
            # Сообщение пользователя - прижимаем к правому краю
            message_row.addStretch()  # Растягиваем слева, чтобы сдвинуть сообщение вправо
            message_row.addWidget(message_label)
            # Виджет уже прижат к правому краю благодаря addStretch() перед ним
        else:
            # Сообщение AI - прижимаем к левому краю
            message_row.addWidget(message_label)
            # Виджет уже прижат к левому краю, так как он первый элемент
            message_row.addStretch()  # Растягиваем справа, чтобы оставить сообщение слева

        # Создаем обертку-виджет для горизонтального layout
        message_widget = QWidget(self.ui.chatMessagesWidget)
        message_widget.setLayout(message_row)

        # Находим спейсер (последний элемент обычно спейсер)
        spacer_index = -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.spacerItem():
                spacer_index = i
                break

        if spacer_index >= 0:
            # Вставляем перед спейсером
            layout.insertWidget(spacer_index, message_widget)
        else:
            # Добавляем в конец
            layout.addWidget(message_widget)

        # Обновляем виджет, чтобы сообщение появилось
        message_widget.show()

        # Прокручиваем вниз, чтобы показать новое сообщение
        scroll_area = self.ui.chatMessagesScrollArea
        scroll_bar = scroll_area.verticalScrollBar()
        # Используем QTimer для прокрутки после обновления layout
        QTimer.singleShot(100, lambda: scroll_bar.setValue(scroll_bar.maximum()))

    def _clear_layout(self, layout):
        """Рекурсивно очищает layout."""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def _update_ui_texts(self):
        """Обновляет тексты UI элементов."""
        # Устанавливаем тексты из UI файла
        # Обрабатываем ошибки, если некоторые виджеты были удалены
        try:
            self.ui.retranslateUi(self)
        except AttributeError:
            # Игнорируем ошибки для удаленных виджетов (например, logsSearchLineEdit)
            # Это нормально, так как мы удалили некоторые виджеты из UI
            pass

    def closeEvent(self, event):
        """Обработчик закрытия окна."""
        # Останавливаем таймеры
        if self._auto_refresh_timer:
            self._auto_refresh_timer.stop()
        if self._parsing_timer:
            self._parsing_timer.stop()

        # Закрываем виджеты валют
        if hasattr(self, "currency_tab"):
            # Закрываем клиенты HTTP
            pass

        event.accept()
