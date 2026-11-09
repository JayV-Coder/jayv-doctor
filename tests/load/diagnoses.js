// 100 Diagnósticos em 1 h (#33), distribuídos entre os Incidentes informados. O tempo de cada um
// (fila até publicação) e o status final saem do banco pelo verify.py.
//
//   USER_JWT=… INCIDENT_IDS=id1,id2 MODE=hybrid API_URL=https://api… k6 run tests/load/diagnoses.js
import http from "k6/http";
import { API_URL, json, required } from "./lib.js";

const JWT = required("USER_JWT");
const INCIDENTS = required("INCIDENT_IDS").split(",");
const MODE = __ENV.MODE || "hybrid";

export const options = {
  scenarios: {
    diagnoses: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.DIAGNOSES || 100),
      timeUnit: __ENV.WINDOW || "1h",
      duration: __ENV.WINDOW || "1h",
      preAllocatedVUs: 2,
    },
  },
  thresholds: { http_req_failed: ["rate<0.001"] },
};

export default function () {
  const incident = INCIDENTS[Math.floor(Math.random() * INCIDENTS.length)];
  const response = http.post(
    `${API_URL}/api/v1/incidents/${incident}/diagnoses`,
    JSON.stringify({ mode: MODE, include_knowledge_base: true }),
    {
      headers: { authorization: `Bearer ${JWT}`, "content-type": "application/json" },
      tags: { name: "diagnostico" },
    },
  );
  json(response, "diagnóstico");
}
