// Ingestão (#33): 3x a premissa do PRD (100 mil Eventos/dia ≈ 1,16/s; 3x ≈ 3,5/s) sustentada e
// um pico de 200 Eventos/s por 10 min. O total aceito sai no resumo (`events_accepted`), e o
// verify.py confere no banco: zero perda e lag p95 < 60 s.
//
//   INGESTION_TOKEN=aid_ing_… INTEGRATION_ID=… RUN_ID=carga-1 API_URL=https://api… \
//     k6 run --summary-export=ingestion-summary.json tests/load/ingestion.js
import http from "k6/http";
import { Counter } from "k6/metrics";
import { API_URL, execution, json, required } from "./lib.js";

const TOKEN = required("INGESTION_TOKEN");
const INTEGRATION = required("INTEGRATION_ID");
const SUSTAINED = __ENV.SUSTAINED_DURATION || "30m";
const SPIKE = __ENV.SPIKE_DURATION || "10m";
const accepted = new Counter("events_accepted");
const rejected = new Counter("events_rejected");

export const options = {
  scenarios: {
    // 7 Eventos a cada 2 s = 3,5/s.
    sustained: {
      executor: "constant-arrival-rate",
      rate: 1,
      timeUnit: "2s",
      duration: SUSTAINED,
      preAllocatedVUs: 2,
      exec: "sustained",
    },
    // 200 Eventos/s: um lote de 200 por segundo (o limite é 500 por lote e 1 MB).
    spike: {
      executor: "constant-arrival-rate",
      rate: 1,
      timeUnit: "1s",
      duration: SPIKE,
      startTime: __ENV.SPIKE_START || "5m",
      preAllocatedVUs: 5,
      maxVUs: 20,
      exec: "spike",
    },
  },
  thresholds: {
    // 5xx acima de 0,1% reprova; 4xx (validação, 429) também conta como falha da rodada.
    http_req_failed: ["rate<0.001"],
    "http_req_duration{scenario:spike}": ["p(95)<1000"],
  },
};

function send(events) {
  const response = json(
    http.post(`${API_URL}/api/v1/ingestion/events`, JSON.stringify({ events }), {
      headers: { authorization: `Bearer ${TOKEN}`, "content-type": "application/json" },
      tags: { name: "ingestion" },
    }),
    "ingestão",
  );
  if (response.status === 202) {
    const body = response.json();
    accepted.add(body.accepted);
    rejected.add(body.rejected.length);
  }
}

function events(count) {
  const batch = [];
  while (batch.length < count) batch.push(...execution(INTEGRATION));
  return batch.slice(0, count);
}

export function sustained() {
  send(events(7));
}

export function spike() {
  send(events(200));
}
