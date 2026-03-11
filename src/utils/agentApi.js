// src/utils/agentApi.js

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

/* ---------------- AGENT QUERY ---------------- */
export async function queryAgent(question) {
  const payload = {
    question,
    top_k: 5,
    similarity_threshold: 0.35,
    temperature: 0.1,
  };

  const res = await fetch(`${API_BASE}/agent/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(txt || 'Agent error');
  }

  return res.json();
}

/* ---------------- SAVE CHAT ---------------- */
export async function saveChat(user_id, question, answer) {
  const params = new URLSearchParams({
    user_id: String(user_id),
    question,
    answer,
  });

  const res = await fetch(`${API_BASE}/chat/send?${params.toString()}`, {
    method: 'POST',
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => null);
    console.warn('saveChat failed', res.status, txt);
    return false;
  }
  return true;
}

/* ---------------- LOAD HISTORY ---------------- */
export async function loadHistoryForUser(user_id) {
  const res = await fetch(`${API_BASE}/chat/history/${user_id}`);
  if (!res.ok) return [];
  return res.json();
}
