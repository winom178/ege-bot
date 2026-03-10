# handlers/__init__.py
from .common import router as common_router
from .subjects import router as subjects_router
from .tasks import router as tasks_router
from .exam import router as exam_router
from .profile import router as profile_router
from .elements import router as elements_router
from .cheatsheets import router as cheatsheets_router
from .photo import router as photo_router
from .admin import router as admin_router
from .achievements import router as achievements_router
from .repetition import router as repetition_router
from .referral import router as referral_router
from .adaptive import router as adaptive_router
from .daily_challenge import router as daily_challenge_router
from .lava import router as lava_router  # Добавлено для интеграции с LAVA

__all__ = [
    "common_router",
    "subjects_router",
    "tasks_router",
    "exam_router",
    "profile_router",
    "elements_router",
    "cheatsheets_router",
    "photo_router",
    "admin_router",
    "achievements_router",
    "repetition_router",
    "referral_router",
    "adaptive_router",
    "daily_challenge_router",
    "lava_router",  # Добавлено в __all__
]
