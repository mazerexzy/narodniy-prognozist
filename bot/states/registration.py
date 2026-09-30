from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    nickname = State()


class Profile(StatesGroup):
    new_nickname = State()
