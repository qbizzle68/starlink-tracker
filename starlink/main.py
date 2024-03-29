from sattrack.coordinates import GeoPosition
from sattrack.exceptions import TLEException
from sattrack.spacetime import JulianDate

from starlink import fetchTLEsFromGroup, getBatchTimes
from starlink.frames import generateDataFrame, getLaunchData


def getDataFrame(group: str, launch: str, jd, adjust=True):
    """Compute DataFrame for the launch 'group-launch'. The adjust argument is passed through to generateDataFrame."""

    tleList = fetchTLEsFromGroup(group, launch)

    return generateDataFrame(tleList, jd, adjust=adjust)


def main(group: str, launch: str, geo: GeoPosition, jd: JulianDate, visibleNumber: int, includePass=False):
    try:
        data = getLaunchData(group, launch, jd)
    except TLEException as e:
        print('error:', e.message)
        return 1

    for i, plane in enumerate(data, 1):
        print('Plane', i, 'of', len(data))
        for j, grp in enumerate(plane, 1):
            print('\nGroup', j, 'of', len(plane))
            if includePass:
                result, (appears, maxInfo, disappears) = getBatchTimes(grp, geo, jd, visibleNumber)
                if result:
                    print('    appears:\t', appears.time.date(), '\talt:', round(appears.altitude, 2), '\taz:',
                          round(appears.azimuth, 2))
                    print('    max:\t', maxInfo.time.date(), '\talt:', round(maxInfo.altitude, 2), '\taz:',
                          round(maxInfo.azimuth, 2))
                    print('    disappears:\t', disappears.time.date(), '\talt:', round(disappears.altitude, 2), '\taz:',
                          round(disappears.azimuth, 2))
                else:
                    print('no visible passes')
            print(grp.round(2))

    return 0
