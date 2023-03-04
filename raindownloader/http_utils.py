# This module brings util functions to deal with HTTP file structure
# it uses mainly BeautifulSoup to parse and navigate through the directories
import os
from pathlib import Path
from typing import List, Union
from urllib.parse import urljoin, urlparse
from enum import Enum
import re
from datetime import datetime
from abc import ABC, abstractmethod


import pytz

from dateutil.parser import parse

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


def is_url(url):
    regex = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9-]+\.)+[A-Z]{2,}|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or IP
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return re.match(regex, url) is not None


def is_valid_year(year_str: str) -> bool:
    """Docstring"""
    pattern = r"^[1-9]\d{0,3}$"
    return bool(re.match(pattern, year_str))


def is_valid_month_number(s):
    """Docstring"""
    pattern = r"^\d{2}$"
    return bool(re.match(pattern, s))


class Urls:  # pylint: disable=too-few-public-methods
    """Docstring"""

    MERGE = "http://ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/DAILY/"


class HTTPFile:
    """Docstring"""

    def __init__(self, url: str) -> None:
        if url.endswith("/"):
            raise IsADirectoryError(f"{url} is not a valid file")

        self.url = url
        self.header = self.get_header(url)
        self.info = self.parse_header(self.header)

    @staticmethod
    def get_header(url: str) -> dict:
        """Get header of the file as a dictionary."""
        response = requests.head(url, timeout=30)

        if not response.ok:
            response.raise_for_status()

        return dict(response.headers)

    @staticmethod
    def parse_header(header: dict):
        """Docstring"""

        # preserve the original header
        info = header.copy()

        # parse the dates and convert to Brazil/East timezone (Brasilia)
        new_tz = pytz.timezone("Brazil/East")

        info["Request_time"] = (
            parse(header["Date"]).astimezone(new_tz).replace(tzinfo=None)
        )
        info["Last-Modified"] = (
            parse(header["Last-Modified"]).astimezone(new_tz).replace(tzinfo=None)
        )
        del info["Date"]
        return info

    @property
    def filename(self) -> str:
        """Docstring"""
        return os.path.basename(urlparse(self.url).path)

    def download(self, folder: Union[str, Path]) -> Path:
        """Docstring"""
        path = Path(folder)

        # Create the path if it does not exists
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        response = requests.get(self.url, timeout=30)

        if not response.ok:
            response.raise_for_status()

        # set the target file path
        target = path / self.filename
        with open(target, "wb") as file:
            file.write(response.content)

        # now preserve the mtime from the server
        mtime = self.info["Last-Modified"].timestamp()
        os.utime(target, (mtime, mtime))

        return target

    def __repr__(self):
        return f"HTTP File at: {self.url}"


class MERGFile(HTTPFile):
    """Docstring"""

    ext = "grib2"

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.info.update(self.parse_name(self.filename))

    @staticmethod
    def parse_name(filename: str) -> dict:
        """Parse filename in this format MERGE_CPTEC_20000702.ctl"""
        filename, extension = filename.split(".")
        model, provider, date = filename.split("_")

        return dict(model=model, provider=provider, date=parse(date), ext=extension)


class OSFile:  # pylint: disable=too-few-public-methods
    """Docstring"""

    def __init__(self, path: Path) -> None:
        self.path = path

        self.info = self.get_file_info(path)

    @staticmethod
    def get_file_info(path: Path) -> dict:
        """
        Get the basic info from a file in the filesystem, such as:
        size, creation_date, modification_date, accessdate
        """
        status = path.stat()

        return dict(
            atime=datetime.fromtimestamp(status.st_atime),
            ctime=datetime.fromtimestamp(status.st_ctime),
            mtime=datetime.fromtimestamp(status.st_mtime),
            birthtime=datetime.fromtimestamp(status.st_birthtime),
            size=(status.st_size),
        )


class NamedOSFile(OSFile):
    """Aqui poderiamos criar o NamedOSFile que recebe o parser e funcionaria com qualquer arquivo"""

    def __init__(self, path: Path, name_parser=MERGFile.parse_name) -> None:
        super().__init__(path)
        self.info.update(name_parser(path.name))


class RainType(Enum):
    """Docstring"""

    MERGE = MERGFile


class FileSystem(ABC):
    """Docstring"""

    @property
    @abstractmethod
    def items(self) -> List:
        """Docstring"""

    @property
    @abstractmethod
    def files(self) -> List:
        """Docstring"""

    @property
    @abstractmethod
    def folders(self) -> List:
        """Docstring"""

    @abstractmethod
    def open_folder(self, subfolder: str):
        """Docstring"""


