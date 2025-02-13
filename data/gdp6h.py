import numpy as np
import pandas as pd
from datetime import datetime
import xarray as xr
import urllib.request
import concurrent.futures
import re
from tqdm import tqdm
import os
from os.path import isfile, join, exists
import warnings


def parse_directory_file(filename: str) -> pd.DataFrame:
    """
    Read a directory file which contains metadata of drifters release

    Note: due to naming of those files, it requires manual intervention to update the last file name after an update of the dataset

    Args:
        filename (str): filename of the dirfl file

    Returns:
        pd.DataFrame: sorted list of drifters
    """
    aoml_dirfl_url = "https://www.aoml.noaa.gov/ftp/pub/phod/buoydata/"

    df = pd.read_csv(join(aoml_dirfl_url, filename), delimiter="\s+", header=None)
    # combine the date and time columns to easily parse dates below
    df[4] += " " + df[5]
    df[8] += " " + df[9]
    df[12] += " " + df[13]
    df = df.drop(columns=[5, 9, 13])
    df.columns = [
        "ID",
        "WMO_number",
        "program_number",
        "buoys_type",
        "Deployment_date",
        "Deployment_lat",
        "Deployment_lon",
        "End_date",
        "End_lat",
        "End_lon",
        "Drogue_off_date",
        "death_code",
    ]
    for t in ["Deployment_date", "End_date", "Drogue_off_date"]:
        df[t] = pd.to_datetime(df[t], format="%Y/%m/%d %H:%M", errors="coerce")
    return df


version = "July 2022"
aoml_https_url = "https://www.aoml.noaa.gov/ftp/pub/phod/lumpkin/netcdf/"
file_pattern = "drifter_{id}.nc"

# create raw data folder and subdirectories
folder = "../data/raw/gdp-6hourly"
aoml_directories = [
    "buoydata_1_5000",
    "buoydata_5001_10000",
    "buoydata_10001_15000",
    "buoydata_15001_jul22",
]
os.makedirs(folder, exist_ok=exists(folder))
for directory in aoml_directories:
    os.makedirs(join(folder, directory), exist_ok=exists(join(folder, directory)))

# read the directory files
file_url = [
    "dirfl_1_5000.dat",
    "dirfl_5001_10000.dat",
    "dirfl_10001_15000.dat",
    "dirfl_15001_jul22.dat",
]
df = pd.concat([parse_directory_file(f) for f in file_url])
df.sort_values(["Deployment_date"], inplace=True, ignore_index=True)


def order_by_date(idx):
    """
    From the previously sorted directory files DataFrame, this function
    returns the drifter indices sorted by their end_date.
    Args:
        idx [list]: list of drifters to include in the ragged array
    Returns:
        idx [list]: sorted list of drifters
    """
    return df.ID[np.where(np.in1d(df.ID, idx))[0]].values


# find out what drifters are part of each directory
dict_id = {}
all_drifter_ids = np.empty(0, dtype="int")
print("Listing AOML directory...")
for directory in aoml_directories:
    print(join(aoml_https_url, directory))
    urlpath = urllib.request.urlopen(join(aoml_https_url, directory))
    string = urlpath.read().decode("utf-8")
    pattern = re.compile("drifter_[0-9]*.nc")
    filelist = pattern.findall(string)
    folder_ids = np.unique([int(f.split("_")[-1][:-3]) for f in filelist])
    all_drifter_ids = np.append(all_drifter_ids, folder_ids)
    dict_id |= dict.fromkeys(folder_ids, directory)


def fetch_netcdf(url, file):
    """
    Download and save file from the given url (if not present)
    """
    if not isfile(file):
        req = urllib.request.urlretrieve(url, file)


def download(drifter_ids: list = None, n_random_id: int = None):
    """
    Download individual netCDF files from the AOML server

    :param drifter_ids [list]: list of drifter to retrieve (Default: all)
    :param n_random_id [int]: randomly select n drifter netCDF files
    :return drifters_ids [list]: list of retrieved drifter
    """
    # load the complete list of drifter IDs
    if drifter_ids is None:
        drifter_ids = all_drifter_ids

    if n_random_id:
        if n_random_id > len(drifter_ids):
            warnings.warn(
                f"Retrieving all listed trajectories because {n_random_id} is larger than the {len(drifter_ids)} listed trajectories."
            )
        else:
            rng = np.random.RandomState(42)
            drifter_ids = sorted(rng.choice(drifter_ids, n_random_id, replace=False))

    with concurrent.futures.ThreadPoolExecutor() as exector:
        # create list of urls and paths
        urls = []
        files = []
        for i in drifter_ids:
            file = f"drifter_{i}.nc"
            directory = dict_id[i]
            urls.append(join(aoml_https_url, directory, file))
            files.append(join(folder, directory, file))

        # parallel retrieving of individual netCDF files
        list(
            tqdm(
                exector.map(fetch_netcdf, urls, files),
                total=len(files),
                desc="Downloading files",
                ncols=80,
            )
        )

    return order_by_date(drifter_ids)


