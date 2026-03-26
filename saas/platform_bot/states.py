from aiogram.fsm.state import State, StatesGroup


class RegisterStates(StatesGroup):
    waiting_name = State()       # Ждём имя копирайтера


class AddBotStates(StatesGroup):
    waiting_token = State()      # Ждём токен от BotFather
    waiting_welcome = State()    # Ждём приветственное сообщение


class CatalogStates(StatesGroup):
    waiting_bot_choice = State()  # Выбор бота (когда ботов > 1)
    waiting_title = State()       # Название услуги
    waiting_description = State() # Описание услуги
    waiting_price = State()       # Цена услуги
