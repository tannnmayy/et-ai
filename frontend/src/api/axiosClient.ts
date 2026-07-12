import axios from 'axios';

// Create a custom Axios instance configured for FastAPI via Vite proxy /api
export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});
