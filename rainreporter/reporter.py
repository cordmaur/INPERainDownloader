"""
Main module for the reporter class
"""
from pathlib import Path
from typing import Union
import tempfile

import geopandas as gpd
import contextily as cx

from raindownloader.inpedownloader import INPEDownloader
from raindownloader.inpe import INPE
from raindownloader.utils import FileType


class RainReporter:
    """Docstring"""

    def __init__(
        self,
        server: str,
        root: str,
        filename_fn=INPE.MERGE_filename,
        structure_fn=INPE.MERGE_structure,
    ):
        self.downloader = INPEDownloader(
            server=server, root=root, filename_fn=filename_fn, structure_fn=structure_fn
        )

    def accum_rain(
        self, start_date: str, end_date: str, download_folder: Union[str, Path]
    ):
        """Get the accumulated rain in a given period"""

        # download the files
        files = self.downloader.download_range(
            start_date=start_date,
            end_date=end_date,
            local_folder=download_folder,
            file_type=FileType.GEOTIFF,
        )

        # create a cube
        cube = INPEDownloader.create_cube(
            files=files,
            name_parser=INPE.parse_MERGE_filename,
            dim_key="date",
            squeeze_dims="band",
        )

        # accumulate the rain in the time axis
        accum = cube.sum(dim="date")

        return accum

    def rain_in_shape(
        self,
        start_date: str,
        end_date: str,
        shapefile: Union[str, Path],
        download_folder: Union[str, Path],
    ):
        """
        Given a time period and a shapefile, plot the rain within the shape
        """

        # first, let's grab the rain
        rain = self.accum_rain(
            start_date=start_date, end_date=end_date, download_folder=download_folder
        )

        # then, open the shapefile
        shp = gpd.read_file(shapefile)

        # check if there is something in the shapefile
        if len(shp) == 0:
            raise ValueError("No elements in the input shapefile")

        if len(shp) > 1:
            print(f"{len(shp)} found in shapefile, selecting the first one.")

        # convert the shapefile to the raster CRS (more cost effective)
        shp.to_crs(rain.rio.crs, inplace=True)

        # to use contextily, we need to save the raster to disk (unfortunately)
        # for that, we will create a tempfile and delete it just after
        tmpfile = tempfile.NamedTemporaryFile(suffix=".tif")
        # rain.

        # plot rain inside shape
        ax = shp.plot(figsize=(5, 5), alpha=0.5, edgecolor="k")

        # cx.add_basemap(ax, source='../tmp/output_raster.tif', crs=chuva.crs, reset_extent=True, vmin=0, vmax=1)
