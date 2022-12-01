# clouddrift-examples

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/philippemiron/clouddrift-examples/main?labpath=notebooks)

This repo provides the example notebooks for the
[CloudDrift](https://github.com/cloud-drift/clouddrift) library.

## Content

To get a taste of the `clouddrift` package and how it works,
look, and/or run on your computer, a number of example notebooks are available:

* [GDP](notebooks/gdp.ipynb): A demo of `clouddrift` working on the hourly dataset of the [NOAA Global Drifter Program (GDP)](https://www.aoml.noaa.gov/global-drifter-program/). It shows how to ingest GDP data into the `RaggedArray` class, how to emit the data as xarray Dataset or Awkward Array instances for analysis, and how to read and write ragged array data in NetCDF and Apache Parquet file formats.
* [GDP 6-hourly](notebooks/gdp.ipynb): Same as above, but for 6-hourly GDP dataset.
* [GLAD](notebooks/glad.ipynb): An example notebook for the [CARTHE GLAD](http://carthe.org/glad/) dataset.
* [Simulation data](notebooks/simulation-data.ipynb): An example using a dataset from a Lagrangian simulation experiment.

## Running the notebooks on your computer

### Get the code

```
git clone https://github.com/cloud-drift/clouddrift-examples
cd clouddrift-examples
```

### Create a Python environment and install dependencies

```
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install .
```

### Run the notebooks

You can now start the Jupyter server with the GDP notebook like this

```
jupyter notebook notebooks/gdp.ipynb
```

and similarly for the other notebooks.
