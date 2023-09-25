import sys
import tomllib
from math import degrees

import geocoder
import pandas as pd
from sattrack.coordinates import GeoPosition
from sattrack.exceptions import TLEException
from sattrack.orbit import Satellite
from sattrack.sgp4 import TwoLineElement
from sattrack.spacetime import now, JulianDate
from sattrack.topocentric import getNextPass
from sattrack.util import EARTH_EQUITORIAL_RADIUS

from sortgroups import importStarlinkTLE


def jdRound(self, n):
    digits = int(self.time().rsplit('.', 1)[1])
    value = self.value - (digits / 86400)
    return JulianDate.fromNumber(value, self.timezone)


JulianDate.__round__ = jdRound


def importConfig(filename):
    with open(filename, 'rb') as f:
        return tomllib.load(f)


def validateBatchName(group: str, launch: str, toml=None) -> bool:
    if toml is None:
        toml = importConfig('starlink.toml')

    token = f'{group}-{launch}'
    return token in toml['launches']


def fetchTLEs(group: str, launch: str, toml=None):
    if toml is None:
        toml = importConfig('starlink.toml')

    if not validateBatchName(group, launch, toml):
        raise ValueError(f'batch name ({group}-{launch}) not found in launch list')

    groupToken = f'group{group}'
    launchToken = f'L{launch}'
    intDes = toml[groupToken][launchToken]

    tleStringList = importStarlinkTLE('starlink.tle')
    tleMasterList = list((TwoLineElement(tle) for tle in tleStringList))

    rtn = list((tle for tle in tleMasterList if int(tle.line1[9:14]) == intDes))

    if not rtn:
        raise TLEException(f'no TLE data for batch {group}-{launch}')

    return rtn


def fetchTLEs2() -> dict[str, TwoLineElement]:
    tleStringList = importStarlinkTLE('starlink.tle')

    return {tle.split('\n', 1)[0].rstrip(): TwoLineElement(tle) for tle in tleStringList}


def _checkInput(value):
    if isinstance(value, str):
        return value.isdigit()
    return isinstance(value, int)


def computeApsides(sma: float, ecc: float) -> (int, int):
    rp = sma * (1 - ecc)
    ra = sma * (1 + ecc)

    return rp - EARTH_EQUITORIAL_RADIUS, ra - EARTH_EQUITORIAL_RADIUS


SCALE = 1.0


def findOutliersIQR(df: pd.Series) -> pd.Series:
    q1 = df.quantile(0.25)
    q3 = df.quantile(0.75)
    IQR = q3 - q1

    # We shouldn't worry about the lower outliers, as those satellites are in the same group.
    return df[df > (q3 + SCALE * IQR)]


def adjustPhase(df: pd.DataFrame) -> pd.DataFrame:
    # Index needs to be in ascending order for this to work.
    maxIndex = df['gap'].idxmax()
    # If maxIndex is zero then the rows are already in order.
    if maxIndex != 0:
        arr = df['phase'].tolist()
        # All rows from maxIndex to the end should precede the first rows, adjust by subtracting 360.
        for i in range(maxIndex, len(arr)):
            arr[i] -= 360

        df = df.assign(phase=arr)

    maxValue = df['phase'].max()
    df['phase'] = df['phase'].apply(lambda x: x - maxValue)
    df.sort_values('phase', ascending=False, inplace=True)

    return df.reset_index(drop=True)


