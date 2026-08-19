import axios from 'axios';

// VITE_API_BASE includes /api (e.g. http://localhost:8000/api in dev, https://api.yourcrm.com/api in prod)
const _raw = import.meta.env.VITE_API_BASE || '';
const _isLocal = _raw.includes('localhost') || _raw.includes('127.0.0.1');
const API_URL = (!_isLocal && _raw.startsWith('http://')) ? _raw.replace('http://', 'https://') : _raw;

// Dummy data for development/demo
const dummyZones = [
  { id: 1, name: "Core Documents", code: "CORE", description: "Essential TMF documents" },
  { id: 2, name: "Country Documents", code: "COUNTRY", description: "Country-specific TMF documents" },
  { id: 3, name: "Site Documents", code: "SITE", description: "Site-level TMF documents" },
  { id: 4, name: "Investigator Documents", code: "INVESTIGATOR", description: "Investigator-specific TMF documents" }
];

const dummyDocuments = [
  {
    id: 1,
    name: "Protocol v1.0",
    status: "APPROVED",
    version: "1.0",
    study: "STUDY-2024-001",
    country: "US",
    site: "Site 101",
    createdBy: "Dr. Alice Smith",
    zone: "Core Documents",
    section: "Protocol",
    artifact: "Protocol",
    subArtifact: "Initial",
    createdAt: "4/15/2024",
    expirationDate: "4/15/2026"
  },
  {
    id: 2,
    name: "Informed Consent Form",
    status: "IN_REVIEW",
    version: "2.1",
    study: "STUDY-2024-001",
    country: "US",
    site: "Site 101",
    createdBy: "Jane Doe",
    zone: "Core Documents",
    section: "Consent",
    artifact: "ICF",
    subArtifact: "Adult",
    createdAt: "4/20/2024",
    expirationDate: "4/20/2026"
  },
  {
    id: 3,
    name: "Site Initiation Checklist",
    status: "DRAFT",
    version: "0.9",
    study: "STUDY-2024-002",
    country: "UK",
    site: "Site 202",
    createdBy: "John Lee",
    zone: "Site Documents",
    section: "Initiation",
    artifact: "Checklist",
    subArtifact: "Site",
    createdAt: "5/1/2024",
    expirationDate: "5/1/2025"
  },
  {
    id: 4,
    name: "Investigator CV",
    status: "APPROVED",
    version: "1.2",
    study: "STUDY-2024-003",
    country: "DE",
    site: "Site 303",
    createdBy: "Dr. Eva Müller",
    zone: "Investigator Documents",
    section: "CV",
    artifact: "Curriculum Vitae",
    subArtifact: "Investigator",
    createdAt: "3/10/2024",
    expirationDate: "3/10/2027"
  },
  {
    id: 5,
    name: "Financial Disclosure Form",
    status: "IN_REVIEW",
    version: "1.0",
    study: "STUDY-2024-002",
    country: "UK",
    site: "Site 202",
    createdBy: "Jane Doe",
    zone: "Site Documents",
    section: "Finance",
    artifact: "Disclosure",
    subArtifact: "Financial",
    createdAt: "5/2/2024",
    expirationDate: "5/2/2025"
  },
  {
    id: 6,
    name: "Ethics Committee Approval",
    status: "APPROVED",
    version: "1.0",
    study: "STUDY-2024-001",
    country: "US",
    site: "Site 101",
    createdBy: "Dr. Alice Smith",
    zone: "Core Documents",
    section: "Ethics",
    artifact: "Approval",
    subArtifact: "Committee",
    createdAt: "4/25/2024",
    expirationDate: "4/25/2026"
  },
  {
    id: 7,
    name: "Monitoring Visit Report",
    status: "DRAFT",
    version: "0.8",
    study: "STUDY-2024-003",
    country: "DE",
    site: "Site 303",
    createdBy: "John Lee",
    zone: "Site Documents",
    section: "Monitoring",
    artifact: "Report",
    subArtifact: "Visit",
    createdAt: "5/5/2024",
    expirationDate: "5/5/2025"
  },
  {
    id: 8,
    name: "Delegation Log",
    status: "IN_REVIEW",
    version: "1.0",
    study: "STUDY-2024-001",
    country: "US",
    site: "Site 101",
    createdBy: "Jane Doe",
    zone: "Core Documents",
    section: "Delegation",
    artifact: "Log",
    subArtifact: "Staff",
    createdAt: "4/30/2024",
    expirationDate: "4/30/2026"
  },
  {
    id: 9,
    name: "Insurance Certificate",
    status: "APPROVED",
    version: "1.0",
    study: "STUDY-2024-002",
    country: "UK",
    site: "Site 202",
    createdBy: "Dr. Eva Müller",
    zone: "Country Documents",
    section: "Insurance",
    artifact: "Certificate",
    subArtifact: "Site",
    createdAt: "5/3/2024",
    expirationDate: "5/3/2025"
  },
  {
    id: 10,
    name: "Subject Enrollment Log",
    status: "DRAFT",
    version: "0.7",
    study: "STUDY-2024-003",
    country: "DE",
    site: "Site 303",
    createdBy: "John Lee",
    zone: "Site Documents",
    section: "Enrollment",
    artifact: "Log",
    subArtifact: "Subject",
    createdAt: "5/6/2024",
    expirationDate: "5/6/2025"
  }
];

// Create an Axios instance with base configuration
const api = axios.create({
  baseURL: `${API_URL}/tmf`,
  headers: {
    'Content-Type': 'application/json',
  },
});

