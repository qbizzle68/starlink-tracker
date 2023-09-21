import sys
import tomllib
from math import degrees
from pprint import pp

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

    # We shouldn't worry about the small outliers, as those satellites are in the same group.
    return df[df > (q3 + SCALE * IQR)]


def adjustLatitudeArguments(df):
    rawArgs = df['latArg'].tolist()
    diffs = [rawArgs[i] - rawArgs[i - 1] for i in range(len(rawArgs))]
    maxValue = max(diffs)
    maxIndex = diffs.index(maxValue)

    if maxValue < 180:
        adjustValue = rawArgs[maxIndex]
        rtn = [a - adjustValue for a in rawArgs]
    else:
        adjustValue = 360 - maxValue

        adjustedArgs = []
        for i in range(len(rawArgs)):
            if i < maxIndex:
                adjustedArgs.append(rawArgs[i] + adjustValue)
            else:
                adjustedArgs.append(rawArgs[i] - 360 + adjustValue)

        maxArgs = max(adjustedArgs)
        rtn = [a - maxArgs for a in adjustedArgs]

    return rtn


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
    elements = [Satellite(tle).getElements(jd) for tle in tleList]
    apsides = [computeApsides(el.sma, el.ecc) for el in elements]
    phases = [degrees(el.aop + el.trueAnomaly) % 360.0 for el in elements]
    data = {
        'name': (tle.name for tle in tleList),
        'inclination': (degrees(el.inc) for el in elements),
        'raan': (degrees(el.raan) for el in elements),
        'phase': phases,
        'perigee': [round(rp, 1) for rp, _ in apsides],
        'apogee': [round(ra, 1) for _, ra in apsides],
    }

    # Sort rows by latArg and update index to be in order.
    df = pd.DataFrame(data).sort_values('phase')
    df.index = range(len(df))

    # Generate gap column in DataFrame.
    phases = df['phase'].tolist()
    gaps = [phases[i] - phases[i - 1] for i in range(len(phases))]
    gaps[0] += 360
    df['gap'] = gaps

    if adjust is True:
        df = adjustPhase(df)
        # maxValue = df['phase'].max()
        # df['phase'] = df['phase'].apply(lambda x: x - maxValue)
        # df.index = range(len(df))

    return df


def splitBatch(df: pd.DataFrame, ignore=None) -> list[pd.DataFrame]:
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
        g = df.iloc[idx:i+1].sort_values('phase', ascending=False)
        groups.append(g.reset_index(drop=True))
        idx = i+1

    return groups


def refineBatch(groups: list[pd.DataFrame]) -> list[pd.DataFrame]:
    rtn = [g for g in groups]
    count = -1
    while len(rtn) != count:
        count = len(rtn)
        tmp = []
        for i, group in enumerate(rtn):
            if i == 0:
                ignore = []
            elif i == count - 1:
                ignore = [0, -1]
            else:
                ignore = []

            tmp.append(splitBatch(group, ignore=ignore))

        rtn = [element for subArr in tmp for element in subArr]

    return rtn


def getDataFrame(group: str, launch: str, jd, adjust=True):
    tleList = fetchTLEs(group, launch)
    return generateDataFrame(tleList, jd, adjust=adjust)


def getSplitFrames(group: str, launch: str, jd):
    tleList = fetchTLEs(group, launch)
    df = generateDataFrame(tleList, jd, adjust=True)
    groups = splitBatch(df, [-1])
    refinedGroups = refineBatch(groups)
    return refinedGroups


def main(group: str, launch: str):
    if not _checkInput(group):
        raise TypeError(f'group must be an int or a str digit')
    if not _checkInput(launch):
        raise TypeError(f'launch must be an int or a str digit')

    jd = now()
    frames = getSplitFrames(group, launch, jd)
    pp(frames)

    return 0


if __name__ == '__main__':
    exit(main(sys.argv[1], sys.argv[2]))