def generateDataFrame(tleList, jd, adjust=True) -> pd.DataFrame:
    """Generate a pandas.DataFrame filled with satellite information derived from the tleList and jd parameters. If
    adjust is True, data is sorted by phase angle, the gap column is inserted and all phase angles are adjusted by
    the maximum value. The index is also reset when adjust is True."""

    elements = [Satellite(tle).getElements(jd) for tle in tleList]
    apsides = [computeApsides(el.sma, el.ecc) for el in elements]
    phases = [degrees(el.aop + el.trueAnomaly) % 360.0 for el in elements]
    data = {
        'sat-id': (tle.name.split('-', 1)[1] for tle in tleList),
        'inc': (degrees(el.inc) for el in elements),
        'raan': (degrees(el.raan) for el in elements),
        'phase': phases,
        'perigee': [round(rp, 1) for rp, _ in apsides],
        'apogee': [round(ra, 1) for _, ra in apsides],
    }

    df = pd.DataFrame(data)

    if adjust is True:
        # Sort rows by latArg and update index to be in order.
        df.sort_values('phase', inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Generate gap column in DataFrame.
        phases = df['phase'].tolist()
        gaps = [phases[i] - phases[i - 1] for i in range(len(phases))]
        gaps[0] += 360
        df['gap'] = gaps
        df = adjustPhase(df)

    return df


def applyGaps(df: pd.DataFrame) -> pd.DataFrame:
    """The df argument is sorted, its index reset, the gap column inserted, and the phase angles adjusted. This is
    similar to setting the adjust parameter to True in the generateDataFrame method.

    The following are equivalent:
        applyGaps(generateDataFrame(tleList, jd, False)
        generateDataFrame(tleList, jd, True)"""

    df2 = df.sort_values('phase').reset_index(drop=True)

    phases = df2['phase'].tolist()
    gaps = [phases[i] - phases[i - 1] for i in range(len(phases))]
    gaps[0] += 360
    df2['gap'] = gaps

    return adjustPhase(df2)


def findSameRaan(df: pd.Series, limit: float) -> pd.Series:
    """Finds all entries of a DataFrame with similar raan values. This is determined using the DataFrame.std() method.

    The df argument must be sorted by raan column, and limit is the value which the standard deviation is compared."""

    i = 1
    while (pd.isna(df.head(i)['raan'].std()) or df.head(i)['raan'].std() < limit) and i <= len(df):
        i += 1

    return df.iloc[:i-1]


def splitByRaan(df: pd.DataFrame) -> list[pd.DataFrame]:
    """Splits a DataFrame into a list of DataFrames that have similar raan values."""

    frame = df.sort_values('raan')
    planes = []
    while frame.empty is False:
        bunch = findSameRaan(frame, 1.25)
        planes.append(bunch)
        frame.drop(bunch.index, inplace=True)

    return planes


def splitByPhase(df: pd.DataFrame, ignore=None) -> list[pd.DataFrame]:
    """Splits a DataFrame of satellites in the same plane into batches based on their phase angles. The ignore argument
    should be an array of indices to ignore while computing interquartile ranges."""

    # As an implementation detail, the last row is always the largest gap, so we don't need to compute max.
    if ignore is None:
        ignore = []
    if -1 in ignore:
        ignore[ignore.index(-1)] = len(df) - 1
    outliers = findOutliersIQR(df.drop(ignore)['gap'])

    # If there are no outliers besides the first gap, there is only one group.
    if len(outliers) == 0:
        return [df.copy()]

    indices = list(outliers.index)
    if len(df) - 1 not in indices:
        indices.append(len(df))
    groups = []
    idx = 0
    for i in indices:
        group = df.iloc[idx:i+1].sort_values('phase', ascending=False)
        groups.append(group.reset_index(drop=True))
        idx = i+1

    return groups


def refineBatch(groups: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """Recursively refines a batch into further batches if there exists new outliers after the data is split."""

    rtn = [g for g in groups]
    count = -1
    while len(rtn) != count:
        # Set the number of batches before computing the next. When they no longer change after an iteration, stop
        # iterating.
        count = len(rtn)
        tmp = []
        for i, group in enumerate(rtn):
            if i == count - 1:
                ignore = [0, -1]
            else:
                ignore = []

            # Check if a batch is split again, creating a folded array in the process.
            tmp.append(splitByPhase(group, ignore=ignore))

        # Unfold the array into a single dimensional array of the groups, then repeat until finished.
        rtn = [element for subArr in tmp for element in subArr]

    return rtn


def splitIntoPlanes(df: pd.DataFrame) -> list[pd.DataFrame]:
    """Return a list of DataFrames where each DataFrame pertains to a specific orbital plane."""

    planes = [applyGaps(plane) for plane in splitByRaan(df)]

    return planes


def splitIntoBatches(df: pd.DataFrame) -> list[pd.DataFrame]:
    """Return a list of DataFrames where each DataFrame pertains to a batch of satellites dependent on phase angle. All
    satellites of df should be in a single orbital plane."""

    groups = splitByPhase(df, [-1])
    refinedGroups = refineBatch(groups)

    return refinedGroups


def getLaunchData(group: str, launch: str, jd) -> list[list[pd.DataFrame]]:
    """Compute the DataFrames for each batch in each orbital plane."""

    tleList = fetchTLEs(group, launch)
    df = generateDataFrame(tleList, jd, adjust=False)
    planes = splitIntoPlanes(df)
    refinedGroups = [splitIntoBatches(plane) for plane in planes]

    return refinedGroups


def getBatchTimes(df: pd.DataFrame, geo: GeoPosition, jd: JulianDate) -> (JulianDate, JulianDate):
    tleMap = fetchTLEs2()
    tleList = [tleMap[f'STARLINK-{satId}'] for satId in df['sat-id']]
    passList = [getNextPass(Satellite(tle), geo, jd) for tle in tleList]

    # Find the next series of passes where at least one pass is visible.
    anyVisible = any([p.visible for p in passList])
    while not anyVisible:
        passList = [getNextPass(Satellite(tle), geo, np) for tle, np in zip(tleList, passList)]
        anyVisible = any([p.visible for p in passList])

    # Find the first time any sat becomes visible, and the first time any sat disappears.
    appearsIndex = -1
    appears, disappears = None, None
    for i, p in enumerate(passList):
        if p.visible:
            startTimes = [info for info in (p.riseInfo, p.firstUnobscuredInfo, p.firstIlluminatedInfo) if
                          info is not None]
            appears = min(startTimes, key=lambda o: o.time)
            appearsIndex = i
            break

    # If passList is a single pass, we want to look at the same pass, so index should be -1, so it becomes 0 when we
    # add 1.
    if len(passList) == 1:
        appearsIndex = -1
    for p in reversed(passList[appearsIndex+1:]):
        if p.visible:
            endTimes = [info for info in (p.setInfo, p.lastUnobscuredInfo, p.lastIlluminatedInfo) if
                        info is not None]
            disappears = min(endTimes, key=lambda o: o.time)
            break

    maxInfos = []
    for p in passList:
        visibleInfos = [info for info in (p.maxInfo, p.lastIlluminatedInfo, p.lastUnobscuredInfo, p.setInfo)
                        if info is not None and info.visible]
        maxInfos.append(max(visibleInfos, key=lambda o: o.altitude))

    # maxInfo = max([p.maxInfo for p in passList], key=lambda o: o.altitude)
    maxInfo = max(maxInfos, key=lambda o: o.altitude)

    return appears, maxInfo, disappears


def addPassInfo(df: pd.DataFrame, geo, jd):
    tleMap = fetchTLEs2()
    tleList = [tleMap[f'STARLINK-{satId}'] for satId in df['sat-id']]
    passList = [getNextPass(Satellite(tle), geo, jd) for tle in tleList]

    # df['rises'] = [p.riseInfo.time.time() for p in passList]
    # df['max-alt'] = [round(p.maxInfo.altitude, 2) for p in passList]
    # df['sets'] = [p.setInfo.time.time() for p in passList]

    df['atime'] = [p.riseInfo.time.time().rsplit('.', 1)[0] for p in passList]
    df['aalt'] = [p.riseInfo.altitude for p in passList]
    df['aaz'] = [p.riseInfo.azimuth for p in passList]
    df['mtime'] = [p.maxInfo.time.time().rsplit('.', 1)[0] for p in passList]
    df['malt'] = [p.maxInfo.altitude for p in passList]
    df['maz'] = [p.maxInfo.azimuth for p in passList]
    df['dtime'] = [p.setInfo.time.time().rsplit('.', 1)[0] for p in passList]
    df['dalt'] = [p.setInfo.altitude for p in passList]
    df['daz'] = [p.setInfo.azimuth for p in passList]


def getPassInfo(df: pd.DataFrame, geo: GeoPosition, jd: JulianDate, visibleNumber=1):
    tleMap = fetchTLEs2()
    tleList = [tleMap[f'STARLINK-{satId}'] for satId in df['sat-id']]

    passList = []
    for tle in tleList:
        sat = Satellite(tle)
        currentNumber = 0

        np = getNextPass(sat, geo, jd)
        if np.visible:
            currentNumber = 1

        while currentNumber < visibleNumber:
            # Some satellites wont produce visible passes, so stop after 7 days.
            if np.riseInfo.time - jd > 7:
                np = None
                break

            np = getNextPass(sat, geo, np)

            if np.visible:
                currentNumber += 1

        passList.append(np)

    return passList


# Functions for ease of use if importing module.

def getDataFrame(group: str, launch: str, jd, adjust=True):
    """Compute DataFrame for the launch 'group-launch'. The adjust argument is passed through to generateDataFrame."""

    tleList = fetchTLEs(group, launch)

    return generateDataFrame(tleList, jd, adjust=adjust)


# don't think we need this, will delete in future
def getSplitFrames(group: str, launch: str, jd):
    tleList = fetchTLEs(group, launch)
    df = generateDataFrame(tleList, jd, adjust=True)
    groups = splitByPhase(df, [-1])
    refinedGroups = refineBatch(groups)
    return refinedGroups


def main(group: str, launch: str, geo: GeoPosition, jd: JulianDate, includePass=False):
    if not _checkInput(group):
        raise TypeError(f'group must be an int or a str digit')
    if not _checkInput(launch):
        raise TypeError(f'launch must be an int or a str digit')

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
                appears, maxInfo, disappears = getBatchTimes(grp, geo, jd)
                print('    appears:\t', appears.time.date(), '\talt:', round(appears.altitude, 2), '\taz:',
                      round(appears.azimuth, 2))
                print('    max:\t', maxInfo.time.date(), '\talt:', round(maxInfo.altitude, 2), '\taz:',
                      round(maxInfo.azimuth, 2))
                print('    disappears:\t', disappears.time.date(), '\talt:', round(disappears.altitude, 2), '\taz:',
                      round(disappears.azimuth, 2))
            print(grp.round(2))
            # if includePass:
            #     # addPassInfo(grp, geo, jd)
            #     passes = getPassInfo(grp, geo, jd, 1)
            #     for (_, row), np in zip(grp.round(2).iterrows(), passes):
            #         print(row.to_frame().T.to_string(header=False))
            #         riseString = f'\tappears: {np.riseInfo.time.date()} - alt: {round(np.riseInfo.altitude)} - az: ' \
            #                      f'{round(np.riseInfo.azimuth)}'
            #         maxString = f'\tappears: {np.maxInfo.time.date()} - alt: {round(np.maxInfo.altitude)} - az: ' \
            #                     f'{round(np.maxInfo.azimuth)}'
            #         setString = f'\tappears: {np.setInfo.time.date()} - alt: {round(np.setInfo.altitude)} - az: ' \
            #                     f'{round(np.setInfo.azimuth)}'
            #         print(riseString, maxString, setString)
            # else:
            #     print(grp.round(2))

    return 0


if __name__ == '__main__':
    groupArg = sys.argv[1]
    launchArg = sys.argv[2]
    gc = geocoder.ip('me')
    geoArg = GeoPosition(gc.latlng[0], gc.latlng[1])
    jdArg = now()
    exit(main(groupArg, launchArg, geoArg, jdArg, True))