const tmfService = {
  zones: {
    getAll: async () => {
      // Return dummy zones for development/demo
      return dummyZones;
      // Uncomment below for real API
      // try {
      //   const response = await api.get('/zones');
      //   return response.data;
      // } catch (error) {
      //   console.error('Error fetching zones:', error);
      //   throw error;
      // }
    },

    getById: async (id) => {
      try {
        const response = await api.get(`/zones/${id}`);
        return response.data;
      } catch (error) {
        console.error('Error fetching zone:', error);
        throw error;
      }
    },

    create: async (zoneData) => {
      try {
        const response = await api.post('/zones', zoneData);
        return response.data;
      } catch (error) {
        console.error('Error creating zone:', error);
        throw error;
      }
    },

    update: async (zoneId, zoneData) => {
      try {
        const response = await api.put(`/zones/${zoneId}`, zoneData);
        return response.data;
      } catch (error) {
        console.error('Error updating zone:', error);
        throw error;
      }
    },

    delete: async (zoneId) => {
      try {
        const response = await api.delete(`/zones/${zoneId}`);
        return response.data;
      } catch (error) {
        console.error('Error deleting zone:', error);
        throw error;
      }
    }
  },

  sections: {
    getAllByZone: async (zoneId) => {
      try {
        const response = await api.get(`/zones/${zoneId}/sections`);
        return response.data;
      } catch (error) {
        console.error('Error fetching sections:', error);
        throw error;
      }
    },

    getById: async (id) => {
      try {
        const response = await api.get(`/sections/${id}`);
        return response.data;
      } catch (error) {
        console.error('Error fetching section:', error);
        throw error;
      }
    },

    create: async (zoneId, sectionData) => {
      try {
        const response = await api.post(`/zones/${zoneId}/sections`, sectionData);
        return response.data;
      } catch (error) {
        console.error('Error creating section:', error);
        throw error;
      }
    }
  },

  artifacts: {
    getAllBySection: async (sectionId) => {
      try {
        const response = await api.get(`/sections/${sectionId}/artifacts`);
        return response.data;
      } catch (error) {
        console.error('Error fetching artifacts:', error);
        throw error;
      }
    },

    getById: async (id) => {
      try {
        const response = await api.get(`/artifacts/${id}`);
        return response.data;
      } catch (error) {
        console.error('Error fetching artifact:', error);
        throw error;
      }
    },

    create: async (sectionId, artifactData) => {
      try {
        const response = await api.post(`/sections/${sectionId}/artifacts`, artifactData);
        return response.data;
      } catch (error) {
        console.error('Error creating artifact:', error);
        throw error;
      }
    }
  },

  subArtifacts: {
    getAllByArtifact: async (artifactId) => {
      try {
        const response = await api.get(`/artifacts/${artifactId}/subartifacts`);
        return response.data;
      } catch (error) {
        console.error('Error fetching subArtifacts:', error);
        throw error;
      }
    },

    getById: async (id) => {
      try {
        const response = await api.get(`/subartifacts/${id}`);
        return response.data;
      } catch (error) {
        console.error('Error fetching subArtifact:', error);
        throw error;
      }
    },

    create: async (artifactId, subArtifactData) => {
      try {
        const response = await api.post(`/artifacts/${artifactId}/subartifacts`, subArtifactData);
        return response.data;
      } catch (error) {
        console.error('Error creating subArtifact:', error);
        throw error;
      }
    }
  },

  documents: {
    getAll: async (zoneId) => {
      // Return dummy documents for development/demo
      return dummyDocuments;
      // Uncomment below for real API
      // try {
      //   const response = await api.get(`/zones/${zoneId}/documents`);
      //   return response.data;
      // } catch (error) {
      //   console.error('Error fetching documents:', error);
      //   throw error;
      // }
    },

    upload: async (zoneId, file, metadata) => {
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('metadata', JSON.stringify(metadata));

        const response = await api.post(`/zones/${zoneId}/documents`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        });
        return response.data;
      } catch (error) {
        console.error('Error uploading document:', error);
        throw error;
      }
    },

    download: async (documentId) => {
      try {
        const response = await api.get(`/documents/${documentId}/download`, {
          responseType: 'blob',
        });
        return response.data;
      } catch (error) {
        console.error('Error downloading document:', error);
        throw error;
      }
    },

    update: async (documentId, metadata) => {
      try {
        const response = await api.put(`/documents/${documentId}`, metadata);
        return response.data;
      } catch (error) {
        console.error('Error updating document:', error);
        throw error;
      }
    },

    delete: async (documentId) => {
      try {
        const response = await api.delete(`/documents/${documentId}`);
        return response.data;
      } catch (error) {
        console.error('Error deleting document:', error);
        throw error;
      }
    },

    search: async (query, filters) => {
      try {
        const response = await api.get('/documents/search', {
          params: {
            query,
            ...filters,
          },
        });
        return response.data;
      } catch (error) {
        console.error('Error searching documents:', error);
        throw error;
      }
    }
  },

  /**
   * TMF routing — publish the document's full payload to the Data Platform
   * (Kafka topic `platform.documents`). Replaces the old email/Mailgun path.
   *
   * Backend endpoint: POST /tmf/send
   */
  sendToTmf: async ({ documentId, studyId, studyNumber }) => {
    try {
      const response = await api.post('/send', {
        documentId,
        studyId,
        studyNumber,
      });
      return response.data;
    } catch (error) {
      console.error('Error routing document to TMF:', error);
      throw error;
    }
  },
};

export default tmfService; 