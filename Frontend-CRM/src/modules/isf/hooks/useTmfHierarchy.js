import { useQuery } from '@tanstack/react-query';
import { fetchTmfHierarchy } from '../services/tmfHierarchy.service';

const TMF_HIERARCHY_QUERY_KEY = ['tmfHierarchy'];

/**
 * Load TMF reference hierarchy from the backend (zones → sections → artifacts → subartifacts).
 */
export function useTmfHierarchy() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: TMF_HIERARCHY_QUERY_KEY,
    queryFn: fetchTmfHierarchy,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  });

  return {
    hierarchyData: data?.hierarchyData ?? [],
    artifactSubartifacts: data?.artifactSubartifacts ?? {},
    isLoading,
    isError,
    error,
    refetch,
  };
}

export default useTmfHierarchy;
