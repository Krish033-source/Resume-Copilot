import { api } from "./core.js";
export const S = { user: null, meta: { roles: [], statuses: [], ai_enabled: false }, latest: null };
export async function loadLatest() { S.latest = (await api("/resumes/latest")).resume; return S.latest; }
