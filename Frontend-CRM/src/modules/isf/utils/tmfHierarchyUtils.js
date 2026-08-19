/**
 * Resolve artifact number/name from a hint string using the dynamic TMF flat map.
 */
export function resolveArtifactDetails(artifactHint, artifactSubartifacts = {}) {
  if (!artifactHint) {
    return { number: '', name: '' };
  }

  const trimmedHint = artifactHint.trim();
  const lowerHint = trimmedHint.toLowerCase();

  if (artifactSubartifacts[trimmedHint]) {
    return {
      number: trimmedHint,
      name: artifactSubartifacts[trimmedHint].name || trimmedHint,
    };
  }

  const numberMatch = trimmedHint.match(/^\d{2}\.\d{2}(?:\.\d{2})?/);
  if (numberMatch) {
    const candidate = numberMatch[0];
    if (artifactSubartifacts[candidate]) {
      return {
        number: candidate,
        name: artifactSubartifacts[candidate].name || trimmedHint,
      };
    }
  }

  const exactNameEntry = Object.entries(artifactSubartifacts).find(
    ([, data]) => data.name === trimmedHint
  );
  if (exactNameEntry) {
    return { number: exactNameEntry[0], name: exactNameEntry[1].name };
  }

  const partialNameEntry = Object.entries(artifactSubartifacts).find(([, data]) => {
    const lowerName = data.name?.toLowerCase();
    return lowerName && (lowerName.includes(lowerHint) || lowerHint.includes(lowerName));
  });
  if (partialNameEntry) {
    return { number: partialNameEntry[0], name: partialNameEntry[1].name };
  }

  const subArtifactEntry = Object.entries(artifactSubartifacts).find(([, data]) =>
    data.subartifacts?.some((sub) => {
      const lowerSub = sub.toLowerCase();
      return lowerSub.includes(lowerHint) || lowerHint.includes(lowerSub);
    })
  );
  if (subArtifactEntry) {
    return { number: subArtifactEntry[0], name: subArtifactEntry[1].name };
  }

  return { number: '', name: trimmedHint };
}

/**
 * Normalize TMF number strings for consistent matching (e.g. 1.01 -> 01.01).
 */
export function normalizeTMF(val) {
  if (val === null || val === undefined) return '';
  const s = String(val).trim();
  if (!s) return '';
  const parts = s.split('.');
  if (parts.length > 0) {
    const p = parseInt(parts[0], 10);
    if (!isNaN(p)) parts[0] = p.toString().padStart(2, '0');
  }
  if (parts.length > 1) {
    const p = parseInt(parts[1], 10);
    parts[1] = isNaN(p) ? parts[1] : p.toString().padStart(2, '0');
  }
  if (parts.length > 2) {
    const p = parseInt(parts[2], 10);
    parts[2] = isNaN(p) ? parts[2] : p.toString().padStart(2, '0');
  }
  return parts.join('.');
}

export function normalizeSectionNumber(value) {
  if (value === undefined || value === null) return '';
  const str = value.toString();
  const parts = str.split('.');
  if (parts.length < 2) return str;
  const zone = parts[0].padStart(2, '0');
  const section = parts[1].padStart(2, '0');
  return `${zone}.${section}`;
}

export function getZonesFromHierarchy(hierarchyData = []) {
  return hierarchyData.map((zone) => ({
    id: zone.Zone?.Number,
    number: zone.Zone?.Number,
    name: zone.Zone?.Name,
  }));
}
