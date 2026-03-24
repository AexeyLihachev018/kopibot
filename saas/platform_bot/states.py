from aiogram.fsm.state import State, StatesGroup


class RegisterStates(StatesGroup):
    waiting_name = State()       # Ждём имя копирайтера


class AddBotStates(StatesGroup):
    waiting_token = State()      # Ждём токен от BotFather
    waiting_welcome = State()    # Ждём приветственное сообщение