class FileItem(ABC):
    pass


class HTTPFileSystem(FileSystem):
    """Docstring"""

    def __init__(self, url: str) -> None:
        # Load the target page
        response = requests.get(url, timeout=30)

        # raise HTTP error if don't get a response
        if not response.ok:
            response.raise_for_status()

        # get HTML content into a BeautifulSoup instance
        # print(f"Getting contents from {url}")

        html_content = response.content.decode("utf-8")
        self.soup = BeautifulSoup(html_content, "html.parser")

        # stores the current directory
        self.url = url

    @property
    def items(self) -> List[Tag]:
        """Returns only the valid links. Exluding parent dir, headers, etc."""
        links = self.soup.find_all("a")

        # Add absolute href to links
        valid_links = []
        for l in links:
            l.attrs["abs_href"] = urljoin(self.url, l.attrs["href"])

            if (l.get("href")[0] != "?") and (l.get("href")[0] != "/"):
                valid_links.append(l)

        return valid_links

    @property
    def files(self) -> List[Tag]:
        """Return the files in the directory"""
        return [l for l in self.items if not l.attrs["href"].endswith("/")]

    @property
    def folders(self) -> List[Tag]:
        """Return the folders in the directory"""
        return [l for l in self.items if l.attrs["href"].endswith("/")]

    def open_folder(self, subfolder: str):
        """Return a HTTPFileSystem for the desired folder"""
        return HTTPFileSystem(self.url + subfolder)


class OSFileSystem(FileSystem):
    """Docstring"""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

        if not self.path.exists():
            self.path.mkdir(parents=True)

    @property
    def items(self) -> List[Path]:
        return list(self.path.iterdir())

    @property
    def files(self) -> List[Path]:
        return [f for f in self.items if f.is_file()]

    @property
    def folders(self) -> List[Path]:
        return [f for f in self.items if f.is_dir()]

    def open_folder(self, subfolder: str):
        """Docstring"""
        return OSFileSystem(self.path / subfolder)


class INPEStructure:
    """Docstring"""

    def __init__(self, address: Union[str, Path]) -> None:
        if isinstance(address, Path) or not is_url(address):
            self.filesystem = OSFileSystem(address)
        else:
            self.filesystem = HTTPFileSystem(address)

    @property
    def years(self):
        """Docstring"""
        return [f for f in self.filesystem.folders if is_valid_year(f.name[:-1])]


class INPEHTTPFileSystem:
    """Docstring"""

    def __init__(self, url=Urls.MERGE, raintype=RainType.MERGE) -> None:

        # create a filesystem
        self.fs = HTTPFileSystem(url)
        self.rain_parser = raintype.value

    @property
    def years(self):
        """Docstring"""
        return [f.text[:-1] for f in self.fs.folders if is_valid_year(f.text[:-1])]

    def months_by_year(self, year: str):
        """Get the months available within a specific year"""
        folders = self.fs.open_folder(year + "/").folders
        return [f.text[:-1] for f in folders if is_valid_month_number(f.text[:-1])]

    def files_by_month(self, year: str, month: str) -> List[Tag]:
        """Docstring"""
        fs = self.fs.open_folder(year + "/").open_folder(month.zfill(2) + "/")
        files = [f for f in fs.files if f.text.split(".")[-1] == self.rain_parser.ext]
        return files

    def dates_by_month(self, year: str, month: str) -> List:
        """Docstring"""
        return [
            self.rain_parser.parse_name(f.text)["date"]
            for f in self.files_by_month(year=year, month=month)
        ]

    def get_file(self, date: str) -> HTTPFile:
        """
        Get the HTTPFile instance corresponding to the given date.
        Date can be informed in any string format accepted by dateutil parser
        """
        dt = parse(date)
        files = self.files_by_month(year=str(dt.year), month=str(dt.month).zfill(2))

        links = [f for f in files if dt.strftime("%Y%m%d") in f.text]
        if len(links) == 0:
            raise LookupError(
                f"No '.{self.rain_parser.ext}' files found for date {date}"
            )

        if len(links) > 1:
            raise LookupError(
                f"More than 1 '.{self.rain_parser.ext}' file found for date {date}"
            )

        link = links[0]
        return self.rain_parser(str(link["abs_href"]))
