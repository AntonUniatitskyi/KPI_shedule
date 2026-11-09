from aiogram import Router

from handlers import chats, commands, inputs, links, menu, subjects

router = Router()
router.include_router(commands.router)
router.include_router(chats.router)
router.include_router(menu.router)
router.include_router(subjects.router)
router.include_router(links.router)
router.include_router(inputs.router)  # останнім: ловить будь-який текст у станах FSM