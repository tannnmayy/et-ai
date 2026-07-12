import axios from 'axios';

// Create a shared axios instance for HTTP calls
export const apiClient = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});
