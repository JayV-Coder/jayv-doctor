// API de leitura (#33): 50 Usuários simultâneos no Dashboard e nas listas. Meta: p95 < 500 ms e
// 5xx abaixo de 0,1%. O rate limit por Usuário (RATE_LIMIT_PER_MINUTE) não é o que se mede:
// em staging, suba o limite na rodada ou passe vários JWTs (USER_JWTS, separados por vírgula).
//
//   USER_JWTS=jwt1,jwt2 API_URL=https://api… k6 run tests/load/read.js
import http from "k6/http";
import { sleep } from "k6";
import { API_URL, json, required } from "./lib.js";

const JWTS = required("USER_JWTS").split(",");

export const options = {
  scenarios: {
    users: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 50),
      duration: __ENV.DURATION || "10m",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<500"],
    "checks{check:leitura: sem 5xx}": ["rate>0.999"],
  },
};

export default function () {
  const headers = {
    authorization: `Bearer ${JWTS[(__VU - 1) % JWTS.length]}`,
    "content-type": "application/json",
  };
  json(
    http.get(`${API_URL}/api/v1/dashboard`, { headers, tags: { name: "dashboard" } }),
    "leitura",
  );
  json(
    http.post(`${API_URL}/api/v1/incidents/search`, JSON.stringify({}), {
      headers,
      tags: { name: "incidentes" },
    }),
    "leitura",
  );
  json(
    http.post(`${API_URL}/api/v1/executions/search`, JSON.stringify({}), {
      headers,
      tags: { name: "execucoes" },
    }),
    "leitura",
  );
  // Quem lê a tela pensa antes do próximo clique.
  sleep(1 + Math.random() * 2);
}