def decode_date(t):
    """
    The date format is specified in 'seconds since 1970-01-01 00:00:00' but the missing values
    are stored as -1e+34 which is not supported by the default parsing mechanism in xarray

    This function returns replaced the missing valye by NaT and return a datetime object.
    :param t: date
    :return: datetime object
    """
    nat_index = np.logical_or(np.isclose(t, -1e34), np.isnan(t))
    t[nat_index] = np.nan
    return t


def fill_values(var, default=np.nan):
    """
    Change fill values (-1e+34, inf, -inf) in var array to value specifed by default
    """
    missing_value = np.logical_or(np.isclose(var, -1e34), ~np.isfinite(var))
    if np.any(missing_value):
        var[missing_value] = default
    return var


def str_to_float(value, default=np.nan):
    """
    :param value: string
    :return: bool
    """
    try:
        fvalue = float(value)
        if np.isnan(fvalue):
            return default
        else:
            return fvalue
    except ValueError:
        return default


def cut_str(value, max_length):
    """
    Cut a string to a specific length.
    :param value: string
           max_length: length of the output
    :return: string with max_length chars
    """
    charar = np.chararray(1, max_length)
    charar[:max_length] = value
    return charar


def drogue_presence(lost_time: float, time: np.array) -> np.array:
    """
    Create drogue status from the drogue lost time and the trajectory time
    :params lost_time: timestamp of the drogue loss (or NaT)
            time[obs]: observation time
    :return: bool[obs]: 1 drogued, 0 undrogued
    """
    if pd.isnull(lost_time) or lost_time >= time[-1]:
        return np.ones_like(time, dtype="bool")
    else:
        return time < lost_time


def rowsize(index: int) -> int:
    return xr.open_dataset(
        join(folder, dict_id[index], file_pattern.format(id=index)),
        decode_cf=False,
        decode_times=False,
        concat_characters=False,
        decode_coords=False,
    ).dims["obs"]


