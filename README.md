# clouddrift-examples

This repo provides the example notebooks for the
[CloudDrift](https://github.com/cloud-drift/clouddrift) library.

## Examples

To get a taste of the `clouddrift` package and how it works,
look, and/or run on your computer, these examples:

* [GDP](notebooks/gdp.ipynb): A demo of `clouddrift` working on the
  hourly Global Drifter Program (GDP) data. It shows how to ingest GDP data
  into the `RaggedArray` class, how to emit the data as Xarray Dataset or 
  Awkward Array instances for analysis, and how to read and write ragged
  array data in NetCDF and Apache Parquet file formats.
* [GDP 6-hourly](notebooks/gdp.ipynb): Same as above, but for 6-hourly GDP data
