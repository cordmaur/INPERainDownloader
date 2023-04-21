"""
The parser module defines the template of a Parser Class.
"""

# from abc import ABC, abstractmethod

import os
from pathlib import Path
from enum import Enum
from typing import Callable, Optional, Union, List
from dateutil import parser
from datetime import datetime

from .utils import DateProcessor, DateFrequency, FTPUtil, OSUtil


class BaseParser:
    """
    This class implements a Base Parser that is responsible for getting to the
    desired file and downloading it. For that, we should provide:

    datatype: To which type this data refers to. This can be a string (e.g., 'MonthlyAverage')
    root: The root folder in the FTP that stores this data (e.g., /modelos/tempo/MERGE/GPM/CLIMATOLOGY/MONTHLY_AVERAGE/)
    fn_creator: This is the FileName creator. This function is responsible for getting a datetime
                and providing the target filename, for example: MERGE_CPTEC_mean_apr.nc
    fl_creator: This is the Folder creator. This funciton is responsible for getting a date string
                and providing the target folder, when it has sub-structures, for example:
                '/DAILY/2001/02/' in the case of Daily rain
    date_freq: The frequency of the file. DateFrequency.[DAILY, MONTHLY, YEARLY]
    """

    def __init__(
        self,
        datatype: Union[Enum, str],
        root: str,
        fn_creator: Callable,
        fl_creator: Optional[Callable] = None,
        date_freq: DateFrequency = DateFrequency.DAILY,
        ftp: Optional[FTPUtil] = None,
        avoid_update: bool = True,
        post_proc: Optional[Callable] = None,
    ):
        self.datatype = datatype
        self.root = Path(root).as_posix()
        self.fn_creator = fn_creator
        self.fl_creator = fl_creator
        self.date_freq = date_freq
        self._ftp = ftp
        self.avoid_update = avoid_update
        self.post_proc = post_proc

    @property
    def ftp(self):
        """Retrieve the internal ftp object"""
        if self._ftp is None:
            raise ValueError(
                f"FTPUtil instance not initialized in the parser {self.datatype}. \nSet it in .ftp."
            )
        else:
            return self._ftp

    @ftp.setter
    def ftp(self, ftp: FTPUtil):
        """Set internal ftp object"""
        self._ftp = ftp

    @property
    def subfolder(self) -> str:
        """Return the subfolder to place files based on the datatype"""
        if isinstance(self.datatype, Enum):
            return self.datatype.name
        else:
            return self.datatype

    def clean_local_folder(self, local_folder: Union[str, Path]) -> None:
        """Clear the .idx files in the local download folder"""

        # get the local path
        local_path = self.local_path(local_folder=local_folder)

        # get idx files
        for file in local_path.glob("*.idx"):
            file.unlink()

    ### File/folder structure functions
    def filename(self, date: Union[str, datetime]) -> str:
        """Return just the filename given a date string"""
        # get the datetime
        date = DateProcessor.parse_date(date)

        return self.fn_creator(date)

    def local_path(self, local_folder: Union[Path, str]) -> Path:
        """Create the local path based on the data type"""

        # create the local path (raises exception if local_folder does not exists)
        local_path = Path(local_folder) / self.subfolder

        local_path.mkdir(parents=False, exist_ok=True)
        return local_path

    def local_target(
        self, date: Union[str, datetime], local_folder: Union[Path, str]
    ) -> Path:
        """
        Local target is the full path of the local file, given a date_str
        """
        return self.local_path(local_folder) / self.filename(date)

    def remote_path(self, date: Union[str, datetime]) -> str:
        """Return just the base path given a date string"""
        # get the datetime
        date = DateProcessor.parse_date(date)

        if self.fl_creator:
            return os.path.join(self.root, self.fl_creator(date))
        else:
            return self.root

    def remote_target(self, date: Union[str, datetime]) -> str:
        """Target is composed by root / folder / filename"""
        return os.path.join(self.remote_path(date), self.filename(date))

    def dates_range(self, start_date: str, end_date: str) -> List[str]:
        """Return the dates range within the specified period"""
        return DateProcessor.dates_range(
            start_date=start_date, end_date=end_date, date_freq=self.date_freq
        )

    ### Download functions
    def download_file(
        self, date: Union[str, datetime], local_folder: Union[Path, str]
    ) -> Path:
        """
        Download the parsed file to a local subfolder (according to the parser datatype).
        OBS: Download file always force the download. Otherwise, use the `get_file` function
        """

        # Download the file directly
        downloaded_file = self.ftp.download_ftp_file(
            remote_file=self.remote_target(date=date),
            local_folder=self.local_path(local_folder=local_folder),
        )

        return downloaded_file

    def is_downloaded(
        self,
        date: Union[str, datetime],
        local_folder: Union[str, Path],
    ) -> bool:
        """Compare remote and local files and return if they are equal"""

        # create target to the local file
        local_target = self.local_target(date=date, local_folder=local_folder)

        # if the file does not exist, exit with false
        if not local_target.exists():
            return False

        # if it exists locally and avoid update is True, we can confirm it is already downloaded
        if self.avoid_update:
            return True

        ### Check if file has changed in the server
        # create a string pointing to the remote file and get its info
        remote_file = self.remote_target(date)

        # Now we need to compare the remote and local files
        local_info = OSUtil.get_local_file_info(local_target)

        result = self.ftp.file_changed(remote_file=remote_file, file_info=local_info)

        return result

    def get_file(
        self,
        date: Union[str, datetime],
        local_folder: Union[str, Path],
        force_download: bool = False,
    ) -> Path:
        """
        Get a specific file. If it is not available locally, download it just in time.
        If it is available locally and avoid_update is not True, check if the file has
        changed in the server
        """

        if force_download or not self.is_downloaded(
            date=date, local_folder=local_folder
        ):
            return self.download_file(date=date, local_folder=local_folder)

        else:
            return self.local_target(date=date, local_folder=local_folder)

    def get_files(
        self,
        dates: List[str],
        local_folder: Union[str, Path],
        force_download: bool = False,
    ) -> List[Path]:
        """
        Download files from a list of dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """
        files = []
        for date in dates:
            files.append(
                self.get_file(
                    date=date,
                    local_folder=local_folder,
                    force_download=force_download,
                )
            )

        return files

    def get_range(
        self,
        start_date: str,
        end_date: str,
        local_folder: Union[str, Path],
        force_download: bool = False,
    ) -> List[Path]:
        """
        Download a range of files from start to end dates and receives a list pointing to the files.
        If there is a problem during the download of one file, a message error will be in the list.
        """
        dates = self.dates_range(start_date, end_date)
        return self.get_files(
            dates=dates,
            local_folder=local_folder,
            force_download=force_download,
        )
