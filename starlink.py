import sys
import tomllib
from math import degrees

import pandas as pd
from sattrack.orbit import Satellite
from sattrack.sgp4 import TwoLineElement
from sattrack.spacetime import now
from sattrack.util import EARTH_EQUITORIAL_RADIUS

from sortgroups import importStarlinkTLE


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

    return list((tle for tle in tleMasterList if int(tle.line1[9:14]) == intDes))


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
        'name': (tle.name for tle in tleList),
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


def splitIntoBatches(df: pd.DataFrame):
    """Return a list of DataFrames where each DataFrame pertains to a batch of satellites dependent on phase angle. All
    satellites of df should be in a single orbital plane."""

    groups = splitByPhase(df, [-1])
    refinedGroups = refineBatch(groups)

    return refinedGroups


def getLaunchData(group: str, launch: str, jd):
    """Compute the DataFrames for each batch in each orbital plane."""

    tleList = fetchTLEs(group, launch)
    df = generateDataFrame(tleList, jd, adjust=False)
    planes = splitIntoPlanes(df)
    refinedGroups = [splitIntoBatches(plane) for plane in planes]

    return refinedGroups


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


def main(group: str, launch: str):
    if not _checkInput(group):
        raise TypeError(f'group must be an int or a str digit')
    if not _checkInput(launch):
        raise TypeError(f'launch must be an int or a str digit')

    jd = now()
    data = getLaunchData(group, launch, jd)
    for i, plane in enumerate(data, 1):
        print('Plane ', i)
        for j, grp in enumerate(plane, 1):
            print('Group ', j)
            print(grp.round(2))

    return 0


if __name__ == '__main__':
    exit(main(sys.argv[1], sys.argv[2]))
