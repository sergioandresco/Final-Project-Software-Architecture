// Carga realista para el análisis de overhead.
//   VUS (50-100 usuarios concurrentes) y DURATION (5m) se controlan por variable de entorno.
//   Con RATE=<iteraciones/s> se usa una tasa de llegada fija (análisis por componente):
//   la carga es idéntica entre variantes y no satura el servicio.
// Mezcla de tráfico: 70% crear orden (service-a -> service-b -> DB), 20% catálogo, 10% consulta de orden.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const RUN_LABEL = __ENV.RUN_LABEL || 'manual';

const RATE = Number(__ENV.RATE || 0);

const createOrderLatency = new Trend('create_order_duration', true);

const scenario = RATE
  ? {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: Number(__ENV.VUS || 100),
      gracefulStop: '10s',
    }
  : {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 100),
      duration: __ENV.DURATION || '5m',
      gracefulStop: '10s',
    };

export const options = {
  scenarios: { steady_load: scenario },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(99)<2000'],
  },
};

const headers = { 'Content-Type': 'application/json' };

export default function () {
  const roll = Math.random();

  if (roll < 0.7) {
    const payload = JSON.stringify({
      customer_id: `customer-${__VU}`,
      product_id: 1 + Math.floor(Math.random() * 50),
      quantity: 1 + Math.floor(Math.random() * 20),
    });
    const res = http.post(`${BASE_URL}/api/orders`, payload, { headers, tags: { name: 'POST /api/orders' } });
    createOrderLatency.add(res.timings.duration);
    check(res, { 'orden creada (201)': (r) => r.status === 201 });
    if (res.status === 201 && Math.random() < 0.15) {
      const id = res.json('id');
      const got = http.get(`${BASE_URL}/api/orders/${id}`, { tags: { name: 'GET /api/orders/{id}' } });
      check(got, { 'orden consultada (200)': (r) => r.status === 200 });
    }
  } else if (roll < 0.9) {
    const res = http.get(`${BASE_URL}/api/catalog?limit=20`, { tags: { name: 'GET /api/catalog' } });
    check(res, { 'catálogo (200)': (r) => r.status === 200 });
  } else {
    const res = http.get(`${BASE_URL}/api/orders?limit=10`, { tags: { name: 'GET /api/orders' } });
    check(res, { 'listado (200)': (r) => r.status === 200 });
  }

  // Think time de un usuario real: 200-800 ms entre acciones (no aplica con tasa fija).
  if (!RATE) sleep(0.2 + Math.random() * 0.6);
}

export function handleSummary(data) {
  return {
    [`/results/${RUN_LABEL}-k6-summary.json`]: JSON.stringify(data, null, 2),
    stdout: `\n[${RUN_LABEL}] p99=${data.metrics.http_req_duration.values['p(99)'].toFixed(1)}ms ` +
      `p95=${data.metrics.http_req_duration.values['p(95)'].toFixed(1)}ms ` +
      `rps=${data.metrics.http_reqs.values.rate.toFixed(1)} ` +
      `errores=${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`,
  };
}
