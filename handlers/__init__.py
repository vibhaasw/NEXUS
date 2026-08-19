"""Handler dispatch system for voice-controlled task routing."""

from handlers.base import HandlerResult, BaseHandler, HandlerRegistry
from handlers.qa_handler import QAHandler
from handlers.code_handler import CodeHandler
from handlers.web_search_handler import WebSearchHandler
from handlers.open_app_handler import OpenAppHandler
from handlers.edit_file_handler import EditFileHandler

__all__ = [
    "HandlerResult",
    "BaseHandler",
    "HandlerRegistry",
    "QAHandler",
    "CodeHandler",
    "WebSearchHandler",
    "OpenAppHandler",
    "EditFileHandler",
]
