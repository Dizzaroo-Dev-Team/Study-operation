export const getDocumentClassificationMetadata = (document) => {
  if (!document) {
    return {
      zone: null,
      section: null,
      artifact: null,
      subArtifact: null,
    };
  }

  const fallbackBoolean = (value, defaultValue = true) =>
    typeof value === 'boolean' ? value : defaultValue;

  const extractZone = () => {
    const zone = document.zone || document.classification?.zone;
    if (zone) {
      return {
        id: zone._id || zone.id || zone,
        number: zone.zoneNumber ?? document.zoneNumber ?? 'N/A',
        name: zone.zoneName ?? document.zoneName ?? 'Unknown Zone',
        isActive: fallbackBoolean(zone.isActive),
      };
    }

    if (document.zoneNumber || document.zoneName) {
      return {
        id: null,
        number: document.zoneNumber ?? 'N/A',
        name: document.zoneName ?? 'Unknown Zone',
        isActive: true,
      };
    }

    return null;
  };

  const extractSection = () => {
    const section = document.section || document.classification?.section;
    if (section) {
      return {
        id: section._id || section.id || section,
        number: section.sectionNumber ?? document.sectionNumber ?? 'N/A',
        name: section.sectionName ?? document.sectionName ?? 'Unknown Section',
        isActive: fallbackBoolean(section.isActive),
      };
    }

    if (document.sectionNumber || document.sectionName) {
      return {
        id: null,
        number: document.sectionNumber ?? 'N/A',
        name: document.sectionName ?? 'Unknown Section',
        isActive: true,
      };
    }

    return null;
  };

  const extractArtifact = () => {
    const artifact = document.artifact || document.classification?.artifact;
    if (artifact) {
      return {
        id: artifact._id || artifact.id || artifact,
        number: artifact.artifactNumber ?? document.artifactNumber ?? document.tmfReference ?? 'N/A',
        name: artifact.artifactName ?? document.artifactName ?? 'Unknown Artifact',
        isActive: fallbackBoolean(artifact.isActive),
      };
    }

    if (document.artifactNumber || document.artifactName || document.tmfReference) {
      return {
        id: null,
        number: document.artifactNumber ?? document.tmfReference ?? 'N/A',
        name: document.artifactName ?? 'Unknown Artifact',
        isActive: true,
      };
    }

    return null;
  };

  const extractSubArtifact = () => {
    const subArtifact = document.subArtifact || document.classification?.subArtifact;
    if (subArtifact) {
      return {
        id: subArtifact._id || subArtifact.id || subArtifact,
        name: subArtifact.subArtifactName ?? document.subArtifactName ?? 'Unknown Sub-Artifact',
        isActive: fallbackBoolean(subArtifact.isActive),
      };
    }

    if (document.subArtifactName) {
      return {
        id: null,
        name: document.subArtifactName,
        isActive: true,
      };
    }

    return null;
  };

  return {
    zone: extractZone(),
    section: extractSection(),
    artifact: extractArtifact(),
    subArtifact: extractSubArtifact(),
  };
};

export const hasClassificationMetadata = (document) => {
  const metadata = getDocumentClassificationMetadata(document);
  return !!(metadata.zone || metadata.section || metadata.artifact || metadata.subArtifact);
};

