"""Все FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class AuthSG(StatesGroup):
    fio = State()
    code = State()


class OnbSG(StatesGroup):
    pair = State()
    tmrw = State()
    tmrw_time = State()
    misc = State()
    theme = State()


class CabSG(StatesGroup):
    tmrw_time = State()


class AttSG(StatesGroup):
    pick = State()


class HwNewSG(StatesGroup):
    title = State()
    task = State()
    due = State()
    expl = State()
    files = State()
    input = State()
    preview = State()


class SchImpSG(StatesGroup):
    wait = State()


class SchEdSG(StatesGroup):
    room = State()
    time = State()
    add_room = State()


class TbNewSG(StatesGroup):
    title = State()
    desc = State()
    files = State()


class TbEdSG(StatesGroup):
    input = State()
    files = State()


class DiscNewSG(StatesGroup):
    name = State()
    emoji = State()
    teacher = State()


class DiscEdSG(StatesGroup):
    input = State()


class StudNewSG(StatesGroup):
    fio = State()


class BcSG(StatesGroup):
    text = State()
    confirm = State()
