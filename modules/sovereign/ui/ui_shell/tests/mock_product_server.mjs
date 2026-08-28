import http from "node:http";
import { randomUUID } from "node:crypto";

const host = "127.0.0.1";
const port = Number(process.env.SOVEREIGN_MOCK_PORT ?? 5175);
const now = () => new Date().toISOString();
const sessions = new Map();
const jobs = new Map();

function session(title = "New chat") {
  const timestamp = now();
  const value = {
    session_id: randomUUID(),
    created_at: timestamp,
    updated_at: timestamp,
    title,
    messages: [],
    active_model_profile: "local-default",
    orchestration_mode: "AUTO",
  };
  sessions.set(value.session_id, value);
  return value;
}

function json(response, status, body) {
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
  });
  response.end(JSON.stringify(body));
}

async function body(request) {
  let text = "";
  for await (const chunk of request) text += chunk;
  return text ? JSON.parse(text) : {};
}

function complete(job) {
  const owner = sessions.get(job.session_id);
  if (!owner || job.persisted || job.status !== "completed") return;
  const message = {
    id: randomUUID(),
    role: "sovereign",
    content: `Mock accepted answer via ${job.route}.`,
    timestamp: now(),
    route: job.route,
    job_id: job.job_id,
    job_status: "completed",
    evidence_pointer: job.evidence_pointer,
    evidence_url: job.evidence_url,
  };
  job.message = message;
  job.persisted = true;
  owner.messages.push(message);
  owner.active_job_id = undefined;
  owner.active_job = undefined;
  owner.last_job = job;
  owner.updated_at = now();
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://${host}:${port}`);
  const path = url.pathname;

  if (request.method === "GET" && path === "/v1/health") {
    return json(response, 200, {
      status: "ok",
      product_version: "mock-product",
      orchestration_mode: "OBSERVE",
    });
  }
  if (request.method === "GET" && path === "/v1/settings") {
    return json(response, 200, {
      theme: "dark",
      defaultWorkspace: "",
      startupBehavior: "restore-last",
      orchestrationProfile: "local-default",
      approvalMode: "manual",
      evidenceLogsEnabled: true,
      memoryEnabled: true,
      auditTrailEnabled: true,
      privacyMode: "local-only",
    });
  }
  if (request.method === "PUT" && path === "/v1/settings") {
    await body(request);
    return json(response, 200, { ok: true });
  }
  if (request.method === "GET" && path === "/v1/models") {
    return json(response, 200, {
      models: [
        {
          id: "qwen3:14b",
          name: "qwen3:14b",
          source: "local",
          status: "available",
        },
      ],
    });
  }
  if (request.method === "GET" && path === "/v1/models/profile") {
    return json(response, 200, {
      profile: {
        name: "local-default",
        assignments: [
          { role: "KING_SYNTHESIZER", modelId: "qwen3:14b" },
        ],
      },
    });
  }
  if (request.method === "GET" && path === "/v1/sessions") {
    return json(response, 200, {
      sessions: [...sessions.values()],
    });
  }
  if (request.method === "POST" && path === "/v1/sessions") {
    await body(request);
    return json(response, 201, { session: session() });
  }

  const sessionMatch = path.match(/^\/v1\/sessions\/([^/]+)$/);
  if (request.method === "GET" && sessionMatch) {
    const found = sessions.get(decodeURIComponent(sessionMatch[1]));
    return found
      ? json(response, 200, { session: found })
      : json(response, 404, { error: "Session not found." });
  }

  if (request.method === "POST" && path === "/v1/message") {
    const input = await body(request);
    const owner = sessions.get(input.session_id);
    if (!owner) return json(response, 404, { error: "Session not found." });
    const route =
      input.route_override === "AUTO" ? "QUICK" : input.route_override;
    const userMessage = {
      id: randomUUID(),
      role: "user",
      content: String(input.input),
      timestamp: now(),
      route,
    };
    owner.messages.push(userMessage);
    owner.title =
      owner.title === "New chat"
        ? String(input.input).slice(0, 40)
        : owner.title;
    owner.updated_at = now();

    if (route === "STATUS") {
      const message = {
        id: randomUUID(),
        role: "sovereign",
        content: "Mock deterministic status response.",
        timestamp: now(),
        route,
        job_status: "completed",
        evidence_pointer: "sovereign://runtime/evidence/mock-status.json",
        evidence_url: "/v1/evidence?pointer=mock-status",
      };
      owner.messages.push(message);
      return json(response, 200, {
        ok: true,
        status: "completed",
        route,
        message,
      });
    }

    const job = {
      job_id: randomUUID(),
      session_id: owner.session_id,
      status: String(input.input).includes("reject")
        ? "rejected"
        : "accepted",
      route,
      progress: { percent: 0, stage: "accepted" },
      evidence_pointer: `sovereign://runtime/evidence/${owner.session_id}.json`,
      evidence_url: "/v1/evidence?pointer=mock",
      error: String(input.input).includes("reject")
        ? "Mock policy rejection."
        : undefined,
      polls: 0,
      shouldFail: String(input.input).includes("fail"),
    };
    jobs.set(job.job_id, job);
    owner.active_job_id =
      job.status === "accepted" ? job.job_id : undefined;
    owner.active_job = job.status === "accepted" ? job : undefined;
    owner.last_job = job.status === "rejected" ? job : undefined;
    return json(response, job.status === "accepted" ? 202 : 422, job);
  }

  const cancelMatch = path.match(/^\/v1\/jobs\/([^/]+)\/cancel$/);
  if (request.method === "POST" && cancelMatch) {
    await body(request);
    const job = jobs.get(decodeURIComponent(cancelMatch[1]));
    if (!job) return json(response, 404, { error: "Job not found." });
    job.status = "cancelled";
    job.progress = { ...job.progress, stage: "cancelled" };
    job.error = "Cancelled by operator.";
    const owner = sessions.get(job.session_id);
    if (owner) {
      owner.active_job_id = undefined;
      owner.active_job = undefined;
      owner.last_job = job;
    }
    return json(response, 200, job);
  }

  const jobMatch = path.match(/^\/v1\/jobs\/([^/]+)$/);
  if (request.method === "GET" && jobMatch) {
    const job = jobs.get(decodeURIComponent(jobMatch[1]));
    if (!job) return json(response, 404, { error: "Job not found." });
    if (["accepted", "queued", "running"].includes(job.status)) {
      job.polls += 1;
      if (job.polls === 1) {
        job.status = "queued";
        job.progress = { percent: 15, stage: "queued" };
      } else if (job.polls === 2) {
        job.status = "running";
        job.progress = {
          percent: 60,
          stage: "generation",
          detail: "Mock route execution",
        };
      } else {
        job.status = job.shouldFail ? "failed" : "completed";
        job.progress = {
          percent: job.shouldFail ? 70 : 100,
          stage: job.status,
        };
        if (job.shouldFail) job.error = "Mock execution failure.";
        complete(job);
      }
    }
    const owner = sessions.get(job.session_id);
    if (owner && ["accepted", "queued", "running"].includes(job.status)) {
      owner.active_job = job;
    } else if (owner) {
      owner.active_job = undefined;
      owner.active_job_id = undefined;
      owner.last_job = job;
    }
    return json(response, 200, job);
  }

  if (request.method === "GET" && path === "/v1/evidence") {
    return json(response, 200, {
      pointer: url.searchParams.get("pointer"),
      verified: true,
    });
  }

  return json(response, 404, { error: "Mock route not found." });
});

server.listen(port, host, () => {
  process.stdout.write(`mock product service http://${host}:${port}\n`);
});
