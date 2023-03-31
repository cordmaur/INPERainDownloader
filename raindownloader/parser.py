"""
The parser module defines the template of a Parser Class.
"""

# from abc import ABC, abstractmethod

import os
from pathlib import Path
from enum import Enum
from typing import Callable, Optional, Union, List
from dateutil import parser

from .utils import DateProcessor, DateFrequency


class BaseParser:
    """Docstring"""

    def __init__(
        self,
        datatype: Union[Enum, str],
        root: str,
        fn_creator: Callable,
        fl_creator: Optional[Callable] = None,
        date_freq: DateFrequency = DateFrequency.DAILY,
    ):
        self.type = datatype
        self.root = Path(root).as_posix()
        self.fn_creator = fn_creator
        self.fl_creator = fl_creator
        self.date_freq = date_freq

    def filename(self, date_str: str) -> str:
        """Return just the filename given a date string"""
        # get the datetime
        date = parser.parse(date_str)

        return self.fn_creator(date)

    def path(self, date_str: str) -> str:
        """Return just the base path given a date string"""
        # get the datetime
        date = parser.parse(date_str)

        if self.fl_creator:
            return os.path.join(self.root, self.fl_creator(date))
        else:
            return self.root

    def target(self, date_str: str) -> str:
        """Target is composed by root / folder / filename"""
        return os.path.join(self.path(date_str), self.filename(date_str))

    def dates_range(self, start_date: str, end_date: str) -> List[str]:
        """Return the dates range within the specified period"""
        return DateProcessor.dates_range(
            start_date=start_date, end_date=end_date, date_freq=self.date_freq
        )
