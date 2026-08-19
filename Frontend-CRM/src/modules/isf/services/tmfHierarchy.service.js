import api from './api';

/**
 * Fetch the full TMF reference hierarchy from the backend.
 * @returns {{ hierarchyData: Array, artifactSubartifacts: Object }}
 */
export async function fetchTmfHierarchy() {
  const response = await api.get('/isf/hierarchy');
  return response.data;
}

export default { fetchTmfHierarchy };
