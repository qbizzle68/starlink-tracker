import argparse
import datetime

import geocoder
from sattrack.coordinates import GeoPosition
from sattrack.spacetime import now, JulianDate


def dataTimeToJulianDate(date_string):
    """Create a JulianDate instance via the datetime interface using an iso formatted string."""

    dt = datetime.datetime.fromisoformat(date_string)
    jd = JulianDate.fromDatetime(dt)

    return jd


def createGeoPosition(geo_string):
    """Create a geo position from components from CLI arguments."""

    args = geo_string.split(' ')
    if len(args) not in (2, 3):
        raise argparse.ArgumentError(geo_string, 'geo argument must have 2 or 3 components')

    return GeoPosition(*(float(a) for a in args))


class geoCoderAction(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        """Use geocoder package to retrieve users geo-position."""

        g = geocoder.ip('me')
        geo = GeoPosition(g.latlng[0], g.latlng[1])

        setattr(namespace, 'geo', geo)


class reduceGeoAction(argparse.Action):

    def __call__(self, parser, namespace, value, option_string=None):
        # Basically a conversion method to convert value from list to GeoPosition. I think this is needed
        # because of the nargs='?' used with the --geo argument. The parser expects a list even though we convert
        # a list of floats into a GeoPosition instance.

        setattr(namespace, self.dest, value[0])


# delete this later
__package__ = 'starlink'
__version__ = '0.1.0'
def createParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute batch specific starlink data.", prog=__package__)
    parser.add_argument('group_number', metavar='group-number', help='the group number the batch belongs to')
    parser.add_argument('launch_number', metavar='launch-number', help='the launch number of the group the batch is from')

    geoGroup = parser.add_mutually_exclusive_group(required=True)
    # use a sub-parser for this?
    geoGroup.add_argument('--geo', metavar='geo-position', nargs='+', type=createGeoPosition, action=reduceGeoAction,
                          help='geolocation values for computing passes, syntax: lat lng [elv]')
    geoGroup.add_argument('--use-geocoder', action=geoCoderAction, nargs=0, default=False, type=bool,
                          help='use geocoder package to automatically detect user geolocation')

    parser.add_argument('-n', '--visible_number', type=int, default=1,
                        help='the nth visible pass from the time given, default is 1')
    parser.add_argument('--time', type=dataTimeToJulianDate, default=now(),
                        help='time to begin looking for visible passes, default is current time')
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')

    showPassGroup = parser.add_mutually_exclusive_group()
    showPassGroup.add_argument('--hide-pass', help="don't print visible pass information", dest='includePass',
                               action='store_false')
    showPassGroup.add_argument('--show-pass', help='print visible pass information (default)', dest='includePass',
                               action='store_true', default=True)

    return parser

if __name__ == '__main__':
    parser = createParser()
    namespace = parser.parse_args()
    print(namespace)

    exit(0)
