"""DIAN provider adapters (T-PR11-04).

Each module here is one concrete adapter behind the ``DianProvider``
ABC. Swapping providers is an operator concern, so the adapters stay
isolated from the dispatcher's state machine.
"""
from __future__ import annotations
