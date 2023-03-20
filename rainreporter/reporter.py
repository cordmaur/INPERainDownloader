"""
Main module for the reporter class
"""
from pathlib import Path
from typing import Union

import geopandas as gpd
import contextily as cx
import rasterio as rio

from raindownloader.inpedownloader import INPEDownloader
from raindownloader.inpe import INPE
from raindownloader.utils import FileType, GISUtil


class RainReporter:
    """Docstring"""

    def __init__(
        self,
        server: str,
        remote_folder: str,
        download_folder: Union[Path, str],
        filename_fn=INPE.MERGE_filename,
        structure_fn=INPE.MERGE_structure,
    ):
        self.downloader = INPEDownloader(
            server=server,
            root=remote_folder,
            filename_fn=filename_fn,
            structure_fn=structure_fn,
        )

        self.download_folder = Path(download_folder)

    def accum_rain(self, start_date: str, end_date: str):
        """Get the accumulated rain in a given period"""

        # download the files
        files = self.downloader.download_range(
            start_date=start_date,
            end_date=end_date,
            local_folder=self.download_folder,
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
    ):
        """
        Given a time period and a shapefile, plot the rain within the shape
        """

        # first, let's grab the rain
        rain = self.accum_rain(
            start_date=start_date,
            end_date=end_date,
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

        # to use contextily, we will write the raster to a MemoryFile
        # so we don't need to write it to disk and reload it
        # first we will create a profile
        array = rain.to_array()
        profile = GISUtil.profile_from_xarray(array)

        plt_ax = shp.plot(figsize=(5, 5), alpha=0.5, edgecolor="k")

        # create a memory file and use it to create a memory dataset
        with rio.MemoryFile() as memfile:
            with memfile.open(**profile) as memdset:

                # write the data to the newly created dataset
                memdset.write(array)

            # with the dataset in memory, add the basemap
            cx.add_basemap(plt_ax, source=memfile)

        # plot rain inside shape

        # cx.add_basemap(ax, source='../tmp/output_raster.tif', crs=chuva.crs, reset_extent=True, vmin=0, vmax=1)