def preprocess(index: int) -> xr.Dataset:
    """
    Mandatory function that extract and preprocess the Lagragangian data and attributes. The function takes and
    identification number that can be used to: create a file or url pattern or select data from a Dataframe. It
    then preprocess the data and return a clean xarray Dataset.

    :param index: drifter's identification number
    :return: xr.Dataset containing the data and attributes
    """

    global dict_id
    if not dict_id:
        list_directories()

    ds = xr.load_dataset(
        join(folder, dict_id[index], file_pattern.format(id=index)),
        decode_times=False,
        decode_coords=False,
    )

    # convert attributes to variable
    ds["DeployingShip"] = (("traj"), cut_str(ds.DeployingShip, 20))
    ds["DeploymentStatus"] = (("traj"), cut_str(ds.DeploymentStatus, 20))
    ds["BuoyTypeManufacturer"] = (("traj"), cut_str(ds.BuoyTypeManufacturer, 20))
    ds["BuoyTypeSensorArray"] = (("traj"), cut_str(ds.BuoyTypeSensorArray, 20))
    ds["CurrentProgram"] = (("traj"), np.int32([str_to_float(ds.CurrentProgram, -1)]))
    ds["PurchaserFunding"] = (("traj"), cut_str(ds.PurchaserFunding, 20))
    ds["SensorUpgrade"] = (("traj"), cut_str(ds.SensorUpgrade, 20))
    ds["Transmissions"] = (("traj"), cut_str(ds.Transmissions, 20))
    ds["DeployingCountry"] = (("traj"), cut_str(ds.DeployingCountry, 20))
    ds["DeploymentComments"] = (
        ("traj"),
        cut_str(ds.DeploymentComments.encode("ascii", "ignore").decode("ascii"), 20),
    )  # remove non ascii char
    ds["ManufactureYear"] = (("traj"), np.int16([str_to_float(ds.ManufactureYear, -1)]))
    ds["ManufactureMonth"] = (
        ("traj"),
        np.int16([str_to_float(ds.ManufactureMonth, -1)]),
    )
    ds["ManufactureSensorType"] = (("traj"), cut_str(ds.ManufactureSensorType, 20))
    ds["ManufactureVoltage"] = (
        ("traj"),
        np.int16([str_to_float(ds.ManufactureVoltage[:-6], -1)]),
    )  # e.g. 56 V
    ds["FloatDiameter"] = (
        ("traj"),
        [str_to_float(ds.FloatDiameter[:-3])],
    )  # e.g. 35.5 cm
    ds["SubsfcFloatPresence"] = (
        ("traj"),
        np.array([str_to_float(ds.SubsfcFloatPresence)], dtype="bool"),
    )
    ds["DrogueType"] = (("traj"), cut_str(ds.DrogueType, 7))
    ds["DrogueLength"] = (("traj"), [str_to_float(ds.DrogueLength[:-2])])  # e.g. 4.8 m
    ds["DrogueBallast"] = (
        ("traj"),
        [str_to_float(ds.DrogueBallast[:-3])],
    )  # e.g. 1.4 kg
    ds["DragAreaAboveDrogue"] = (
        ("traj"),
        [str_to_float(ds.DragAreaAboveDrogue[:-4])],
    )  # 10.66 m^2
    ds["DragAreaOfDrogue"] = (
        ("traj"),
        [str_to_float(ds.DragAreaOfDrogue[:-4])],
    )  # e.g. 416.6 m^2
    ds["DragAreaRatio"] = (("traj"), [str_to_float(ds.DragAreaRatio)])  # e.g. 39.08
    ds["DrogueCenterDepth"] = (
        ("traj"),
        [str_to_float(ds.DrogueCenterDepth[:-2])],
    )  # e.g. 20.0 m
    ds["DrogueDetectSensor"] = (("traj"), cut_str(ds.DrogueDetectSensor, 20))

    # convert type of some variable
    ds["ID"].data = ds["ID"].data.astype("int64")
    ds["WMO"].data = ds["WMO"].data.astype("int32")
    ds["expno"].data = ds["expno"].data.astype("int32")
    ds["typedeath"].data = ds["typedeath"].data.astype("int8")
    ds["CurrentProgram"].data = ds["CurrentProgram"].data.astype("int32")

    # new variables
    ds["ids"] = (["traj", "obs"], [np.repeat(ds.ID.values, ds.dims["obs"])])
    ds["drogue_status"] = (
        ["traj", "obs"],
        [drogue_presence(ds.drogue_lost_date.data, ds.time.data[0])],
    )

    # vars attributes
    vars_attrs = {
        "ID": {"long_name": "Global Drifter Program Buoy ID", "units": "-"},
        "longitude": {"long_name": "Longitude", "units": "degrees_east"},
        "lon360": {"long_name": "Longitude", "units": "degrees_east"},
        "latitude": {"long_name": "Latitude", "units": "degrees_north"},
        "time": {"long_name": "Time", "units": "seconds since 1970-01-01 00:00:00"},
        "ids": {
            "long_name": "Global Drifter Program Buoy ID repeated along observations",
            "units": "-",
        },
        "rowsize": {
            "long_name": "Number of observations per trajectory",
            "sample_dimension": "obs",
            "units": "-",
        },
        "WMO": {
            "long_name": "World Meteorological Organization buoy identification number",
            "units": "-",
        },
        "expno": {"long_name": "Experiment number", "units": "-"},
        "deploy_date": {
            "long_name": "Deployment date and time",
            "units": "seconds since 1970-01-01 00:00:00",
        },
        "deploy_lon": {"long_name": "Deployment longitude", "units": "degrees_east"},
        "deploy_lat": {"long_name": "Deployment latitude", "units": "degrees_north"},
        "end_date": {
            "long_name": "End date and time",
            "units": "seconds since 1970-01-01 00:00:00",
        },
        "end_lon": {"long_name": "End latitude", "units": "degrees_north"},
        "end_lat": {"long_name": "End longitude", "units": "degrees_east"},
        "drogue_lost_date": {
            "long_name": "Date and time of drogue loss",
            "units": "seconds since 1970-01-01 00:00:00",
        },
        "typedeath": {
            "long_name": "Type of death",
            "units": "-",
            "comments": "0 (buoy still alive), 1 (buoy ran aground), 2 (picked up by vessel), 3 (stop transmitting), 4 (sporadic transmissions), 5 (bad batteries), 6 (inactive status)",
        },
        "typebuoy": {
            "long_name": "Buoy type (see https://www.aoml.noaa.gov/phod/dac/dirall.html)",
            "units": "-",
        },
        "DeployingShip": {"long_name": "Name of deployment ship", "units": "-"},
        "DeploymentStatus": {"long_name": "Deployment status", "units": "-"},
        "BuoyTypeManufacturer": {"long_name": "Buoy type manufacturer", "units": "-"},
        "BuoyTypeSensorArray": {"long_name": "Buoy type sensor array", "units": "-"},
        "CurrentProgram": {
            "long_name": "Current Program",
            "units": "-",
            "_FillValue": "-1",
        },
        "PurchaserFunding": {"long_name": "Purchaser funding", "units": "-"},
        "SensorUpgrade": {"long_name": "Sensor upgrade", "units": "-"},
        "Transmissions": {"long_name": "Transmissions", "units": "-"},
        "DeployingCountry": {"long_name": "Deploying country", "units": "-"},
        "DeploymentComments": {"long_name": "Deployment comments", "units": "-"},
        "ManufactureYear": {
            "long_name": "Manufacture year",
            "units": "-",
            "_FillValue": "-1",
        },
        "ManufactureMonth": {
            "long_name": "Manufacture month",
            "units": "-",
            "_FillValue": "-1",
        },
        "ManufactureSensorType": {"long_name": "Manufacture Sensor Type", "units": "-"},
        "ManufactureVoltage": {
            "long_name": "Manufacture voltage",
            "units": "V",
            "_FillValue": "-1",
        },
        "FloatDiameter": {"long_name": "Diameter of surface floater", "units": "cm"},
        "SubsfcFloatPresence": {"long_name": "Subsurface Float Presence", "units": "-"},
        "DrogueType": {"drogue_type": "Drogue Type", "units": "-"},
        "DrogueLength": {"long_name": "Length of drogue.", "units": "m"},
        "DrogueBallast": {
            "long_name": "Weight of the drogue's ballast.",
            "units": "kg",
        },
        "DragAreaAboveDrogue": {"long_name": "Drag area above drogue.", "units": "m^2"},
        "DragAreaOfDrogue": {"long_name": "Drag area drogue.", "units": "m^2"},
        "DragAreaRatio": {"long_name": "Drag area ratio", "units": "m"},
        "DrogueCenterDepth": {
            "long_name": "Average depth of the drogue.",
            "units": "m",
        },
        "DrogueDetectSensor": {"long_name": "Drogue detection sensor", "units": "-"},
        "ve": {"long_name": "Eastward velocity", "units": "m/s"},
        "vn": {"long_name": "Northward velocity", "units": "m/s"},
        "err_lat": {
            "long_name": "Standard error in latitude",
            "units": "degrees_north",
        },
        "err_lon": {
            "long_name": "Standard error in longitude",
            "units": "degrees_east",
        },
        "temp": {
            "long_name": "Sea Surface Bulk Temperature",
            "units": "degree_Celcius",
        },
        "err_temp": {
            "long_name": "Standard error in temperature",
            "units": "degree_Celcius",
        },
        "drogue_status": {
            "long_name": "Status indicating the presence of the drogue",
            "units": "-",
            "flag_values": "1,0",
            "flag_meanings": "drogued, undrogued",
        },
    }

    # global attributes
    attrs = {
        "title": "Global Drifter Program six-hourly drifting buoy collection",
        "history": f"Last update {version}. Metadata from dirall.dat and deplog.dat",
        "Conventions": "CF-1.6",
        "date_created": datetime.now().isoformat(),
        "publisher_name": "GDP Drifter DAC",
        "publisher_email": "aoml.dftr@noaa.gov",
        "publisher_url": "https://www.aoml.noaa.gov/phod/gdp",
        "licence": "freely available",
        "processing_level": "Level 2 QC by GDP drifter DAC",
        "metadata_link": "https://www.aoml.noaa.gov/phod/dac/dirall.html",
        "contributor_name": "NOAA Global Drifter Program",
        "contributor_role": "Data Acquisition Center",
        "institution": "NOAA Atlantic Oceanographic and Meteorological Laboratory",
        "acknowledgement": "Lumpkin, Rick; Centurioni, Luca (2019). NOAA Global Drifter Program quality-controlled 6-hour interpolated data from ocean surface drifting buoys. [indicate subset used]. NOAA National Centers for Environmental Information. Dataset. https://doi.org/10.25921/7ntx-z961. Accessed [date].",
        "summary": "Global Drifter Program six-hourly data",
        "doi": "10.25921/7ntx-z961",
    }

    # set attributes
    for var in vars_attrs.keys():
        ds[var].attrs = vars_attrs[var]
    ds.attrs = attrs

    # set coordinates
    ds = ds.set_coords(["ids", "longitude", "lon360", "latitude", "time"])

    return ds
