from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    new_tournament_title = State()
    round_text = State()
    add_matches_text = State()     # data: round_id
    new_admin_username = State()
