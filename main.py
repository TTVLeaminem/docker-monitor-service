#!/usr/bin/env python3
"""
Shop-BI Docker Container Monitor
Мониторинг состояния Docker контейнеров с уведомлениями в Telegram
Поддержка кнопок управления и мгновенного отслеживания через Docker Events
"""

import os
import json
import logging
import threading
import queue
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import docker
from docker.errors import DockerException, APIError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ContainerState:
    """Состояние контейнера"""
    name: str
    status: str  # 'running', 'stopped', 'restarting', 'paused', 'exited'
    health: Optional[str]  # 'healthy', 'unhealthy', 'starting', None
    last_check: str
    downtime_start: Optional[str] = None
    last_status: Optional[str] = None


@dataclass
class MonitorState:
    """Общее состояние мониторинга"""
    containers: Dict[str, ContainerState]
    last_update: str


class TelegramNotifier:
    """Класс для отправки уведомлений в Telegram"""
    
    def __init__(self, application: Application, chat_id: str):
        self.application = application
        self.chat_id = chat_id
    
    async def send_message(self, message: str, parse_mode: str = "HTML", reply_markup: Optional[InlineKeyboardMarkup] = None) -> bool:
        """Отправка сообщения в Telegram"""
        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")
            return False
    
    def format_duration(self, seconds: int) -> str:
        """Форматирование длительности"""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}д")
        if hours > 0:
            parts.append(f"{hours}ч")
        if minutes > 0:
            parts.append(f"{minutes}м")
        if secs > 0 or not parts:
            parts.append(f"{secs}с")
        
        return " ".join(parts)
    
    async def notify_container_down(self, container_name: str, status: str, downtime_start: datetime):
        """Уведомление о падении контейнера"""
        downtime_str = downtime_start.strftime("%Y-%m-%d %H:%M:%S UTC")
        message = (
            f"🔴 <b>Контейнер недоступен!</b>\n\n"
            f"📦 Контейнер: <code>{container_name}</code>\n"
            f"❌ Статус: {status}\n"
            f"🕐 Время падения: {downtime_str}\n"
            f"⚠️ Начинаю отслеживание простоя..."
        )
        await self.send_message(message)
    
    async def notify_container_up(self, container_name: str, downtime_duration: int, recovery_time: datetime):
        """Уведомление о восстановлении контейнера"""
        downtime_formatted = self.format_duration(downtime_duration)
        recovery_str = recovery_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        message = (
            f"🟢 <b>Контейнер восстановлен!</b>\n\n"
            f"📦 Контейнер: <code>{container_name}</code>\n"
            f"✅ Статус: Работает\n"
            f"⏱️ Время простоя: {downtime_formatted}\n"
            f"🕐 Время восстановления: {recovery_str}"
        )
        await self.send_message(message)
    
    async def notify_container_status_change(self, container_name: str, old_status: str, new_status: str, health: Optional[str] = None):
        """Уведомление об изменении статуса контейнера"""
        health_info = f"\n🏥 Health: {health}" if health else ""
        message = (
            f"🟡 <b>Изменение статуса контейнера</b>\n\n"
            f"📦 Контейнер: <code>{container_name}</code>\n"
            f"📊 Статус: {old_status} → {new_status}{health_info}\n"
            f"🕐 Время: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        await self.send_message(message)
    
    async def notify_startup(self, monitored_containers: List[str]):
        """Уведомление о запуске мониторинга"""
        containers_list = "\n".join([f"  • <code>{name}</code>" for name in monitored_containers])
        keyboard = self.get_main_keyboard()
        message = (
            f"🔵 <b>Мониторинг запущен</b>\n\n"
            f"📊 Отслеживаемые контейнеры:\n{containers_list}\n\n"
            f"🕐 Время запуска: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"Используйте кнопки ниже для управления:"
        )
        await self.send_message(message, reply_markup=keyboard)
    
    @staticmethod
    def get_main_keyboard() -> InlineKeyboardMarkup:
        """Создание клавиатуры с кнопками управления"""
        keyboard = [
            [
                InlineKeyboardButton("📋 Список контейнеров", callback_data="list_containers"),
                InlineKeyboardButton("📊 Статусы контейнеров", callback_data="status_containers")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)


class DockerMonitor:
    """Класс для мониторинга Docker контейнеров"""
    
    def __init__(
        self,
        telegram_notifier: TelegramNotifier,
        state_file: str = "/tmp/docker-monitor-state.json",
        check_interval: int = 60,
        monitored_containers: Optional[List[str]] = None
    ):
        self.telegram_notifier = telegram_notifier
        self.state_file = Path(state_file)
        self.check_interval = check_interval
        self.monitored_containers = monitored_containers or []
        self._stop_events = False
        self._event_queue = queue.Queue()
        
        try:
            # Проверяем, нужно ли подключаться к удаленному Docker
            remote_docker_host = os.getenv('REMOTE_DOCKER_HOST')
            if remote_docker_host:
                remote_user = os.getenv('REMOTE_DOCKER_USER', 'root')
                # Формируем DOCKER_HOST для SSH подключения
                # Формат: ssh://user@host
                docker_host = f"ssh://{remote_user}@{remote_docker_host}"
                logger.info(f"Подключение к удаленному Docker: {docker_host}")
                self.docker_client = docker.DockerClient(base_url=docker_host)
            else:
                self.docker_client = docker.from_env()
                logger.info("Подключение к локальному Docker API установлено")
        except DockerException as e:
            logger.error(f"Ошибка подключения к Docker: {e}")
            raise
        
        self.state = self.load_state()
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    def load_state(self) -> MonitorState:
        """Загрузка состояния из файла"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    containers = {
                        name: ContainerState(**container_data)
                        for name, container_data in data.get('containers', {}).items()
                    }
                    return MonitorState(
                        containers=containers,
                        last_update=data.get('last_update', datetime.now(timezone.utc).isoformat())
                    )
            except Exception as e:
                logger.warning(f"Ошибка загрузки состояния: {e}")
        
        return MonitorState(containers={}, last_update=datetime.now(timezone.utc).isoformat())
    
    def save_state(self):
        """Сохранение состояния в файл"""
        try:
            state_dict = {
                'containers': {
                    name: asdict(container_state)
                    for name, container_state in self.state.containers.items()
                },
                'last_update': self.state.last_update
            }
            with open(self.state_file, 'w') as f:
                json.dump(state_dict, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния: {e}")
    
    def get_container_status(self, container_name: str) -> Optional[Dict]:
        """Получение статуса контейнера"""
        try:
            container = self.docker_client.containers.get(container_name)
            attrs = container.attrs
            
            status = attrs.get('State', {}).get('Status', 'unknown')
            health = None
            
            # Получаем health status если доступен
            health_state = attrs.get('State', {}).get('Health', {})
            if health_state:
                health = health_state.get('Status')
            
            return {
                'status': status,
                'health': health,
                'exists': True
            }
        except docker.errors.NotFound:
            return {'status': 'not_found', 'health': None, 'exists': False}
        except Exception as e:
            logger.error(f"Ошибка получения статуса контейнера {container_name}: {e}")
            return None
    
    def is_container_healthy(self, status_info: Dict) -> bool:
        """Проверка, что контейнер работает нормально"""
        if not status_info or not status_info.get('exists'):
            return False
        
        status = status_info.get('status', '')
        health = status_info.get('health')
        
        # Контейнер считается здоровым если:
        # - статус 'running'
        # - health либо None (нет healthcheck), либо 'healthy'
        if status == 'running':
            if health is None or health == 'healthy':
                return True
        
        return False
    
    def discover_containers(self) -> List[str]:
        """Автоматическое обнаружение контейнеров для мониторинга"""
        if self.monitored_containers:
            return self.monitored_containers
        
        try:
            # Получаем все контейнеры с префиксом shop_bi
            all_containers = self.docker_client.containers.list(all=True)
            shop_bi_containers = [
                c.name for c in all_containers
                if c.name.startswith('shop_bi_')
            ]
            return shop_bi_containers
        except Exception as e:
            logger.error(f"Ошибка обнаружения контейнеров: {e}")
            return []
    
    def get_all_containers_status(self) -> Dict[str, Dict]:
        """Получение статусов всех отслеживаемых контейнеров"""
        containers_to_monitor = self.discover_containers()
        statuses = {}
        
        for container_name in containers_to_monitor:
            status_info = self.get_container_status(container_name)
            if status_info:
                statuses[container_name] = status_info
        
        return statuses
    
    def format_containers_list(self) -> str:
        """Форматирование списка контейнеров"""
        containers = self.discover_containers()
        if not containers:
            return "❌ Контейнеры не найдены"
        
        containers_list = "\n".join([f"  • <code>{name}</code>" for name in sorted(containers)])
        return f"📋 <b>Отслеживаемые контейнеры ({len(containers)}):</b>\n\n{containers_list}"
    
    def format_containers_status(self) -> str:
        """Форматирование статусов контейнеров"""
        statuses = self.get_all_containers_status()
        if not statuses:
            return "❌ Не удалось получить статусы контейнеров"
        
        lines = ["📊 <b>Статусы контейнеров:</b>\n"]
        
        for container_name in sorted(statuses.keys()):
            status_info = statuses[container_name]
            status = status_info.get('status', 'unknown')
            health = status_info.get('health')
            
            # Эмодзи для статуса
            status_emoji = {
                'running': '🟢',
                'exited': '🔴',
                'stopped': '🔴',
                'restarting': '🟡',
                'paused': '⏸️',
                'not_found': '❌'
            }.get(status, '⚪')
            
            # Эмодзи для health
            health_emoji = {
                'healthy': '✅',
                'unhealthy': '⚠️',
                'starting': '🔄'
            }.get(health, '')
            
            health_text = f" {health_emoji} {health}" if health else ""
            lines.append(f"{status_emoji} <code>{container_name}</code>: {status}{health_text}")
        
        return "\n".join(lines)
    
    async def process_container_event(self, event: Dict):
        """Обработка события Docker"""
        try:
            event_type = event.get('Type')
            action = event.get('Action')
            actor = event.get('Actor', {})
            attributes = actor.get('Attributes', {})
            container_name = attributes.get('name')
            
            # Проверяем, отслеживаем ли мы этот контейнер
            containers_to_monitor = self.discover_containers()
            if not container_name or container_name not in containers_to_monitor:
                return
            
            # Обрабатываем только события контейнеров
            if event_type != 'container':
                return
            
            current_time = datetime.now(timezone.utc)
            
            # Получаем текущий статус
            status_info = self.get_container_status(container_name)
            if status_info is None:
                return
            
            current_status = status_info.get('status', 'unknown')
            current_health = status_info.get('health')
            is_healthy = self.is_container_healthy(status_info)
            
            # Получаем предыдущее состояние
            prev_state = self.state.containers.get(container_name)
            
            if prev_state is None:
                # Первая проверка контейнера
                self.state.containers[container_name] = ContainerState(
                    name=container_name,
                    status=current_status,
                    health=current_health,
                    last_check=current_time.isoformat(),
                    last_status=current_status
                )
                if not is_healthy:
                    self.state.containers[container_name].downtime_start = current_time.isoformat()
                    await self.telegram_notifier.notify_container_down(
                        container_name, current_status, current_time
                    )
                self.save_state()
                return
            
            # Проверяем изменения статуса
            prev_status = prev_state.status
            prev_healthy = self.is_container_healthy({
                'status': prev_status,
                'health': prev_state.health,
                'exists': True
            })
            
            # Обновляем состояние
            prev_state.status = current_status
            prev_state.health = current_health
            prev_state.last_check = current_time.isoformat()
            
            # Обработка изменений
            if not is_healthy and prev_healthy:
                # Контейнер упал
                prev_state.downtime_start = current_time.isoformat()
                await self.telegram_notifier.notify_container_down(
                    container_name, current_status, current_time
                )
                logger.warning(f"Контейнер {container_name} упал: {current_status}")
            
            elif is_healthy and not prev_healthy:
                # Контейнер восстановился
                downtime_duration = 0
                if prev_state.downtime_start:
                    downtime_start = datetime.fromisoformat(prev_state.downtime_start.replace('Z', '+00:00'))
                    downtime_duration = int((current_time - downtime_start).total_seconds())
                
                await self.telegram_notifier.notify_container_up(
                    container_name, downtime_duration, current_time
                )
                prev_state.downtime_start = None
                logger.info(f"Контейнер {container_name} восстановлен после простоя {downtime_duration}с")
            
            elif current_status != prev_status and current_status != prev_state.last_status:
                # Изменился статус (но не критично)
                await self.telegram_notifier.notify_container_status_change(
                    container_name, prev_status, current_status, current_health
                )
                prev_state.last_status = current_status
            
            self.state.last_update = current_time.isoformat()
            self.save_state()
            
        except Exception as e:
            logger.error(f"Ошибка обработки события Docker: {e}")
    
    def listen_docker_events(self):
        """Прослушивание событий Docker для мгновенных уведомлений (работает в отдельном потоке)"""
        logger.info("Запуск прослушивания Docker Events...")
        
        # Отслеживаем важные события контейнеров
        important_actions = {'start', 'stop', 'die', 'kill', 'pause', 'unpause', 'health_status: unhealthy', 'health_status: healthy', 'restart'}
        
        while not self._stop_events:
            try:
                events = self.docker_client.events(
                    decode=True,
                    filters={'type': 'container'}
                )
                
                for event in events:
                    if self._stop_events:
                        break
                    
                    action = event.get('Action', '')
                    # Фильтруем только важные события
                    if action in important_actions or action.startswith('health_status:'):
                        # Добавляем событие в очередь для обработки в asyncio loop
                        try:
                            self._event_queue.put_nowait(event)
                        except queue.Full:
                            logger.warning("Очередь событий переполнена, пропускаем событие")
                        
            except Exception as e:
                logger.error(f"Ошибка прослушивания Docker Events: {e}")
                # Переподключение через 5 секунд
                import time
                if not self._stop_events:
                    time.sleep(5)
    
    async def check_containers_async(self):
        """Асинхронная проверка состояния всех контейнеров (резервный механизм)"""
        current_time = datetime.now(timezone.utc)
        containers_to_monitor = self.discover_containers()
        
        logger.info(f"Периодическая проверка {len(containers_to_monitor)} контейнеров...")
        
        for container_name in containers_to_monitor:
            status_info = self.get_container_status(container_name)
            
            if status_info is None:
                continue
            
            is_healthy = self.is_container_healthy(status_info)
            current_status = status_info.get('status', 'unknown')
            current_health = status_info.get('health')
            
            # Получаем предыдущее состояние
            prev_state = self.state.containers.get(container_name)
            
            if prev_state is None:
                # Первая проверка контейнера
                self.state.containers[container_name] = ContainerState(
                    name=container_name,
                    status=current_status,
                    health=current_health,
                    last_check=current_time.isoformat(),
                    last_status=current_status
                )
                if not is_healthy:
                    self.state.containers[container_name].downtime_start = current_time.isoformat()
                    await self.telegram_notifier.notify_container_down(
                        container_name, current_status, current_time
                    )
                continue
            
            # Проверяем изменения статуса
            prev_status = prev_state.status
            prev_healthy = self.is_container_healthy({
                'status': prev_status,
                'health': prev_state.health,
                'exists': True
            })
            
            # Обновляем состояние
            prev_state.status = current_status
            prev_state.health = current_health
            prev_state.last_check = current_time.isoformat()
            
            # Обработка изменений
            if not is_healthy and prev_healthy:
                # Контейнер упал
                prev_state.downtime_start = current_time.isoformat()
                await self.telegram_notifier.notify_container_down(
                    container_name, current_status, current_time
                )
                logger.warning(f"Контейнер {container_name} упал: {current_status}")
            
            elif is_healthy and not prev_healthy:
                # Контейнер восстановился
                downtime_duration = 0
                if prev_state.downtime_start:
                    downtime_start = datetime.fromisoformat(prev_state.downtime_start.replace('Z', '+00:00'))
                    downtime_duration = int((current_time - downtime_start).total_seconds())
                
                await self.telegram_notifier.notify_container_up(
                    container_name, downtime_duration, current_time
                )
                prev_state.downtime_start = None
                logger.info(f"Контейнер {container_name} восстановлен после простоя {downtime_duration}с")
            
            elif current_status != prev_status and current_status != prev_state.last_status:
                # Изменился статус (но не критично)
                await self.telegram_notifier.notify_container_status_change(
                    container_name, prev_status, current_status, current_health
                )
                prev_state.last_status = current_status
        
        self.state.last_update = current_time.isoformat()
        self.save_state()
    
    async def process_event_queue(self):
        """Обработка событий из очереди (работает в asyncio loop)"""
        while not self._stop_events:
            try:
                # Получаем событие из очереди с таймаутом
                try:
                    event = self._event_queue.get(timeout=1.0)
                    await self.process_container_event(event)
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
            except Exception as e:
                logger.error(f"Ошибка обработки события из очереди: {e}")
                await asyncio.sleep(1)
    
    def start_periodic_check(self, application: Application):
        """Запуск периодической проверки (резервный механизм)"""
        async def periodic_check():
            while not self._stop_events:
                try:
                    await self.check_containers_async()
                except Exception as e:
                    logger.error(f"Ошибка при периодической проверке контейнеров: {e}")
                
                await asyncio.sleep(self.check_interval)
        
        asyncio.create_task(periodic_check())
    
    def stop(self):
        """Остановка мониторинга"""
        self._stop_events = True
        self.save_state()
        self.executor.shutdown(wait=True)


# Глобальная переменная для доступа к монитору из handlers
monitor_instance: Optional[DockerMonitor] = None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = TelegramNotifier.get_main_keyboard()
    await update.message.reply_text(
        "👋 <b>Добро пожаловать в мониторинг контейнеров!</b>\n\n"
        "Используйте кнопки ниже для управления:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def list_containers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Список контейнеров'"""
    query = update.callback_query
    await query.answer()
    
    if monitor_instance:
        message = monitor_instance.format_containers_list()
        keyboard = TelegramNotifier.get_main_keyboard()
        await query.edit_message_text(
            text=message,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await query.edit_message_text("❌ Мониторинг не инициализирован")


async def status_containers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Статусы контейнеров'"""
    query = update.callback_query
    await query.answer()
    
    if monitor_instance:
        message = monitor_instance.format_containers_status()
        keyboard = TelegramNotifier.get_main_keyboard()
        await query.edit_message_text(
            text=message,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await query.edit_message_text("❌ Мониторинг не инициализирован")


def main():
    """Точка входа"""
    global monitor_instance
    
    # Загрузка конфигурации из переменных окружения
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    check_interval = int(os.getenv('MONITOR_INTERVAL', '60'))
    state_file = os.getenv('MONITOR_STATE_FILE', '/tmp/docker-monitor-state.json')
    monitored_containers = os.getenv('MONITORED_CONTAINERS', '').split(',')
    monitored_containers = [c.strip() for c in monitored_containers if c.strip()]
    
    if not bot_token or not chat_id:
        logger.error("Не указаны TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID")
        return 1
    
    # Создание приложения Telegram
    application = Application.builder().token(bot_token).build()
    
    # Создание уведомителя
    notifier = TelegramNotifier(application, chat_id)
    
    # Создание монитора
    monitor_instance = DockerMonitor(
        telegram_notifier=notifier,
        state_file=state_file,
        check_interval=check_interval,
        monitored_containers=monitored_containers if monitored_containers else None
    )
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(list_containers_callback, pattern="^list_containers$"))
    application.add_handler(CallbackQueryHandler(status_containers_callback, pattern="^status_containers$"))
    
    # Запуск мониторинга
    containers = monitor_instance.discover_containers()
    logger.info(f"Запуск мониторинга для контейнеров: {', '.join(containers)}")
    
    # Запуск прослушивания Docker Events в отдельном потоке
    events_thread = threading.Thread(target=monitor_instance.listen_docker_events, daemon=True)
    events_thread.start()
    
    # Запуск периодической проверки и обработки событий (резервный механизм)
    async def post_init(application: Application):
        # Настройка меню команд бота
        commands = [
            BotCommand("start", "Запустить бота и показать меню управления"),
        ]
        await application.bot.set_my_commands(commands)
        logger.info("Меню команд бота настроено")
        
        # Запускаем обработку событий из очереди
        asyncio.create_task(monitor_instance.process_event_queue())
        # Запускаем периодическую проверку
        monitor_instance.start_periodic_check(application)
        # Отправляем уведомление о запуске
        if containers:
            await notifier.notify_startup(containers)
    
    application.post_init = post_init
    
    # Запуск бота
    logger.info("Запуск Telegram бота...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, stop_signals=None)
    except KeyboardInterrupt:
        logger.info("Остановка мониторинга...")
        monitor_instance.stop()
    
    return 0


if __name__ == '__main__':
    exit(main())
