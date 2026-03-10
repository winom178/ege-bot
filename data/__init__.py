# data/__init__.py

from .chemistry import TASKS as chemistry_tasks, VIDEO_LINKS as chemistry_videos
from .biology import TASKS as biology_tasks, VIDEO_LINKS as biology_videos
from .math import TASKS as math_tasks, VIDEO_LINKS as math_videos
from .physics import TASKS as physics_tasks, VIDEO_LINKS as physics_videos
from .informatics import TASKS as informatics_tasks, VIDEO_LINKS as informatics_videos
from .history import TASKS as history_tasks, VIDEO_LINKS as history_videos
from .geography import TASKS as geography_tasks, VIDEO_LINKS as geography_videos
from .social import TASKS as social_tasks, VIDEO_LINKS as social_videos
from .literature import TASKS as literature_tasks, VIDEO_LINKS as literature_videos
from .russian import TASKS as russian_tasks, VIDEO_LINKS as russian_videos

# Объединяем словари заданий
TASKS = {}
TASKS.update(chemistry_tasks)
TASKS.update(biology_tasks)
TASKS.update(math_tasks)
TASKS.update(physics_tasks)
TASKS.update(informatics_tasks)
TASKS.update(history_tasks)
TASKS.update(geography_tasks)
TASKS.update(social_tasks)
TASKS.update(literature_tasks)
TASKS.update(russian_tasks)

# Объединяем словари видео
VIDEO_LINKS = {}
VIDEO_LINKS.update(chemistry_videos)
VIDEO_LINKS.update(biology_videos)
VIDEO_LINKS.update(math_videos)
VIDEO_LINKS.update(physics_videos)
VIDEO_LINKS.update(informatics_videos)
VIDEO_LINKS.update(history_videos)
VIDEO_LINKS.update(geography_videos)
VIDEO_LINKS.update(social_videos)
VIDEO_LINKS.update(literature_videos)
VIDEO_LINKS.update(russian_videos)
