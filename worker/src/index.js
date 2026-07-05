import { AwsClient } from "aws4fetch";

const UPLOAD_FORM = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Master Userlist Upload</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 560px; margin: 60px auto; padding: 0 20px; color: #222; }
  h1 { font-size: 20px; }
  .drop { border: 2px dashed #999; border-radius: 8px; padding: 40px; text-align: center; color: #666; }
  input[type=file] { margin: 16px 0; }
  button { background: #16a34a; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; cursor: pointer; }
  button:disabled { background: #999; }
  #status { margin-top: 16px; font-size: 14px; }
  ul { font-size: 13px; color: #555; }
  #status .row { padding: 4px 0; border-bottom: 1px solid #eee; }
  .ok { color: #16a34a; }
  .err { color: #dc2626; }
  .pending { color: #999; }
</style>
</head>
<body>
<h1>Master Userlist &mdash; Data Upload</h1>
<p>Upload one or more exports and they'll be ingested automatically into Master Userlist / Daily Records. Files upload directly to storage, so there's no size limit.</p>
<ul>
  <li><code>lotteryUserInfo_*.xlsx</code> &rarr; Master Userlist</li>
  <li><code>water_*.xlsx</code> &rarr; Deposits</li>
  <li><code>withdraw_*.xlsx</code> &rarr; Withdrawals</li>
  <li><code>detail_*.xlsx</code> &rarr; Wallet transactions</li>
  <li><code>Agent*.xlsx</code> &rarr; Agent assignments (Mastersheet 04 tab)</li>
  <li><code>Reassign*.xlsx</code> &rarr; Bulk agent reassignment (Column A: User ID, Column B: Agent Name -- must match a name already on the dashboard exactly, or "Un-Assigned")</li>
</ul>
<form id="f">
  <div class="drop">
    <input type="file" id="file" accept=".xlsx" multiple required>
  </div>
  <button type="submit" id="btn">Upload &amp; Ingest</button>
</form>
<div id="status"></div>

<hr style="margin:40px 0;border:none;border-top:1px solid #eee;">

<h1>Business API Token</h1>
<p>Deposits, withdrawals, and wallet details are pulled automatically from the business API using this token. Update it here whenever it rotates &mdash; no GitHub access needed. Saving a new token restarts the pipeline immediately.</p>
<div id="token-alert" style="display:none;margin-bottom:12px;padding:12px 14px;border-radius:6px;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;font-size:14px;font-weight:600;">
  &#9888;&#65039; Update new bearer token to run the pipeline
</div>
<div id="token-status" style="font-size:13px;color:#666;margin-bottom:10px;">Checking current token&hellip;</div>
<form id="tokenForm">
  <input type="password" id="tokenInput" placeholder="Paste new bearer token" style="width:100%;padding:10px;border:1px solid #ccc;border-radius:6px;font-size:13px;box-sizing:border-box;">
  <button type="submit" id="tokenBtn" style="margin-top:10px;">Save Token</button>
</form>
<div id="tokenMsg" style="margin-top:10px;font-size:14px;"></div>

<script>
async function refreshTokenStatus() {
  try {
    const res = await fetch('/api-token-status');
    const data = await res.json();
    document.getElementById('token-status').textContent = data.exists
      ? 'Current token last updated: ' + new Date(data.lastModified).toLocaleString()
      : 'No token saved yet -- the scheduled pull will fail until one is set.';
    document.getElementById('token-alert').style.display = (data.exists && data.pipelineOk === false) ? 'block' : 'none';
  } catch (e) {
    document.getElementById('token-status').textContent = 'Could not check token status.';
  }
}
refreshTokenStatus();
document.getElementById('tokenForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('tokenBtn');
  const msg = document.getElementById('tokenMsg');
  const input = document.getElementById('tokenInput');
  const token = input.value.trim();
  if (!token) return;
  btn.disabled = true;
  msg.textContent = 'Saving...';
  msg.className = '';
  try {
    const res = await fetch('/set-api-token', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.status);
    msg.textContent = 'Token saved -- pipeline restarting now.';
    msg.className = 'ok';
    input.value = '';
    document.getElementById('token-alert').style.display = 'none';
    refreshTokenStatus();
  } catch (err) {
    msg.textContent = 'Error: ' + err.message;
    msg.className = 'err';
  }
  btn.disabled = false;
});
</script>

<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('btn');
  const statusEl = document.getElementById('status');
  const files = Array.from(document.getElementById('file').files);
  if (!files.length) return;
  btn.disabled = true;
  statusEl.innerHTML = files.map((f, i) =>
    '<div class="row pending" id="row-' + i + '">' + f.name + ': queued</div>'
  ).join('');

  // Each file: 1) ask the worker for a presigned R2 PUT URL (bypasses the
  // Worker's own request-body limit since the actual upload goes straight
  // to R2), 2) PUT the file there, 3) notify the worker so it can trigger
  // the ingest workflow. The workflow itself queues via a concurrency
  // group, so it's safe for these to fire in parallel, but sequential
  // keeps the per-row status readable.
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const row = document.getElementById('row-' + i);
    try {
      row.textContent = file.name + ': requesting upload URL...';
      const presignRes = await fetch('/presign', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ filename: file.name }),
      });
      const presignData = await presignRes.json();
      if (!presignRes.ok) throw new Error(presignData.error || presignRes.status);

      row.textContent = file.name + ': uploading (' + (file.size / 1024 / 1024).toFixed(1) + ' MB)...';
      const putRes = await fetch(presignData.url, { method: 'PUT', body: file });
      if (!putRes.ok) throw new Error('upload failed: ' + putRes.status);

      row.textContent = file.name + ': starting ingest...';
      const notifyRes = await fetch('/notify', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key: presignData.key, file_type: presignData.file_type }),
      });
      const notifyData = await notifyRes.json();
      if (!notifyRes.ok) throw new Error(notifyData.error || notifyRes.status);

      row.textContent = file.name + ': ingest started (' + presignData.file_type + ')';
      row.className = 'row ok';
    } catch (err) {
      row.textContent = file.name + ': error - ' + err.message;
      row.className = 'row err';
    }
  }
  btn.disabled = false;
});
</script>
</body>
</html>`;

function detectFileType(filename) {
  if (filename.startsWith("lotteryUserInfo")) return "userlist";
  if (filename.startsWith("water")) return "deposits";
  if (filename.startsWith("withdraw")) return "withdrawals";
  if (filename.startsWith("detail")) return "wallet";
  // Checked before the plain "Agent" prefix below, since "Reassign..." would
  // otherwise also need to not collide with it -- order matters here only
  // because both prefixes start with different letters, so this is just
  // defensive ordering, not a real dependency.
  if (/^reassign/i.test(filename)) return "bulk_reassign";
  if (filename.startsWith("Agent") || filename.startsWith("agent")) return "agents";
  return null;
}

async function dispatchWorkflow(env, workflowFile, inputs) {
  const dispatchRes = await fetch(
    `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "master-userlist-upload-worker",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: inputs || {},
      }),
    }
  );
  if (!dispatchRes.ok) {
    const text = await dispatchRes.text();
    throw new Error(`failed to trigger ${workflowFile}: ${dispatchRes.status} ${text}`);
  }
}

