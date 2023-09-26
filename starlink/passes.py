import pandas as pd
from sattrack.coordinates import GeoPosition
from sattrack.orbit import Satellite
from sattrack.spacetime import JulianDate
from sattrack.topocentric import getNextPass

from starlink.import_tle import fetchAllTLEs


def getNthPasses(df: pd.DataFrame, geo: GeoPosition, jd: JulianDate, visibleNumber=1) -> list:
    tleMap = fetchAllTLEs()
    tleList = [tleMap[satId] for satId in df['sat-id']]

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


def getBatchTimes(df: pd.DataFrame, geo: GeoPosition, jd: JulianDate, visibleNumber=1) \
        -> (bool, (JulianDate, JulianDate, JulianDate)):
    passList = getNthPasses(df, geo, jd, visibleNumber)
    if not any(passList):
        return False, (None, None, None)

    # Find the first time any sat becomes visible, and the first time any sat disappears.
    appearsIndex = -1
    appears, disappears = None, None
    for i, p in enumerate(passList):
        if p is None:
            continue
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
        if p is None:
            continue
        if p.visible:
            endTimes = [info for info in (p.setInfo, p.lastUnobscuredInfo, p.lastIlluminatedInfo) if
                        info is not None]
            disappears = min(endTimes, key=lambda o: o.time)
            break

    maxInfos = []
    for p in passList:
        if p is None:
            continue
        visibleInfos = [info for info in (p.maxInfo, p.lastIlluminatedInfo, p.lastUnobscuredInfo, p.setInfo)
                        if info is not None and info.visible]
        maxInfos.append(max(visibleInfos, key=lambda o: o.altitude))

    maxInfo = max(maxInfos, key=lambda o: o.altitude)

    return True, (appears, maxInfo, disappears)
