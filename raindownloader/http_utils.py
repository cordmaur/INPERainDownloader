# This module brings util functions to deal with HTTP file structure
# it uses mainly BeautifulSoup to parse and navigate through the directories
import os
import requests
from pathlib import Path
from dateutil.parser import parse
from urllib.parse import urljoin, urlparse
from urllib.request import urlretrieve

from bs4 import BeautifulSoup
from bs4.element import Tag

from typing import Optional, List, Union
from enum import Enum

import re


def is_valid_year(year_str: str) -> bool:
    pattern = r"^[1-9]\d{0,3}$"
    return bool(re.match(pattern, year_str))


def is_valid_month_number(s):
    pattern = r"^\d{2}$"
    return bool(re.match(pattern, s))


class Urls:
    MERGE = "http://ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/DAILY/"


class HTTPFile:
    def __init__(self, url: str) -> None:
        if url.endswith("/"):
            raise Exception(f"{url} is not a valid file")

        self.url = url
        self.header = self.get_header(url)
        self.info = self.parse_header(self.header)

    @staticmethod
    def get_header(url: str) -> dict:
        """Get header of the file as a dictionary."""
        response = requests.head(url)

        if not response.ok:
            response.raise_for_status()

        return dict(response.headers)

    @staticmethod
    def parse_header(header: dict):
        info = header.copy()
        info["Request_time"] = parse(header["Date"])
        info["Last-Modified"] = parse(header["Last-Modified"])
        del info["Date"]
        return info

    @property
    def filename(self) -> str:
        return os.path.basename(urlparse(self.url).path)

    def download(self, folder: Union[str, Path]) -> Path:
        path = Path(folder)

        # Create the path if it does not exists
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)

        response = requests.get(self.url)

        if not response.ok:
            response.raise_for_status()

        with open(path / self.filename, "wb") as f:
            f.write(response.content)

        return path / self.filename

    def __repr__(self):
        return f"HTTP File at: {self.url}"


class MERGEFile(HTTPFile):
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


class RainType(Enum):
    MERGE = MERGEFile


class HTTPFileSystem:
    def __init__(self, url: str) -> None:
        # Load the target page
        response = requests.get(url)

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
    def links(self) -> List[Tag]:
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
        return [l for l in self.links if not l.attrs["href"].endswith("/")]

    @property
    def folders(self) -> List[Tag]:
        """Return the folders in the directory"""
        return [l for l in self.links if l.attrs["href"].endswith("/")]

    def open_folder(self, subfolder: str):
        """Return a HTTPFileSystem for the desired folder"""
        return HTTPFileSystem(self.url + subfolder)


class INPEHTTPFileSystem:
    def __init__(self, url=Urls.MERGE, raintype=RainType.MERGE) -> None:

        # create a filesystem
        self.fs = HTTPFileSystem(url)
        self.rain_parser = raintype.value

    @property
    def years(self):
        return [f.text[:-1] for f in self.fs.folders if is_valid_year(f.text[:-1])]

    def months_by_year(self, year: str):
        """Get the months available within a specific year"""
        folders = self.fs.open_folder(year + "/").folders
        return [f.text[:-1] for f in folders if is_valid_month_number(f.text[:-1])]

    def files_by_month(self, year: str, month: str) -> List[Tag]:
        fs = self.fs.open_folder(year + "/").open_folder(month.zfill(2) + "/")
        files = [f for f in fs.files if f.text.split(".")[-1] == self.rain_parser.ext]
        return files

    def dates_by_month(self, year: str, month: str) -> List:
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
            raise Exception(f"No '.{self.rain_parser.ext}' files found for date {date}")
        elif len(links) > 1:
            raise Exception(
                f"More than 1 '.{self.rain_parser.ext}' file found for date {date}"
            )
        else:
            link = links[0]
            return self.rain_parser(str(link["abs_href"]))
