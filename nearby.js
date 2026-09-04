/* nearby.js
 * Pure functions for Haversine distance, walking time, opening hours,
 * scoring, sorting, and diacritic-insensitive matching.
 * No DOM, no Leaflet dependency.
 */

'use strict';

(function (exports) {
  const R_KM = 6371.0088; // IUGG mean Earth radius
  const WALK_KMH = 4.5;   // Normal city walking speed in km/h

  function haversineKm(lat1, lon1, lat2, lon2) {
    if (
      lat1 == null || lon1 == null ||
      lat2 == null || lon2 == null ||
      isNaN(lat1) || isNaN(lon1) ||
      isNaN(lat2) || isNaN(lon2)
    ) {
      return Infinity;
    }
    const toRad = (deg) => (deg * Math.PI) / 180;
    const phi1 = toRad(lat1);
    const phi2 = toRad(lat2);
    const dPhi = toRad(lat2 - lat1);
    const dLambda = toRad(lon2 - lon1);

    const a =
      Math.sin(dPhi / 2) ** 2 +
      Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
    return R_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function walkTimeMinutes(km) {
    if (!isFinite(km) || km < 0) return 0;
    return Math.round((km / WALK_KMH) * 60);
  }

  function normalizeText(text) {
    return String(text || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim();
  }

  function matchesText(text, query) {
    if (!query) return true;
    return normalizeText(text).includes(normalizeText(query));
  }

  function getLocalTimeInTz(date, timeZone) {
    try {
      const options = {
        timeZone: timeZone || 'UTC',
        hour12: false,
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
      };
      const formatter = new Intl.DateTimeFormat('en-US', options);
      const parts = formatter.formatToParts(date || new Date());
      let weekdayStr = '';
      let hourStr = '00';
      let minuteStr = '00';

      for (const p of parts) {
        if (p.type === 'weekday') weekdayStr = p.value;
        if (p.type === 'hour') hourStr = p.value;
        if (p.type === 'minute') minuteStr = p.value;
      }

      // Convert en-US weekday to 0..6 (0=Mon..6=Sun)
      const dayMap = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
      const dayIndex = dayMap[weekdayStr] ?? 0;
      const timeStr = `${hourStr}:${minuteStr}`;

      return { dayIndex, timeStr, hour: parseInt(hourStr, 10) };
    } catch (e) {
      return { dayIndex: 0, timeStr: '12:00', hour: 12 };
    }
  }

  function checkOpenStatus(hoursParsed, date, timeZone) {
    if (!hoursParsed || !hoursParsed.ok || !Array.isArray(hoursParsed.weekly)) {
      return { status: 'unknown', label: 'Hours unconfirmed' };
    }

    const { dayIndex, timeStr } = getLocalTimeInTz(date, timeZone);
    const daySlots = hoursParsed.weekly[dayIndex];

    if (!Array.isArray(daySlots) || daySlots.length === 0) {
      return { status: 'closed', label: 'Closed today' };
    }

    for (const slot of daySlots) {
      if (slot.open && slot.close) {
        if (timeStr >= slot.open && timeStr <= slot.close) {
          return { status: 'open', label: `Open now until ${slot.close}` };
        }
      }
    }

    return { status: 'closed', label: 'Closed now' };
  }

  function calculateScore(place, anchor, date, timeZone) {
    const km = haversineKm(anchor.lat, anchor.lon, place.lat, place.lon);
    if (!isFinite(km)) return -1;

    // 1. Distance score (1.5 km half-weight)
    const distanceScore = 1 / (1 + km / 1.5);

    // 2. Priority score
    const prio = place.priority;
    const priorityScore = prio === 'Must' ? 1.0 : prio === 'Nice' ? 0.6 : 0.4;

    // 3. Open score
    const openInfo = checkOpenStatus(place.hoursParsed, date, timeZone);
    const openScore =
      openInfo.status === 'open' ? 1.0 : openInfo.status === 'unknown' ? 0.7 : 0.0;

    // 4. Time bucket score
    const { hour } = getLocalTimeInTz(date, timeZone);
    const partOfDay = hour >= 6 && hour < 18 ? 'day' : 'night';
    const tb = place.timeBucket || 'any';
    const timeScore = tb === 'any' || tb === partOfDay || tb === 'day or night' ? 1.0 : 0.5;

    const score =
      0.45 * distanceScore +
      0.30 * priorityScore +
      0.15 * openScore +
      0.10 * timeScore;

    return {
      score,
      km,
      walkMin: walkTimeMinutes(km),
      openStatus: openInfo.status,
      openLabel: openInfo.label,
    };
  }

  function rankPlaces(places, anchor, options) {
    options = options || {};
    const radiusKm = options.radiusKm || 1.5;
    const openNowOnly = options.openNowOnly || false;
    const typeFilter = options.typeFilter || 'all';
    const sortMode = options.sortMode || 'best'; // 'best' or 'nearest'
    const date = options.date || new Date();
    const timeZone = options.timeZone || 'UTC';

    if (!anchor || anchor.lat == null || anchor.lon == null) {
      return { results: [], nearestOutside: null };
    }

    const scoredList = [];
    let nearestOutside = null;
    let minOutsideKm = Infinity;

    for (const p of places) {
      if (typeFilter !== 'all' && p.type !== typeFilter) continue;

      const info = calculateScore(p, anchor, date, timeZone);
      if (info.km === -1) continue;

      if (openNowOnly && info.openStatus === 'closed') continue;

      const item = Object.assign({}, p, {
        distanceKm: info.km,
        walkMinutes: info.walkMin,
        score: info.score,
        openStatus: info.openStatus,
        openLabel: info.openLabel,
      });

      if (info.km <= radiusKm) {
        scoredList.push(item);
      } else {
        if (info.km < minOutsideKm) {
          minOutsideKm = info.km;
          nearestOutside = item;
        }
      }
    }

    scoredList.sort((a, b) => {
      if (sortMode === 'nearest') {
        return a.distanceKm - b.distanceKm || a.name.localeCompare(b.name);
      }
      // 'best' match score
      return b.score - a.score || a.distanceKm - b.distanceKm || a.name.localeCompare(b.name);
    });

    return {
      results: scoredList,
      nearestOutside: nearestOutside,
    };
  }

  exports.haversineKm = haversineKm;
  exports.walkTimeMinutes = walkTimeMinutes;
  exports.normalizeText = normalizeText;
  exports.matchesText = matchesText;
  exports.checkOpenStatus = checkOpenStatus;
  exports.calculateScore = calculateScore;
  exports.rankPlaces = rankPlaces;
})(typeof exports !== 'undefined' ? exports : (window.Nearby = {}));
