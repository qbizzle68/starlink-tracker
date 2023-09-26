# Starlink-tracker
Starlink-tracker is a python package for generating data for batches of starlink satellites using
the sattrack satellite prediction library. The main purpose of the package is to facilitate finding
visible passes of Starlink batches in the few days after they're launched, the time when they are
the brightest and most easily visible to the naked eye. The package further divides batches into
orbital planes and smaller subgroups amongst a single batch due to phasing as they progress to
more specific positions in their shells.

## Install
The package can be installed using pip:
```python
pip install starlink-tracker
```
The package requires sattrack and pandas as dependencies which will be installed at the same time.

## Usage
The package can be run from the command line or imported to be used as a utility in your own scripts.

### Command line
To run from the command line, run 
``` bash
python -m starlink ARGS
```
Where ares specify the batch and geo-position inputs. The batch number consists of two components, the
group number and launch number of that group. For example the first launch of group 6 is 6-1, which
should be entered with a space instead of a hyphen, e.g. `6 1`.

The geo-position inputs are latitude and longitude values following the `--geo` flag. Optionally an
elevation in kilometers can be specified after the latitude and longitude inputs. If your coordinates are
unknown, or you wish to use your IP location, you can use the geocoder package to determine your computer's
location with the `--use-geocoder` flag. The `--geo` and `--use-geocoder` flags are mutually exclusive,
and cannot both be set.

Some basic examples are:
``` bash
python -m starlink 6 18 --geo 38 -97
```
Using elevation:
``` bash
python -m starlink 7 1 --geo 38 -97 0.473
```
Using geocoder:
``` bash
python -m starlink 2 1 --use-geocoder
```

For other flags and capabilities use ```python -m starlink --help```.

### Import
The package can also be imported and run from an interpreter or another script or application. Simply
importing with `from starlink import *` should import all functionalities needed. You can run the `main`
function for the same output from the command line. 