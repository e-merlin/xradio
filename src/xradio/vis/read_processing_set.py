import os
import xarray as xr
from ._processing_set import processing_set
import graphviper.utils.logger as logger
from xradio._utils.zarr.common import _open_dataset
import s3fs

def read_processing_set(
    ps_store: str, intents: list = None, fields: str = None
)->processing_set:
    """Creates a lazy representation of a Processing Set (only meta-data is loaded into memory).

    Parameters
    ----------
    ps_store : str
        String of the path and name of the processing set. For example '/users/user_1/uid___A002_Xf07bba_Xbe5c_target.lsrk.vis.zarr'.
    intents : list, optional
        A list of the intents to be read for example ['OBSERVE_TARGET#ON_SOURCE']. The intents in a processing set can be seem by calling processing_set.summary().
        By default None, which will read all intents.
    fields : str, optional
       The list of field names that will be read, by default None which will read all fields. 
       
    Returns
    -------
    processing_set
        Lazy representation of processing set (data is represented by Dask.arrays). 
    """    
    if os.path.isdir(ps_store):
        # default to assuming the data are accessible on local file system
        ps_store_is_s3dir = False
        items = os.listdir(ps_store)

    elif ps_store.startswith("s3"):
        # only if not found locally, check if dealing with an S3 bucket URL
        try:
            # initiatlize the S3 "file system", first attempting to use pre-configured credentials
            s3 = s3fs.S3FileSystem(anon=False, requester_pays=False)
        except PermissionError:
            # only public, read-only buckets will be accessible; might want to add messaging
            s3 = s3fs.S3FileSystem(anon=True)

        if s3.isdir(ps_store):
            ps_store_is_s3dir = True
            if not ps_store.endswith("/"):
                # just for consistency, as there is no os.path equivalent in s3fs
                ps.store.append("/")

        if (len([ff for ff in s3.find(ps_store) if ".zgroup" in ff]) >= 1) == True:
            # surely a stronger guarantee of conformance is desireable,
            # e.g., a processing_set version/spec file ala zarr's .zmeta...
            # and probably a better way to ensure that store contains valid MSv4 datasets, at that
            items = [bd.split(sep='/')[-1] for bd in s3.listdir(ps_store, detail=False)]
    else:
        raise(FileNotFoundError, f"Could not find {ps_store} either locally or in the cloud.")

    ms_xds = xr.Dataset()
    ps = processing_set()
    data_group = 'base'
    for ms_dir_name in items:
        if "ddi" in ms_dir_name:
            if ps_store_is_s3dir:
                store_path = ps_store+ms_dir_name
                store_path_main = store_path + "/MAIN"
            else:
                store_path_main = os.path.join(ps_store, ms_dir_name, "MAIN")
                store_path = os.path.split(store_path_main)[0]
            xds = _open_dataset(store_path_main)

            if (intents is None) or (xds.attrs["intent"] in intents):
                data_name = _get_data_name(xds, data_group)

                if (fields is None) or (
                    xds[data_name].attrs["field_info"]["name"] in fields
                ):
                    xds.attrs = {
                        **xds.attrs,
                        **_read_sub_xds(store_path),
                    }
                    ps[ms_dir_name] = xds
    return ps


def _read_sub_xds(ms_store, load=False):
    sub_xds_dict = {}

    sub_xds = {
        "antenna_xds": "ANTENNA",
    }
    for sub_xds_key, sub_xds_name in sub_xds.items():
        sub_xds_dict[sub_xds_key] = _open_dataset(
            os.path.join(ms_store, sub_xds_name), load=load
        )

    optional_sub_xds = {
        "weather_xds": "WEATHER",
        "pointing_xds": "POINTING",
    }
    for sub_xds_key, sub_xds_name in optional_sub_xds.items():
        sub_xds_path = os.path.join(ms_store, sub_xds_name)
        if os.path.isdir(sub_xds_path):
            sub_xds_dict[sub_xds_key] = _open_dataset(sub_xds_path, load=load)

    return sub_xds_dict


def _get_data_name(xds, data_group):
    if "visibility" in xds.attrs["data_groups"][data_group]:
        data_name = xds.attrs["data_groups"][data_group]["visibility"]
    elif "spectrum" in xds.attrs["data_groups"][data_group]:
        data_name = xds.attrs["data_groups"][data_group]["spectrum"]
    else:
        error_message = (
            "No Visibility or Spectrum data variable found in data_group "
            + data_group
            + "."
        )
        logger.exception(error_message)
        raise ValueError(error_message)
    return data_name
