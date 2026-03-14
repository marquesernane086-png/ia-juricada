import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_KEY = process.env.REACT_APP_API_KEY;

const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  headers: API_KEY ? { "X-API-Key": API_KEY } : {},
});

export default api;
export const API_BASE = `${BACKEND_URL}/api`;
