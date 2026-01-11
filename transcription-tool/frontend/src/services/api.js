import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
});

export const checkHealth = async () => {
  const response = await api.get('/health');
  return response.data;
};

export const transcribeAudio = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/transcribe', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const cleanupTranscript = async (transcript) => {
  const response = await api.post('/api/cleanup', { transcript });
  return response.data;
};

export const transcribeAndCleanup = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post('/api/transcribe-and-cleanup', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};