async function triggerIngest(env, fileType, key) {
  return dispatchWorkflow(env, "ingest.yml", { file_type: fileType, key });
}

async function triggerReassign(env, userId, agent) {
  return dispatchWorkflow(env, "reassign_agent.yml", { user_id: String(userId), agent: agent || "" });
}

async function triggerBanUser(env, userId) {
  return dispatchWorkflow(env, "ban_user.yml", { user_id: String(userId) });
}

// The Reassign Agent widget lives on the dashboard (04-project-performance.*),
// a different origin from this upload worker -- CORS is required for that
// cross-origin POST to succeed.
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
};

// api_pull_ingest.py marks config/token_status.json ok:false the moment the
// business API token stops working, and /set-api-token immediately dispatches
// a fresh run once a new token is saved. So the hourly cron only needs to skip
// dispatching while that flag is already false -- no need to guess or re-check
// the token itself here, and it self-heals the instant a new token is saved.
async function runPullIfTokenOk(env) {
  try {
    const statusObj = await env.USERLIST_BUCKET.get("config/token_status.json");
    if (statusObj) {
      const status = await statusObj.json();
      if (status.ok === false) {
        console.log("Skipping scheduled api_pull.yml -- token known invalid since", status.checked_at);
        return;
      }
    }
  } catch (e) {
    // If the status check itself fails, don't let that block the pipeline --
    // fall through and dispatch as normal.
  }
  return dispatchWorkflow(env, "api_pull.yml", {});
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return new Response(UPLOAD_FORM, { headers: { "content-type": "text/html; charset=utf-8" } });
    }

    if (request.method === "POST" && url.pathname === "/presign") {
      try {
        const { filename } = await request.json();
        if (!filename || !filename.endsWith(".xlsx")) {
          return jsonError("Only .xlsx files are accepted", 400);
        }
        const fileType = detectFileType(filename);
        if (!fileType) {
          return jsonError(
            "Filename must start with lotteryUserInfo, water, withdraw, detail, Agent, or Reassign",
            400
          );
        }

        const key = `incoming/${fileType}/${Date.now()}_${filename}`;
        const client = new AwsClient({
          accessKeyId: env.R2_ACCESS_KEY_ID,
          secretAccessKey: env.R2_SECRET_ACCESS_KEY,
          service: "s3",
          region: "auto",
        });
        const objectUrl = `${env.R2_S3_ENDPOINT}/${env.R2_BUCKET_NAME}/${key}`;
        const signed = await client.sign(objectUrl, {
          method: "PUT",
          aws: { signQuery: true },
        });

        return new Response(JSON.stringify({ ok: true, url: signed.url, key, file_type: fileType }), {
          headers: { "content-type": "application/json" },
        });
      } catch (err) {
        return jsonError(err.message || "Unknown error", 500);
      }
    }

    if (request.method === "GET" && url.pathname === "/api-token-status") {
      try {
        const head = await env.USERLIST_BUCKET.head("config/business_api_token.txt");
        let pipelineOk = null;
        const statusObj = await env.USERLIST_BUCKET.get("config/token_status.json");
        if (statusObj) {
          const status = await statusObj.json();
          pipelineOk = status.ok;
        }
        return new Response(
          JSON.stringify({ exists: !!head, lastModified: head ? head.uploaded : null, pipelineOk }),
          { headers: { "content-type": "application/json" } }
        );
      } catch (err) {
        return jsonError(err.message || "Unknown error", 500);
      }
    }

    if (request.method === "POST" && url.pathname === "/set-api-token") {
      try {
        const { token } = await request.json();
        if (!token || typeof token !== "string" || token.trim().length < 10) {
          return jsonError("Token looks too short/empty", 400);
        }
        await env.USERLIST_BUCKET.put("config/business_api_token.txt", token.trim());
        // Clear any stale "invalid token" alert immediately -- the next run will set
        // it again if the new token also fails.
        await env.USERLIST_BUCKET.put(
          "config/token_status.json",
          JSON.stringify({ ok: true, message: null, checked_at: new Date().toISOString() })
        );
        // Restart the pipeline right away instead of waiting for the next scheduled tick.
        await dispatchWorkflow(env, "api_pull.yml", {});
        return new Response(JSON.stringify({ ok: true }), {
          headers: { "content-type": "application/json" },
        });
      } catch (err) {
        return jsonError(err.message || "Unknown error", 500);
      }
    }

    if (request.method === "POST" && url.pathname === "/notify") {
      try {
        const { key, file_type } = await request.json();
        if (!key || !file_type) {
          return jsonError("Missing key or file_type", 400);
        }
        await triggerIngest(env, file_type, key);
        return new Response(JSON.stringify({ ok: true }), {
          headers: { "content-type": "application/json" },
        });
      } catch (err) {
        return jsonError(err.message || "Unknown error", 500);
      }
    }

    if (request.method === "OPTIONS" && (url.pathname === "/reassign-agent" || url.pathname === "/ban-user")) {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    if (request.method === "POST" && url.pathname === "/reassign-agent") {
      try {
        const { user_id, agent } = await request.json();
        const userId = Number(user_id);
        if (!user_id || !Number.isInteger(userId) || userId <= 0) {
          return jsonError("user_id must be a positive integer", 400, CORS_HEADERS);
        }
        if (agent != null && typeof agent !== "string") {
          return jsonError("agent must be a string (or empty to un-assign)", 400, CORS_HEADERS);
        }
        await triggerReassign(env, userId, agent);
        return new Response(JSON.stringify({ ok: true }), {
          headers: { "content-type": "application/json", ...CORS_HEADERS },
        });
      } catch (err) {
        return jsonError(err.message || "Unknown error", 500, CORS_HEADERS);
      }
    }

    if (request.method === "POST" && url.pathname === "/ban-user") {
      try {
        const { user_id } = await request.json();
        const userId = Number(user_id);
        if (!user_id || !Number.isInteger(userId) || userId <= 0) {
          return jsonError("user_id must be a positive integer", 400, CORS_HEADERS);
        }
        await triggerBanUser(env, userId);
        return new Response(JSON.stringify({ ok: true }), {
          headers: { "content-type": "application/json", ...CORS_HEADERS },
        });
      } catch (err) {
        return jsonError(err.message || "Unknown error", 500, CORS_HEADERS);
      }
    }

    return new Response("Not found", { status: 404 });
  },

  async scheduled(event, env, ctx) {
    if (event.cron === "0 * * * *") {
      // One-time skip, per explicit request: the 2026-07-05 08:00 UTC run
      // (1:30 PM IST) is skipped -- the next hourly run (09:00 UTC / 2:30 PM
      // IST) already fires on the normal schedule right after, so no other
      // change is needed. Safe to remove this block once that date passes.
      const skipStart = new Date("2026-07-05T08:00:00Z");
      const skipEnd = new Date("2026-07-05T08:10:00Z");
      const scheduledAt = new Date(event.scheduledTime);
      if (scheduledAt >= skipStart && scheduledAt < skipEnd) {
        console.log("Skipping this scheduled api_pull.yml run (one-time, 2026-07-05 08:00 UTC / 1:30 PM IST)");
        return;
      }
      ctx.waitUntil(runPullIfTokenOk(env));
    } else if (event.cron === "30 0 * * *") {
      ctx.waitUntil(dispatchWorkflow(env, "sweep_incoming_v2.yml", {}));
    }
  },
};

function jsonError(message, status, extraHeaders) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "content-type": "application/json", ...(extraHeaders || {}) },
  });
}
