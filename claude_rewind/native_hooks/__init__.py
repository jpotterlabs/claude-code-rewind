"""Native hooks integration for Claude Code 2.0."""

from .registration import register_native_hooks, unregister_hooks
from .handlers import NativeHookDispatcher
from .events import HookEvent, HookEventType

__all__ = [
    'register_native_hooks',
    'unregister_hooks',
    'NativeHookDispatcher',
    'HookEvent',
    'HookEventType',
]
